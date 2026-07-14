#!/bin/bash
# PORTMASTER: pocketcurator.zip, PocketCurator.Installer.sh
# ===========================================================================
# Pocket Curator one-file installer
# ===========================================================================
# Copy THIS FILE alone into your ports folder and launch it from
# EmulationStation. With WiFi connected, it downloads the latest Pocket
# Curator release from GitHub, verifies it, installs it, and refreshes
# EmulationStation so Pocket Curator appears - icon and all.
#
# It always installs the LATEST release, so this file never goes stale.
# Re-running it later reinstalls/repairs (your settings are preserved).
# After a successful install you can delete it, or keep it around.
#
# WHICH RELEASE?
# --------------
# It installs the NEWEST release, whether that is a stable release or a
# pre-release. That is deliberate: an older stable release may not be able
# to update itself to a newer pre-release, so installing "the latest stable"
# could strand a fresh device on a version it cannot move off.
#
# Once Pocket Curator is installed, you choose for yourself from inside the
# app: Settings > Check For Updates offers both channels - A for the stable
# release, Y for the pre-release.
# ===========================================================================

REPO="tomtombombadil/PocketCurator"
API_LATEST="https://api.github.com/repos/$REPO/releases/latest"
API_ALL="https://api.github.com/repos/$REPO/releases?per_page=30"

# Self-heal Windows line endings if they snuck in.
if LC_ALL=C grep -q $'\r' "$0" 2>/dev/null; then
    self_clean="$(dirname "$0")/.${0##*/}.lf"
    if tr -d '\r' < "$0" > "$self_clean" 2>/dev/null && [ -s "$self_clean" ]; then
        chmod +x "$self_clean" 2>/dev/null
        exec /bin/bash "$self_clean" "$@"
    fi
    echo "[PC-Install] FATAL: installer has Windows line endings; cannot self-heal." >&2
    exit 1
fi

{ # force bash to load the whole script into RAM

shopt -s expand_aliases
XDG_DATA_HOME=${XDG_DATA_HOME:-$HOME/.local/share}
SCRIPT_DIR="$(dirname "$0")"

# ---- PortMaster bootstrap (same hunt as the main launcher) ---------------
controlfolder=""
for candidate in \
    "/opt/system/Tools/PortMaster" \
    "/opt/tools/PortMaster" \
    "$XDG_DATA_HOME/PortMaster" \
    "$SCRIPT_DIR/PortMaster" \
    "/roms/ports/PortMaster" \
    "/roms2/ports/PortMaster"; do
  if [ -f "$candidate/control.txt" ]; then
    controlfolder="$candidate"
    break
  fi
done
if [ -z "$controlfolder" ]; then
  echo "[PC-Install] FATAL: no working PortMaster install found." >&2
  echo "[PC-Install] Please install PortMaster from https://portmaster.games/ first." >&2
  exit 1
fi
source "$controlfolder/control.txt"
cfw_lower="$(echo "$CFW_NAME" | tr '[:upper:]' '[:lower:]')"
if [ -f "${controlfolder}/mod_${cfw_lower}.txt" ]; then
  source "${controlfolder}/mod_${cfw_lower}.txt"
elif [ -f "${controlfolder}/mod_${CFW_NAME}.txt" ]; then
  source "${controlfolder}/mod_${CFW_NAME}.txt"
fi
type pm_message >/dev/null 2>&1 || pm_message() { echo "[pm_message] $*"; }

PORTS_DIR="/$directory/ports"
GAMEDIR="$PORTS_DIR/pocketcurator"
WORK_ZIP="$PORTS_DIR/.pc_install.zip"
LOGF="$PORTS_DIR/pocketcurator_install.log"
> "$LOGF" 2>/dev/null

say() {
  echo "[PC-Install] $*"
  # Flush each stage to disk AND sync, so a hard freeze still leaves a
  # breadcrumb of exactly how far the installer got (we had a fresh
  # Knulli wedge with no log; this makes the next one diagnosable).
  { echo "$(date '+%F %T') $*" >> "$LOGF"; sync; } 2>/dev/null
  pm_message "Pocket Curator: $*"
}

die() {
  say "FAILED: $*"
  pm_message "Install failed: $*"
  sleep 6
  rm -f "$WORK_ZIP"
  exit 1
}

say "installer starting on $CFW_NAME"

# ---- preflight ------------------------------------------------------------
command -v curl  >/dev/null 2>&1 || die "curl not found on this firmware."
command -v unzip >/dev/null 2>&1 || die "unzip not found on this firmware."

# No-RTC devices boot with a bogus clock until NTP syncs, which breaks
# TLS with a cryptic error. Detect it and say something a human can act on.
if [ "$(date +%Y)" -lt 2026 ]; then
  say "device clock looks wrong ($(date +%F)) - TLS may fail."
  say "if this install fails: connect WiFi, wait a minute, run me again."
fi

# Free space: zip (~5 MB) + extracted (~18 MB) + headroom.
free_kb=$(df -Pk "$PORTS_DIR" 2>/dev/null | awk 'NR==2 {print $4}')
if [ -n "$free_kb" ] && [ "$free_kb" -lt 61440 ]; then
  die "not enough free space ($((free_kb / 1024)) MB free, need 60 MB)."
fi

# ---- find the latest release ----------------------------------------------
say "looking up the newest release..."

# /releases lists every release, newest first, pre-releases included. We
# take the newest one that actually carries a port zip. Using
# /releases/latest instead would only ever see STABLE releases - and a
# device installed from an old stable can be left unable to reach anything
# newer, which is exactly the trap we're avoiding.
all_json="$(curl -sfL --connect-timeout 10 -m 25 \
              -H 'Accept: application/vnd.github+json' "$API_ALL")" \
  || die "can't reach GitHub. Is WiFi connected?"

if command -v python3 >/dev/null 2>&1; then
  read -r tag zip_url sha_url <<EOF
$(printf '%s' "$all_json" | python3 -c "
import json, sys
try:
    rels = json.load(sys.stdin)
except Exception:
    sys.exit(0)
for r in rels:
    if r.get('draft'):
        continue
    z = s = ''
    for a in r.get('assets') or []:
        n = a.get('name') or ''
        if n.startswith('pocketcurator_port-v') and n.endswith('.zip'):
            z = a.get('browser_download_url') or ''
        elif n.endswith('.zip.sha256'):
            s = a.get('browser_download_url') or ''
    if z:
        print(r.get('tag_name',''), z, s)
        break
" 2>/dev/null)
EOF
else
  # Shouldn't happen: every supported firmware ships python3 (the app needs
  # it). Fall back to the stable release rather than guess at the JSON.
  say "python3 not found - falling back to the latest stable release."
  api_json="$(curl -sfL --connect-timeout 10 -m 20 \
                -H 'Accept: application/vnd.github+json' "$API_LATEST")" \
    || die "can't reach GitHub. Is WiFi connected?"
  tag="$(echo "$api_json" | grep -o '"tag_name"[^,]*' | head -1 \
          | sed -E 's/.*"(v[0-9.]+)".*/\1/')"
  zip_url="$(echo "$api_json" | grep -o '"browser_download_url"[^"]*"[^"]*pocketcurator_port-v[0-9.]*\.zip"' \
          | head -1 | sed -E 's/.*"(https[^"]+)"/\1/')"
  sha_url="$(echo "$api_json" | grep -o '"browser_download_url"[^"]*"[^"]*pocketcurator_port-v[0-9.]*\.zip\.sha256"' \
          | head -1 | sed -E 's/.*"(https[^"]+)"/\1/')"
fi

[ -n "$tag" ] && [ -n "$zip_url" ] || die "couldn't find a release zip on GitHub."

say "found $tag - downloading (about 5 MB)..."

# ---- download + verify -----------------------------------------------------
rm -f "$WORK_ZIP"
curl -fL --connect-timeout 10 -m 600 -o "$WORK_ZIP" "$zip_url" >> "$LOGF" 2>&1 \
  || { rm -f "$WORK_ZIP"; curl -fL --connect-timeout 10 -m 600 -o "$WORK_ZIP" "$zip_url" >> "$LOGF" 2>&1; } \
  || die "download failed. Check WiFi and try again."

if [ -n "$sha_url" ] && command -v sha256sum >/dev/null 2>&1; then
  expected="$(curl -sfL --connect-timeout 10 -m 20 "$sha_url" | awk '{print $1}')"
  if [ -n "$expected" ]; then
    actual="$(sha256sum "$WORK_ZIP" | awk '{print $1}')"
    [ "$actual" = "$expected" ] || die "download failed its integrity check. Try again."
    say "checksum verified."
  fi
fi
unzip -tqq "$WORK_ZIP" >/dev/null 2>&1 || die "downloaded zip is corrupt. Try again."

# ---- install ----------------------------------------------------------------
say "installing $tag..."
if [ -f "$GAMEDIR/settings.json" ]; then
  # Reinstall/repair: never clobber the user's settings.
  unzip -oqq "$WORK_ZIP" -x "pocketcurator/settings.json" -d "$PORTS_DIR" \
    || die "extraction failed (SD card full or read-only?)."
else
  unzip -oqq "$WORK_ZIP" -d "$PORTS_DIR" \
    || die "extraction failed (SD card full or read-only?)."
fi
rm -f "$WORK_ZIP"
chmod +x "$PORTS_DIR/Pocket Curator.sh" \
         "$GAMEDIR/tools/install_metadata.sh" 2>/dev/null

# ---- metadata + ES refresh ---------------------------------------------------
# The metadata installer writes our icon/description/video into the Ports
# gamelist and already knows how to refresh EmulationStation on every
# supported firmware (reload API, or service restart on ArkOS-family) -
# which also makes the new 'Pocket Curator' entry itself appear.
say "$tag installed - registering with EmulationStation..."
# Run metadata registration with a hard timeout so it can NEVER hang the
# installer or the device. The script schedules its own deferred ES
# refresh and returns quickly; the timeout is just a backstop.
_run_meta() {
  local script="$1"
  if command -v timeout >/dev/null 2>&1; then
    PC_SKIP_PMFINISH=1 timeout 60 /bin/bash "$script" >> "$LOGF" 2>&1
  else
    PC_SKIP_PMFINISH=1 /bin/bash "$script" >> "$LOGF" 2>&1
  fi
}
if [ -f "$GAMEDIR/tools/install_metadata.sh" ]; then
  _run_meta "$GAMEDIR/tools/install_metadata.sh"     || say "metadata step returned non-zero or timed out (install still OK)"
elif [ -f "$PORTS_DIR/PocketCuratorMetadataInstall.sh" ]; then
  _run_meta "$PORTS_DIR/PocketCuratorMetadataInstall.sh"     || say "metadata step returned non-zero or timed out (install still OK)"
fi

# Our log started in the ports root before pocketcurator/ existed;
# now that it does, keep the ports folder clean and move it home.
if [ -d "$GAMEDIR" ]; then
  mv -f "$LOGF" "$GAMEDIR/install.log" 2>/dev/null && LOGF="$GAMEDIR/install.log"
fi
say "done! Pocket Curator $tag will appear in Ports momentarily."
pm_message "Pocket Curator $tag installed! You can delete the installer, or keep it for repairs."
sleep 6
exit 0

} # end RAM-load brace
