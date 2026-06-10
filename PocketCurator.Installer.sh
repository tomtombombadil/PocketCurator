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
# ===========================================================================

REPO="tomtombombadil/PocketCurator"
API_LATEST="https://api.github.com/repos/$REPO/releases/latest"

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
  echo "$(date '+%F %T') $*" >> "$LOGF" 2>/dev/null
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
say "looking up the latest release..."
api_json="$(curl -sfL --connect-timeout 10 -m 20 \
              -H 'Accept: application/vnd.github+json' "$API_LATEST")" \
  || die "can't reach GitHub. Is WiFi connected?"

tag="$(echo "$api_json" | grep -o '"tag_name"[^,]*' | head -1 \
        | sed -E 's/.*"(v[0-9.]+)".*/\1/')"
zip_url="$(echo "$api_json" | grep -o '"browser_download_url"[^"]*"[^"]*pocketcurator_port-v[0-9.]*\.zip"' \
        | head -1 | sed -E 's/.*"(https[^"]+)"/\1/')"
sha_url="$(echo "$api_json" | grep -o '"browser_download_url"[^"]*"[^"]*pocketcurator_port-v[0-9.]*\.zip\.sha256"' \
        | head -1 | sed -E 's/.*"(https[^"]+)"/\1/')"
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
if [ -f "$GAMEDIR/tools/install_metadata.sh" ]; then
  PC_SKIP_PMFINISH=1 /bin/bash "$GAMEDIR/tools/install_metadata.sh" >> "$LOGF" 2>&1
elif [ -f "$PORTS_DIR/PocketCuratorMetadataInstall.sh" ]; then
  # Releases before 0.62.1 shipped it in the ports root.
  PC_SKIP_PMFINISH=1 /bin/bash "$PORTS_DIR/PocketCuratorMetadataInstall.sh" >> "$LOGF" 2>&1
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
