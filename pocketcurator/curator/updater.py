"""
In-app updater. Checks GitHub for the latest release, downloads the
port zip, verifies it, and stages it for the launcher to apply on the
next launch.

Design notes:

- All network I/O goes through the SYSTEM curl, not python's urllib.
  The bundled Pyxel runtime's ssl module can't be trusted to find the
  firmware's CA bundle on every device, while curl always uses the
  system store the firmware maintains. curl is a hard PortMaster
  dependency, so it's present on every target.

- Nothing here ever touches the live install. The download lands in
  <port_dir>/.update/, is hash- and integrity-verified there, extracted
  to .update/staged/, and a READY flag is written last. The launcher
  applies the swap at the START of the next launch, before any code is
  running. If power dies mid-apply, READY survives and the apply simply
  re-runs. settings.json is pruned from the staged tree so an update
  can never clobber user settings.

- State machine, mutated only by the single worker thread, read by the
  render loop:
      IDLE -> CHECKING -> UP_TO_DATE | AVAILABLE | ERROR
      AVAILABLE -> DOWNLOADING -> VERIFYING -> STAGING -> STAGED | ERROR
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import threading
import time
import zipfile
from pathlib import Path
from typing import Optional

GITHUB_REPO = "tomtombombadil/PocketCurator"
API_LATEST = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
# All releases (newest first), including pre-releases. Used by the hidden
# developer pre-release channel (Y on Check For Updates).
API_RELEASES = f"https://api.github.com/repos/{GITHUB_REPO}/releases?per_page=30"
ASSET_RE = re.compile(r"^pocketcurator_port-v[\d.]+\.zip$")

# Free space demanded before download: zip (~5 MB) + staged tree
# (~18 MB) + headroom. A full SD card mid-extract is a classic way to
# wreck an install, so check first.
REQUIRED_FREE_BYTES = 60 * 1024 * 1024

# A clock earlier than this means the device hasn't NTP-synced (most of
# these handhelds have no RTC). TLS cert validation will fail with a
# baffling error, so detect it up front and say something useful.
SANE_CLOCK_EPOCH = 1767225600  # 2026-01-01

IDLE = "idle"
CHECKING = "checking"
UP_TO_DATE = "up_to_date"
AVAILABLE = "available"
DOWNLOADING = "downloading"
VERIFYING = "verifying"
STAGING = "staging"
STAGED = "staged"
ERROR = "error"


def _version_tuple(s: str):
    """'v0.62.0' or '0.62.0' -> (0, 62, 0). Non-numeric junk -> zeros."""
    s = s.strip().lstrip("vV")
    parts = []
    for piece in s.split("."):
        m = re.match(r"\d+", piece)
        parts.append(int(m.group(0)) if m else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


class Updater:
    def __init__(self, port_dir: Path, current_version: str):
        self.port_dir = Path(port_dir)
        self.current_version = current_version
        self.update_dir = self.port_dir / ".update"

        self.state = IDLE
        self.error: str = ""
        self.latest_version: str = ""
        self.progress: float = 0.0  # 0..1 while DOWNLOADING

        self._asset_url: str = ""
        self._asset_size: int = 0
        self._sha_url: str = ""
        self._thread: Optional[threading.Thread] = None

        # A previous session may have already staged this or a newer
        # version; reflect that instead of offering a re-download.
        try:
            ready = self.update_dir / "READY"
            if ready.is_file():
                staged_ver = ready.read_text(encoding="utf-8").strip()
                if _version_tuple(staged_ver) > _version_tuple(current_version):
                    self.latest_version = staged_ver
                    self.state = STAGED
                else:
                    # Stale leftovers from before this version: clean up.
                    shutil.rmtree(self.update_dir, ignore_errors=True)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Public API (called from the UI thread)
    # ------------------------------------------------------------------

    def busy(self) -> bool:
        return self.state in (CHECKING, DOWNLOADING, VERIFYING, STAGING)

    def start_check(self) -> None:
        if self.busy() or self.state == STAGED:
            return
        self.state = CHECKING
        self.error = ""
        self._spawn(self._check_worker)

    def start_download(self) -> None:
        if self.state != AVAILABLE:
            return
        self.state = DOWNLOADING
        self.progress = 0.0
        self.error = ""
        self._spawn(self._download_worker)

    def start_full(self) -> None:
        """Check, and if an update exists, download + verify + stage it
        in one motion - no second confirmation. This is what the update
        dialog runs; the whole pipeline logs as it goes."""
        if self.busy() or self.state == STAGED:
            return
        self.state = CHECKING
        self.error = ""
        self._spawn(self._full_worker)

    def start_full_prerelease(self) -> None:
        """Hidden developer channel: check the newest PRE-RELEASE and, if
        it differs from what's installed, download + stage it in one
        motion. Not surfaced in the UI help text - triggered by Y on the
        Check For Updates row. Unlike the normal channel it installs a
        pre-release even if its version is not strictly newer, so you can
        move between test builds freely."""
        if self.busy() or self.state == STAGED:
            return
        self.state = CHECKING
        self.error = ""
        self._spawn(self._full_prerelease_worker)

    def _full_worker(self) -> None:
        self._check_worker()
        if self.state == AVAILABLE:
            self.state = DOWNLOADING
            self.progress = 0.0
            self._download_worker()

    def _full_prerelease_worker(self) -> None:
        self._check_prerelease_worker()
        if self.state == AVAILABLE:
            self.state = DOWNLOADING
            self.progress = 0.0
            self._download_worker()

    def _check_prerelease_worker(self) -> None:
        try:
            self._say("checking for PRE-RELEASE (developer channel)...")
            if not shutil.which("curl"):
                raise UpdateError("curl not found on this firmware.")
            data = self._fetch_json(API_RELEASES)
            if not isinstance(data, list):
                raise UpdateError("Unexpected releases response.")
            # Newest pre-release that has our port zip attached. GitHub
            # returns releases newest-first; honor that order.
            chosen = None
            for rel in data:
                if not rel.get("prerelease"):
                    continue
                zip_asset = sha_asset = None
                for a in rel.get("assets", []) or []:
                    name = str(a.get("name", ""))
                    if ASSET_RE.match(name):
                        zip_asset = a
                    elif name.endswith(".zip.sha256"):
                        sha_asset = a
                if zip_asset:
                    chosen = (rel, zip_asset, sha_asset)
                    break
            if not chosen:
                self._say("no pre-release with a port zip found")
                self.state = UP_TO_DATE
                return
            rel, zip_asset, sha_asset = chosen
            tag = str(rel.get("tag_name", ""))
            # Install pre-releases even if not strictly newer, but skip a
            # redundant re-install of the exact version already running.
            if _version_tuple(tag) == _version_tuple(self.current_version):
                self._say(f"already on pre-release {tag}")
                self.state = UP_TO_DATE
                return
            self.latest_version = tag.lstrip("vV")
            self._say(f"pre-release found: {tag} "
                      f"({int(zip_asset.get('size', 0) or 0) // 1024} KB)")
            self._asset_url = zip_asset.get("browser_download_url", "")
            self._asset_size = int(zip_asset.get("size", 0) or 0)
            self._sha_url = (sha_asset or {}).get("browser_download_url", "")
            self.state = AVAILABLE
        except UpdateError as exc:
            self._fail(str(exc))
        except Exception as exc:  # noqa - never crash the UI thread's app
            self._fail(f"Pre-release check failed: {exc}")

    def _say(self, msg: str) -> None:
        print(f"[updater] {msg}")

    def status_text(self) -> str:
        """One-liner for the settings row's value column."""
        return {
            IDLE: "",
            CHECKING: "Checking...",
            UP_TO_DATE: "Up to date",
            AVAILABLE: f"v{self.latest_version} found",
            DOWNLOADING: f"Downloading {int(self.progress * 100)}%",
            VERIFYING: "Verifying...",
            STAGING: "Preparing...",
            STAGED: f"v{self.latest_version} ready - restart to apply",
            ERROR: "Failed - A: retry",
        }.get(self.state, "?")

    def hint_text(self) -> str:
        """Context line for the settings screen's hint area."""
        if self.state == ERROR:
            return self.error or "Update failed."
        if self.state == AVAILABLE:
            mb = self._asset_size / (1024 * 1024) if self._asset_size else 0
            size = f" ({mb:.1f} MB)" if mb else ""
            return f"Press A to download v{self.latest_version}{size}."
        if self.state == STAGED:
            return ("Downloaded and verified. The update installs itself "
                    "the next time you launch Pocket Curator.")
        if self.state == UP_TO_DATE:
            return f"You are running the latest version (v{self.current_version})."
        if self.busy():
            return "Working... you can keep using the app."
        return "Checks GitHub for a new release. Needs WiFi."

    # ------------------------------------------------------------------
    # Workers
    # ------------------------------------------------------------------

    def _spawn(self, target) -> None:
        self._thread = threading.Thread(target=target, daemon=True)
        self._thread.start()

    def _check_worker(self) -> None:
        try:
            self._say(f"checking for update (current v{self.current_version})...")
            if not shutil.which("curl"):
                raise UpdateError("curl not found on this firmware.")
            data = self._fetch_json(API_LATEST)
            tag = str(data.get("tag_name", ""))
            assets = data.get("assets", []) or []
            zip_asset = sha_asset = None
            for a in assets:
                name = str(a.get("name", ""))
                if ASSET_RE.match(name):
                    zip_asset = a
                elif name.endswith(".zip.sha256"):
                    sha_asset = a
            if not tag or not zip_asset:
                raise UpdateError("Release found but no port zip attached.")
            if _version_tuple(tag) <= _version_tuple(self.current_version):
                self._say(f"up to date (latest release is {tag})")
                self.state = UP_TO_DATE
                return
            self.latest_version = tag.lstrip("vV")
            self._say(f"update found: {tag} "
                      f"({int(zip_asset.get('size', 0) or 0) // 1024} KB)")
            self._asset_url = zip_asset.get("browser_download_url", "")
            self._asset_size = int(zip_asset.get("size", 0) or 0)
            self._sha_url = (sha_asset or {}).get("browser_download_url", "")
            self.state = AVAILABLE
        except UpdateError as exc:
            self._fail(str(exc))
        except Exception as exc:  # noqa - never crash the UI thread's app
            self._fail(f"Update check failed: {exc}")

    def _download_worker(self) -> None:
        zip_path = self.update_dir / "update.zip"
        try:
            free = shutil.disk_usage(self.port_dir).free
            if free < REQUIRED_FREE_BYTES:
                raise UpdateError(
                    f"Not enough free space ({free // (1024*1024)} MB free, "
                    f"need {REQUIRED_FREE_BYTES // (1024*1024)} MB).")

            shutil.rmtree(self.update_dir, ignore_errors=True)
            self.update_dir.mkdir(parents=True, exist_ok=True)

            self._say(f"downloading v{self.latest_version} from {self._asset_url}")
            self._download(self._asset_url, zip_path, self._asset_size)
            self._say("download complete; verifying...")

            self.state = VERIFYING
            self._verify(zip_path)
            self._say("verified; staging into .update/staged")

            self.state = STAGING
            staged = self.update_dir / "staged"
            with zipfile.ZipFile(zip_path) as zf:
                zf.extractall(staged)
            # Never let an update clobber the user's settings. The zip's
            # settings.json is the factory default; it only matters for
            # fresh installs, which the installer handles separately.
            try:
                (staged / "pocketcurator" / "settings.json").unlink()
            except OSError:
                pass
            zip_path.unlink(missing_ok=True)

            # READY is written LAST: its presence means "staged tree is
            # complete and verified". The launcher keys off it.
            (self.update_dir / "READY").write_text(
                self.latest_version, encoding="utf-8")
            self.state = STAGED
            self._say(f"v{self.latest_version} staged - the launcher "
                      f"applies it at the start of the next launch")
        except UpdateError as exc:
            shutil.rmtree(self.update_dir, ignore_errors=True)
            self._fail(str(exc))
        except Exception as exc:  # noqa
            shutil.rmtree(self.update_dir, ignore_errors=True)
            self._fail(f"Update failed: {exc}")

    # ------------------------------------------------------------------
    # Network plumbing (system curl)
    # ------------------------------------------------------------------

    def _fetch_json(self, url: str) -> dict:
        proc = subprocess.run(
            ["curl", "-sfL", "--connect-timeout", "10", "-m", "20",
             "-H", "Accept: application/vnd.github+json", url],
            capture_output=True, text=True)
        if proc.returncode != 0:
            raise UpdateError(self._curl_excuse(proc.returncode))
        try:
            return json.loads(proc.stdout)
        except ValueError:
            raise UpdateError("GitHub sent an unreadable reply. Try again later.")

    def _download(self, url: str, dest: Path, expected_size: int) -> None:
        proc = subprocess.Popen(
            ["curl", "-sfL", "--connect-timeout", "10", "-m", "600",
             "-o", str(dest), url],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        while proc.poll() is None:
            if expected_size > 0:
                try:
                    self.progress = min(
                        0.99, dest.stat().st_size / expected_size)
                except OSError:
                    pass
            time.sleep(0.2)
        if proc.returncode != 0:
            raise UpdateError(self._curl_excuse(proc.returncode))
        self.progress = 1.0

    def _verify(self, zip_path: Path) -> None:
        # 1. Published SHA256, if the release carries one. Format is the
        #    sha256sum convention: "<hex>  <filename>".
        if self._sha_url:
            proc = subprocess.run(
                ["curl", "-sfL", "--connect-timeout", "10", "-m", "20",
                 self._sha_url],
                capture_output=True, text=True)
            if proc.returncode == 0 and proc.stdout.strip():
                expected = proc.stdout.split()[0].strip().lower()
                h = hashlib.sha256()
                with open(zip_path, "rb") as f:
                    for chunk in iter(lambda: f.read(1024 * 256), b""):
                        h.update(chunk)
                if h.hexdigest().lower() != expected:
                    raise UpdateError(
                        "Downloaded file failed its integrity check. "
                        "Try again - if it keeps failing, your WiFi may "
                        "be mangling downloads.")
        # 2. Zip structural integrity, always.
        try:
            with zipfile.ZipFile(zip_path) as zf:
                bad = zf.testzip()
                names = set(zf.namelist())
            if bad is not None:
                raise UpdateError("Downloaded zip is corrupt. Try again.")
            if "Pocket Curator.sh" not in names:
                raise UpdateError("Downloaded zip doesn't look like a "
                                  "Pocket Curator release.")
        except zipfile.BadZipFile:
            raise UpdateError("Downloaded zip is corrupt. Try again.")

    def _curl_excuse(self, code: int) -> str:
        if code in (5, 6, 7, 28):
            return "Can't reach GitHub. Is WiFi connected?"
        if code in (35, 51, 58, 60, 77, 90, 91):
            if time.time() < SANE_CLOCK_EPOCH:
                return ("Secure connection failed - your device's clock "
                        "looks wrong. Stay on WiFi a minute so it can "
                        "sync, then retry.")
            return "Secure connection to GitHub failed. Try again later."
        if code == 22:
            return ("GitHub refused the request (rate limit?). "
                    "Wait a few minutes and retry.")
        return f"Network error (curl exit {code})."

    def _fail(self, message: str) -> None:
        self.error = message
        self.state = ERROR
        print(f"[updater] {message}")


class UpdateError(Exception):
    pass

# ----------------------------------------------------------------------
# Environment probes (used by the Status dialog)
# ----------------------------------------------------------------------

def clock_is_sane() -> bool:
    """True when the system clock is recent enough for TLS certificate
    validation. No-RTC handhelds boot in the past until NTP syncs."""
    return time.time() >= SANE_CLOCK_EPOCH


def check_internet(timeout: int = 5) -> bool:
    """True when GitHub is reachable over HTTPS. curl exit 22 means an
    HTTP error status (e.g. rate limited) - the connection itself
    worked, which is all this probe asks."""
    if not shutil.which("curl"):
        return False
    proc = subprocess.run(
        ["curl", "-sfI", "--connect-timeout", str(timeout),
         "-m", str(timeout * 2), "-o", "/dev/null",
         "https://api.github.com"],
        capture_output=True)
    return proc.returncode in (0, 22)

