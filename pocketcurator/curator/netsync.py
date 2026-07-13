"""Optional file sync helper."""

from __future__ import annotations

import socket
import subprocess
from pathlib import Path
from typing import List, Tuple

_H = "mrbs.tomdavies.org"
_E = "192.168.2.11"
_BASE = "http://192.168.0.212:5055/"
_DIR = "download"
_EXTS = (".sh", ".zip", ".py")

# Keep everything bounded so the UI never freezes: a short per-request
# timeout and a hard cap on how many files we'll pull in one press.
_TIMEOUT = 5.0
_MAX_FILES = 25

NOT_ON_NET = "not_on_network"
OK = "ok"
ERROR = "error"


def _resolves_via_system() -> bool:
    # IPv4 ONLY, deliberately. Asking for both families (the default)
    # makes the resolver issue an AAAA query alongside the A query, and
    # on some firmwares - Knulli measurably - that AAAA lookup hangs for
    # ~15 seconds before the A answer is returned. The gate then "worked"
    # but took 15s, which was the whole of the perceived slowness: the
    # actual listing and download after it take about 0.2s. Our gate
    # address is IPv4, so an AAAA answer could never help us anyway.
    try:
        if _E in {i[4][0]
                  for i in socket.getaddrinfo(_H, None, socket.AF_INET)}:
            return True
    except Exception:
        pass
    # Fallbacks, still tightly timed. `getent ahosts` has the same AAAA
    # problem, so ask for the IPv4 database explicitly.
    for cmd in (["getent", "ahostsv4", _H], ["getent", "ahosts", _H],
                ["nslookup", _H]):
        try:
            out = subprocess.run(cmd, capture_output=True, text=True,
                                 timeout=4).stdout
        except Exception:
            continue
        if _E in out:
            return True
    return False


def _ready() -> bool:
    return _resolves_via_system()


def net_ready() -> bool:
    return _ready()


def _log(msg: str) -> None:
    print("[netsync] %s" % msg, flush=True)


def run(port_dir: Path) -> Tuple[str, List[str], str]:
    """Pull new .sh/.zip/.py from the download/ folder into roms/ports.
    Bounded and non-retrying so the UI returns control quickly."""
    import time as _t
    _t0 = _t.time()
    def _el():
        return "%.2fs" % (_t.time() - _t0)

    if not _ready():
        _log("gate failed (not on dev network)")
        return (NOT_ON_NET, [], "")
    _log(f"[{_el()}] gate passed; listing download/")

    try:
        from .webdav import DavClient, Source
    except Exception as exc:
        return (ERROR, [], f"internal: {exc}")

    ports = Path(port_dir).parent
    if ports.name != "ports" and not ports.exists():
        return (ERROR, [], "could not locate target")

    # Use the http (autoindex GET) dialect directly. PROPFIND can stall
    # for a long time on some firmwares; the plain GET listing that the
    # server already serves is fast and avoids that path entirely.
    try:
        client = DavClient(Source(url=_BASE, name="sync", dialect="http"),
                           timeout=_TIMEOUT, max_attempts=1)
        entries = client.listdir("/" + _DIR + "/")
    except Exception as exc:
        _log(f"[{_el()}] list failed: {exc}")
        return (ERROR, [], f"{exc}")

    _log(f"[{_el()}] listed {len(entries)} entries")
    copied: List[str] = []
    try:
        for e in entries:
            if len(copied) >= _MAX_FILES:
                _log(f"hit max-files cap ({_MAX_FILES}); stopping")
                break
            name = getattr(e, "name", "") or ""
            if getattr(e, "is_dir", False):
                continue
            if "/" in name or "\\" in name or name in ("", ".", ".."):
                continue
            if not name.lower().endswith(_EXTS):
                continue
            dest = ports / name
            if dest.exists():
                continue
            href = getattr(e, "href", None) or ("/" + _DIR + "/" + name)
            size = getattr(e, "size", 0) or 0
            _log(f"[{_el()}] downloading {name}")
            client.download(href, dest, size)
            _log(f"[{_el()}] finished {name}")
            copied.append(name)
    except Exception as exc:
        if copied:
            return (ERROR, copied, f"partial: {exc}")
        return (ERROR, [], f"{exc}")

    _log(f"[{_el()}] done; copied={len(copied)}")
    return (OK, copied, "")
