#!/bin/bash
# ===========================================================================
# Pocket Curator - metadata installer (internal tool)
# ===========================================================================
# Writes Pocket Curator's own entry (name, description, artwork, video,
# rating, release date, etc.) into the Ports gamelist and refreshes
# EmulationStation so it shows up. Lives in pocketcurator/tools/ so it
# never appears as a launchable entry in EmulationStation's Ports menu.
#
# Invoked automatically - users never run this by hand:
#   - by PocketCurator.Installer.sh right after a fresh install
#   - by the launcher when the app reports its gamelist entry is
#     missing or incomplete (e.g. after a manual zip install)
#
# Never sets 'favorite' or any other user-preference flag - only the
# descriptive fields Pocket Curator owns.
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
# returned to its idle menu (past its game-exit flush). ES owns our
# <game> node while a port is running and rewrites it from RAM on the
# game-exit flush; the only moment a write sticks is when ES is idle at
# its menu. So we wait for that, write ONCE, and reload ONCE. The reload
# (disk->RAM) makes ES adopt our on-disk change; it cannot clobber it the
# way a RAM->disk flush would. Detached (setsid) so it survives our exit.
seq='
  sleep 8
  PC_API_OK=0
  if command -v timeout >/dev/null 2>&1; then
    timeout 30 "$PC_PYBIN" -u "$PC_HELPER" >/dev/null 2>&1
  else
    "$PC_PYBIN" -u "$PC_HELPER" >/dev/null 2>&1
  fi
  if command -v curl >/dev/null 2>&1; then
    if curl -s -m 8 http://localhost:1234/reloadgames >/dev/null 2>&1; then
      PC_API_OK=1
    fi
  fi
  # ArkOS family (incl. dArkOS) has no reloadgames API; the write above
  # landed on disk but the running ES will not show it (and could flush
  # a stale copy over it later). Queue one ES service restart so it
  # re-reads gamelists. --no-block hands the job to PID 1 and returns
  # immediately: we are inside the ES cgroup, so the restart kills this
  # very shell - the job must already be queued when that happens. This
  # is the last statement, so dying then is fine.
  if [ "$PC_API_OK" != "1" ] \
      && [ -f /etc/systemd/system/emulationstation.service ] \
      && command -v systemctl >/dev/null 2>&1; then
    if [ "$(id -u)" = "0" ]; then
      systemctl restart emulationstation --no-block
    else
      sudo -n systemctl restart emulationstation --no-block
    fi
  fi
'
if command -v setsid >/dev/null 2>&1; then
  PC_PYBIN="$PYBIN" PC_HELPER="$HELPER" PC_GAMELIST="$GAMELIST" setsid bash -c "$seq" >/dev/null 2>&1 &
else
  PC_PYBIN="$PYBIN" PC_HELPER="$HELPER" PC_GAMELIST="$GAMELIST" bash -c "$seq" >/dev/null 2>&1 &
  disown 2>/dev/null || true
fi

# When the launcher invokes us mid-exit it handles PortMaster cleanup
# itself; calling pm_finish twice double-kills gptokeyb harmlessly but
# noisily, so the launcher asks us to skip it.
[ -z "$PC_SKIP_PMFINISH" ] && pm_finish
exit 0

} # end RAM-load wrapper
