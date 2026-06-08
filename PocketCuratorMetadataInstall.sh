#!/bin/bash
# PORTMASTER: pocketcurator.zip, PocketCuratorMetadataInstall.sh
# ===========================================================================
# Pocket Curator - one-shot metadata installer
# ===========================================================================
# Writes Pocket Curator's own entry (name, description, artwork, video,
# rating, release date, etc.) into the Ports gamelist and refreshes
# EmulationStation so it shows up. Run this ONCE from the Ports menu.
# Afterwards you can delete it or keep it - it's harmless to leave.
#
# Why a separate, deferred script:
# EmulationStation rewrites the ports gamelist from its in-RAM copy every
# time you return from a "game" (a port counts), which clobbers any
# metadata written while a port is running. The only moment a write to an
# existing entry sticks is when ES is idle at its menu. So this script does
# NOT write immediately - it schedules the write + reload to run a few
# seconds AFTER it exits, once ES is back at its menu and past its
# game-exit gamelist flush. (This mirrors doing it by hand once ES is idle.)
# ===========================================================================

# Self-heal Windows line endings if they snuck in.
if LC_ALL=C grep -q $'\r' "$0" 2>/dev/null; then
    self_clean="$(dirname "$0")/.${0##*/}.lf"
    if tr -d '\r' < "$0" > "$self_clean" 2>/dev/null && [ -s "$self_clean" ]; then
        chmod +x "$self_clean" 2>/dev/null
        exec /bin/bash "$self_clean" "$@"
    fi
    echo "[PC-MetaInstall] FATAL: script has Windows line endings; cannot self-heal." >&2
    exit 1
fi

{ # force bash to load the whole script into RAM

shopt -s expand_aliases
XDG_DATA_HOME=${XDG_DATA_HOME:-$HOME/.local/share}
SCRIPT_DIR="$(dirname "$0")"

# Locate PortMaster.
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
  echo "[PC-MetaInstall] FATAL: no working PortMaster install found." >&2
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
type pm_finish  >/dev/null 2>&1 || pm_finish()  { :; }

get_controls 2>/dev/null || true

GAMEDIR="/$directory/ports/pocketcurator"
HELPER="$GAMEDIR/tools/write_ports_metadata.py"
GAMELIST="/$directory/ports/gamelist.xml"

if [ ! -f "$HELPER" ]; then
  pm_message "Pocket Curator isn't installed. Install Pocket Curator first, then run this."
  pm_finish
  exit 1
fi

# Find a system python3 (the helper only needs the standard library).
PYBIN=""
for cand in /usr/bin/python3 /usr/local/bin/python3 python3; do
  if command -v "$cand" >/dev/null 2>&1; then PYBIN="$cand"; break; fi
done
if [ -z "$PYBIN" ]; then
  pm_message "No system python3 found; cannot write metadata."
  pm_finish
  exit 1
fi

pm_message "Installing Pocket Curator metadata. Your Emulation Station gameslist will automatically refresh in a few seconds."

# Schedule the write + reload to run AFTER this script exits and ES has
# returned to its idle menu (past its game-exit flush). We wait, then
# write + reload, and stop as soon as our metadata is confirmed present -
# so a device where the first pass works gets exactly one refresh.
# Slower devices retry a few times. Detached (setsid) so it survives our
# exit. No restart - the reload is in-place.
seq='
  sleep 8
  for _i in 1 2 3 4 5; do
    "$PC_PYBIN" -u "$PC_HELPER" >/dev/null 2>&1
    if command -v curl >/dev/null 2>&1; then
      curl -s -m 8 http://localhost:1234/reloadgames >/dev/null 2>&1
    fi
    sleep 2
    # Stop once our metadata is present and (ES now idle) staying put.
    if grep -q "PocketCurator.mp4" "$PC_GAMELIST" 2>/dev/null; then
      break
    fi
    sleep 2
  done
'
if command -v setsid >/dev/null 2>&1; then
  PC_PYBIN="$PYBIN" PC_HELPER="$HELPER" PC_GAMELIST="$GAMELIST" setsid bash -c "$seq" >/dev/null 2>&1 &
else
  PC_PYBIN="$PYBIN" PC_HELPER="$HELPER" PC_GAMELIST="$GAMELIST" bash -c "$seq" >/dev/null 2>&1 &
  disown 2>/dev/null || true
fi

pm_finish
exit 0

} # end RAM-load wrapper
