#!/bin/bash
# PORTMASTER: pocketcurator.zip, Pocket Curator.sh v1.0.14
# ===========================================================================
# Pocket Curator launcher
# ===========================================================================
# Single-file launcher. Sources PortMaster's control.txt, downloads the
# Pyxel runtime on first launch if needed, mounts it, sets up the python
# environment, runs the app, cleans up.
# ===========================================================================

# Self-heal Windows line endings if they snuck in.
if LC_ALL=C grep -q $'\r' "$0" 2>/dev/null; then
    self_clean="$(dirname "$0")/.${0##*/}.lf"
    if tr -d '\r' < "$0" > "$self_clean" 2>/dev/null && [ -s "$self_clean" ]; then
        chmod +x "$self_clean" 2>/dev/null
        exec /bin/bash "$self_clean" "$@"
    fi
    echo "[Pocket Curator] FATAL: launcher has Windows line endings; cannot self-heal." >&2
    exit 1
fi

{ # Added by Tom to force bash to load this whole script into RAM

# Enable alias expansion BEFORE sourcing control.txt. PortMaster on Rocknix
# defines its pm_* helpers as aliases, and non-interactive bash doesn't
# expand aliases by default.
shopt -s expand_aliases

XDG_DATA_HOME=${XDG_DATA_HOME:-$HOME/.local/share}
SCRIPT_DIR="$(dirname "$0")"

# ===========================================================================
# Apply a staged update, if the in-app updater left one.
# ===========================================================================
# The updater downloads, verifies, and extracts the new release into
# pocketcurator/.update/staged/ and writes the READY flag LAST - so if
# READY exists, the staged tree is complete. We apply it here, at the
# very start of a launch, before any of our code is running.
#
# The actual file replacement runs from a helper copied to /tmp because
# this script is about to overwrite ITSELF, and bash reads scripts
# incrementally from disk. The helper finishes the swap and then execs
# the NEW launcher, so the user gets the new version this very session.
#
# Crash safety: payload first, the two launcher scripts last (each via
# copy-then-rename), and .update/ is removed only after everything
# succeeded. A power cut mid-apply leaves READY in place, so the apply
# simply re-runs on the next launch. The staged tree never contains
# settings.json (the updater prunes it), so user settings survive.
PC_UPDATE_DIR="$SCRIPT_DIR/pocketcurator/.update"
if [ -z "$PC_SKIP_UPDATE" ] && [ -f "$PC_UPDATE_DIR/READY" ] \
    && [ -f "$PC_UPDATE_DIR/staged/Pocket Curator.sh" ]; then
  PC_NEW_VER="$(cat "$PC_UPDATE_DIR/READY" 2>/dev/null)"
  echo "[Pocket Curator] applying staged update v${PC_NEW_VER}..."
  PC_APPLY="/tmp/pc_apply_update.$$.sh"
  cat > "$PC_APPLY" <<'PCAPPLY'
#!/bin/bash
# Pocket Curator update applier. Args: <ports_dir> <original args...>
PORTS="$1"; shift
GAME="$PORTS/pocketcurator"
STAGED="$GAME/.update/staged"
LOGF="$GAME/update.log"
log() { echo "[pc-update] $*"; echo "$(date '+%F %T') $*" >> "$LOGF" 2>/dev/null; }

fail() {
  log "FAILED: $*"
  log "update left staged; will retry next launch"
  # Run whatever launcher is on disk, but don't loop into another apply.
  PC_SKIP_UPDATE=1 exec /bin/bash "$PORTS/Pocket Curator.sh" "$@"
}

log "applying $(cat "$GAME/.update/READY" 2>/dev/null)"

# 1. Payload (everything under pocketcurator/). Runtime files we don't
#    ship (conf/, logs, flags, settings.json) are untouched by -a copy.
cp -a "$STAGED/pocketcurator/." "$GAME/" || fail "payload copy"

# 2. Scripts in the ports root, each copy-then-rename so the swap of
#    each file is atomic. (Releases since 0.62.1 ship only the
#    launcher here; the [ -f ] guard keeps this compatible both ways.)
for f in "Pocket Curator.sh" "PocketCuratorMetadataInstall.sh"; do
  if [ -f "$STAGED/$f" ]; then
    cp "$STAGED/$f" "$PORTS/.$f.new" || fail "stage $f"
    chmod +x "$PORTS/.$f.new" 2>/dev/null
    mv -f "$PORTS/.$f.new" "$PORTS/$f" || fail "swap $f"
  fi
done
# Pre-0.62.1 installs had the metadata installer in the ports root,
# where EmulationStation lists it as a launchable entry. It lives in
# pocketcurator/tools/ now - remove the stray so the menu decluttering
# actually reaches updated installs.
if [ ! -f "$STAGED/PocketCuratorMetadataInstall.sh" ]; then
  rm -f "$PORTS/PocketCuratorMetadataInstall.sh"
fi

# 3. Only now is the update 'done'.
rm -rf "$GAME/.update"
sync 2>/dev/null
log "applied OK; relaunching"
PC_UPDATE_JUST_APPLIED=1 exec /bin/bash "$PORTS/Pocket Curator.sh" "$@"
PCAPPLY
  chmod +x "$PC_APPLY"
  exec /bin/bash "$PC_APPLY" "$SCRIPT_DIR" "$@"
fi
if [ -n "$PC_UPDATE_JUST_APPLIED" ]; then
  echo "[Pocket Curator] update applied successfully"
fi

# Locate PortMaster. Test for control.txt itself so a broken PM install
# doesn't win the check.
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
  echo "[Pocket Curator] FATAL: no working PortMaster install found." >&2
  echo "[Pocket Curator] Please install or reinstall PortMaster from https://portmaster.games/" >&2
  exit 1
fi

source "$controlfolder/control.txt"

# Source the firmware-specific mod file if present. Lowercase the name
# because Rocknix sets CFW_NAME=ROCKNIX but ships mod_rocknix.txt.
cfw_lower="$(echo "$CFW_NAME" | tr '[:upper:]' '[:lower:]')"
if [ -f "${controlfolder}/mod_${cfw_lower}.txt" ]; then
  source "${controlfolder}/mod_${cfw_lower}.txt"
elif [ -f "${controlfolder}/mod_${CFW_NAME}.txt" ]; then
  source "${controlfolder}/mod_${CFW_NAME}.txt"
fi

# Fallback pm_message stub for firmwares that don't ship one.
type pm_message >/dev/null 2>&1 || pm_message() { echo "[pm_message] $*"; }

if [ -z "$CFW_NAME" ] || [ -z "$DEVICE_ARCH" ]; then
  echo "[Pocket Curator] FATAL: control.txt sourced but CFW_NAME/DEVICE_ARCH unset." >&2
  exit 1
fi

# Pass PortMaster's authoritative firmware name to the app. The Python
# side's filesystem-marker detection is unreliable across devices (some
# Knulli builds lack /etc/knulli-release etc.), so prefer this.
export POCKETCURATOR_CFW="$CFW_NAME"

get_controls

GAMEDIR="/$directory/ports/pocketcurator"
CONFDIR="$GAMEDIR/conf"
mkdir -p "$CONFDIR"
cd "$GAMEDIR" || exit 1

# Fresh log every launch.
> "$GAMEDIR/pocketcurator.log" && exec > >(tee "$GAMEDIR/pocketcurator.log") 2>&1

# Launcher-phase timing. $SECONDS counts from shell start, so these
# lines bracket everything the in-app [timing] marks can't see: the
# update apply, runtime mount, python boots, and SDL probing. A slow
# first launch should now be attributable from the log alone.
pc_stage() { echo "[Pocket Curator +${SECONDS}s] $1"; }
pc_stage "launcher log started"
if [ -n "$PC_UPDATE_JUST_APPLIED" ]; then
  pc_stage "an update was applied at the start of this launch (see update.log)"
fi

# The one-file installer leaves its log in the ports root, where the
# user trips over it. Adopt it into our folder on first launch.
if [ -f "$SCRIPT_DIR/pocketcurator_install.log" ]; then
  mv -f "$SCRIPT_DIR/pocketcurator_install.log" "$GAMEDIR/install.log" 2>/dev/null \
    && pc_stage "moved installer log into pocketcurator/install.log"
fi

APP_VERSION=$(grep '^__version__' "$GAMEDIR/curator/__init__.py" | sed -E 's/.*"([^"]+)".*/\1/')
APP_BUILD=$(grep '^__build__'   "$GAMEDIR/curator/__init__.py" | sed -E 's/.*"([^"]+)".*/\1/')

echo "=========================================="
echo "  Pocket Curator v${APP_VERSION} (build ${APP_BUILD})"
echo "=========================================="
echo "[Pocket Curator] running on $CFW_NAME / $DEVICE_ARCH"
echo "[Pocket Curator] launcher: $0"
echo "[Pocket Curator] launcher mtime: $(stat -c '%y' "$0" 2>/dev/null)"
echo "[Pocket Curator] PID $$"

# Kill any stale gptokeyb from a previous crashed run.
$ESUDO kill -9 $(pidof gptokeyb 2>/dev/null) 2>/dev/null
$ESUDO kill -9 $(pidof gptokeyb2 2>/dev/null) 2>/dev/null
sleep 0.2

# ===========================================================================
# Set up the Python runtime
# ===========================================================================
if [[ "${CFW_NAME,,}" == "knulli" || "${CFW_NAME,,}" == "batocera" ]]; then
  # Knulli/Batocera ship a system Python AND their own pygame, built
  # against their specific SDL (which has Mali/KMS drivers compiled in
  # for these handheld GPUs). Their pygame works with their display
  # out of the box. Our bundled Pyxel runtime's SDL is a generic Linux
  # build and lacks the Mali driver, so falling back to Pyxel on these
  # firmwares produces a black screen even though pygame technically
  # loads. Always prefer system pygame on Knulli/Batocera.
  #
  # We test by actually importing pygame, which catches both "no
  # python3" and "python3 but no pygame" cases in one shot.
  candidate_py="$(command -v python3)"
  if [ -n "$candidate_py" ] && "$candidate_py" -c "import pygame" >/dev/null 2>&1; then
    sys_py_ver=$("$candidate_py" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null)
    sys_pg_ver=$("$candidate_py" -c "import pygame; print(pygame.version.ver)" 2>/dev/null)
    sys_sdl_ver=$("$candidate_py" -c "import pygame; print('.'.join(str(x) for x in pygame.version.SDL))" 2>/dev/null)
    echo "[Pocket Curator] system python: $candidate_py (Python $sys_py_ver)"
    echo "[Pocket Curator] system pygame: $sys_pg_ver (SDL $sys_sdl_ver) - has Mali/KMS support on Knulli"
    USE_SYSTEM_PYTHON=1
    PYTHON_BIN="$candidate_py"
    unset PYTHONHOME
    py_dir=""
  else
    if [ -z "$candidate_py" ]; then
      echo "[Pocket Curator] no system python3 found; falling back to bundled Pyxel runtime"
    else
      echo "[Pocket Curator] system python found but pygame not importable; falling back to bundled Pyxel"
    fi
    USE_SYSTEM_PYTHON=0
  fi
else
  USE_SYSTEM_PYTHON=0
fi

# Gamepad-as-keyboard translation default. OFF for every firmware -
# gptokeyb's keyboard reaches SDL on all of them EXCEPT our own pcSDL
# kmsdrm path on AmberELEC, which flips this to 1 after the probe. This
# default must be set for ALL launch paths (the system-python branch
# used by Knulli/Batocera never enters the probe block, so without an
# early default it fell back to the app's driver heuristic and doubled
# every input).
export PC_PAD_INPUT=0

if [ "$USE_SYSTEM_PYTHON" = "0" ]; then
  pc_stage "runtime ready"
  echo "[Pocket Curator] using bundled Pyxel runtime"
  runtime="pyxel_2.2.8_python_3.11"
  runtime_file="$controlfolder/libs/${runtime}.squashfs"

  if [ ! -f "$runtime_file" ]; then
    if [ ! -f "$controlfolder/harbourmaster" ]; then
      pm_message "Pocket Curator requires the latest PortMaster. Please update via https://portmaster.games/"
      sleep 5
      pm_finish
      exit 1
    fi
    n=0
	# Tom changed the number of retries to 4 from 3 and increased the wait time from 3 to 5 seconds between tries
	# to give the handheld a longer time to wake-up and get good internet connectivity
    while [ $n -lt 4 ] && [ ! -f "$runtime_file" ]; do
      n=$((n+1))
      if [ $n -eq 1 ]; then
        echo "[Pocket Curator] fetching Python 3.11 runtime (attempt 1 of 4)..."
      else
        echo "[Pocket Curator] previous attempt failed; retrying (attempt $n of 4)..."
        sleep 5
      fi
      $ESUDO "$controlfolder/harbourmaster" --quiet --no-check runtime_check "${runtime}.squashfs"
    done
    if [ ! -f "$runtime_file" ]; then
      pm_message "Pocket Curator: runtime download failed. Network or GitHub CDN issue."
      sleep 3
      pm_finish
      exit 1
    fi
    echo "[Pocket Curator] runtime downloaded; syncing"
    sync
  fi

  py_dir="$HOME/pyxel"
  $ESUDO mkdir -p "$py_dir"
  if [[ "$PM_CAN_MOUNT" != "N" ]]; then
    $ESUDO umount "$py_dir" 2>/dev/null || true
    $ESUDO mount "$runtime_file" "$py_dir"
  fi
  source "$py_dir/bin/activate"
  export PYTHONHOME="$py_dir"
  export PYTHONPYCACHEPREFIX="/tmp/pocketcurator_pycache"
  PYTHON_BIN="$py_dir/bin/python3"
fi

if [ "$USE_SYSTEM_PYTHON" = "1" ]; then
  # System pygame is on Knulli's default sys.path; we only need our app
  # code findable. Putting libs.aarch64 in front would shadow system
  # pygame with our incompatible cpython-311 wheels.
  export PYTHONPATH="$GAMEDIR:${PYTHONPATH:-}"
else
  # Pyxel runtime: our bundled pygame wheels must be found first.
  export PYTHONPATH="$GAMEDIR/libs.${DEVICE_ARCH}:$GAMEDIR:${PYTHONPATH:-}"
fi
PC_ORIG_LD_LIBRARY_PATH="${LD_LIBRARY_PATH:-}"
if [ "$USE_SYSTEM_PYTHON" = "1" ]; then
  # System pygame resolves its own deps via system paths. Don't inject
  # our bundled libs - this matches the working v0.16-v0.26 config.
  export LD_LIBRARY_PATH="/usr/lib/compat/:${LD_LIBRARY_PATH:-}"
else
  export LD_LIBRARY_PATH="$GAMEDIR/libs.${DEVICE_ARCH}:/usr/lib/compat/:${LD_LIBRARY_PATH:-}"
fi
if [ "$USE_SYSTEM_PYTHON" = "1" ]; then
  # On Knulli/Batocera, system pygame already knows how to talk to the
  # device's display (Mali GPU, KMS, etc). Forcing a driver here breaks
  # what otherwise works out of the box. The old working v0.16-v0.26
  # logs explicitly showed "SDL_VIDEODRIVER=(let system pick)" - we're
  # restoring that.
  unset SDL_VIDEODRIVER
else
  # Pyxel runtime path (Rocknix etc): help SDL find the Wayland session.
  export SDL_VIDEODRIVER="${SDL_VIDEODRIVER:-wayland}"
fi

echo "[Pocket Curator] PYTHONHOME=${PYTHONHOME:-(unset)}"
echo "[Pocket Curator] PYTHONPATH=$PYTHONPATH"
echo "[Pocket Curator] LD_LIBRARY_PATH=$LD_LIBRARY_PATH"
echo "[Pocket Curator] PYTHON_BIN=$PYTHON_BIN"
echo "[Pocket Curator] SDL_VIDEODRIVER=$SDL_VIDEODRIVER"
echo "[Pocket Curator] WAYLAND_DISPLAY=${WAYLAND_DISPLAY:-(unset)}"
echo "[Pocket Curator] XDG_RUNTIME_DIR=${XDG_RUNTIME_DIR:-(unset)}"
echo "[Pocket Curator] python prefix = $($PYTHON_BIN -c 'import sys; print(sys.prefix)' 2>/dev/null)"
echo "[Pocket Curator] python stdlib found: $($PYTHON_BIN -c 'import os; print(True)' 2>/dev/null)"

# Display-probe cache: once a driver combo works on this firmware +
# device, remember it and try it first next launch - and skip the
# standalone pygame import test, since the cached probe's preflight
# proves the same thing with one less Python boot (~3-6s on slow SD).
PC_PROBE_CACHE="$GAMEDIR/conf/display_probe.cache"
PC_PROBE_KEY="${CFW_NAME}|${DEVICE_NAME:-?}"
PC_CACHED_LINE=""
if [ -f "$PC_PROBE_CACHE" ]; then
  cached="$(cat "$PC_PROBE_CACHE" 2>/dev/null)"
  if [ "${cached%%::*}" = "$PC_PROBE_KEY" ]; then
    PC_CACHED_LINE="${cached#*::}"
    echo "[Pocket Curator] probe cache hit for $PC_PROBE_KEY: $PC_CACHED_LINE"
  else
    echo "[Pocket Curator] probe cache is for different hardware; ignoring"
  fi
fi

if [ -n "$PC_CACHED_LINE" ] && [ "$USE_SYSTEM_PYTHON" != "1" ]; then
  echo "[Pocket Curator] skipping pygame import test (cached probe will verify the runtime)"
elif true; then
echo "[Pocket Curator] testing pygame import..."
pc_stage "python boot + pygame import test starting (first run after an update recompiles bytecode here)"
if ! "$PYTHON_BIN" -c "import pygame; print('[Pocket Curator] pygame', pygame.version.ver, 'loaded OK')"; then
  pm_message "Pocket Curator: pygame failed to import. Check pocketcurator.log."
  sleep 10
  if [ "$USE_SYSTEM_PYTHON" != "1" ] && [[ "$PM_CAN_MOUNT" != "N" ]]; then
    $ESUDO umount "$py_dir" 2>/dev/null || true
  fi
  pm_finish
  exit 1
fi
fi

# Gamepad -> keyboard mapping. Knulli/Batocera use the opposite A/B
# X/Y convention from Rocknix at the gamepad layer; the user-facing
# legend in the app stays identical because the swap happens here.
case "${CFW_NAME,,}" in
  knulli|batocera) GPTK_FILE="$GAMEDIR/pocketcurator-knulli.gptk" ;;
  *)               GPTK_FILE="$GAMEDIR/pocketcurator.gptk" ;;
esac
echo "[Pocket Curator] using gptk: $GPTK_FILE"

# --- controller diagnostics ---------------------------------------------
# ES and gptokeyb use different input stacks: ES reads its own input config,
# gptokeyb maps via the SDL gamecontroller mapping below. If a device's SDL
# mapping puts A/B in a different order than another unit, ports feel swapped
# while ES is fine. Logging the live mapping lets us compare units (e.g. an
# RG40xxH that feels swapped vs an RG40xxV that doesn't) without guessing.
echo "[Pocket Curator] --- controller diag ---"
echo "[Pocket Curator] CFW=$CFW_NAME DEVICE_NAME=${DEVICE_NAME:-?} ARCH=$DEVICE_ARCH"
echo "[Pocket Curator] GPTOKEYB=${GPTOKEYB:-?}"
if [ -n "${sdl_controllerconfig:-}" ]; then
  echo "[Pocket Curator] SDL face-button map (a/b/x/y) for each controller:"
  printf '%s\n' "$sdl_controllerconfig" | tr ',' '\n' \
    | grep -E '^(platform|guid|[abxy]):' | sed 's/^/[Pocket Curator]   /'
  # Hand the device's own SDL gamecontroller mapping to the app, so
  # pygame's GameController API labels A/B/X/Y and the d-pad correctly
  # regardless of the pad's raw evdev button/axis order. This is what
  # makes the kmsdrm joystick-translation path map buttons right on
  # devices like the RG552 (GO-Super Gamepad).
  export SDL_GAMECONTROLLERCONFIG="$sdl_controllerconfig"
else
  echo "[Pocket Curator] sdl_controllerconfig is unset"
fi
if [ -r /proc/bus/input/devices ]; then
  echo "[Pocket Curator] kernel input device names:"
  grep -E '^N: ' /proc/bus/input/devices | sed 's/^/[Pocket Curator]   /'
fi
echo "[Pocket Curator] --- end controller diag ---"

$GPTOKEYB "python3" -c "$GPTK_FILE" &
GPTK_PID=$!

# Release the display BEFORE probing. On AmberELEC (and any firmware
# whose ES holds DRM master while a port launches), probing kmsdrm with
# ES still owning the display fails every real driver and the old code
# fell through to a headless dummy run - a black screen with the app
# invisibly alive (RG552, v0.62.2/v0.63.0). The release used to happen
# after the probes; that ordering was lost in a launcher reconstruction.
if type pm_platform_helper >/dev/null 2>&1; then
  echo "[Pocket Curator] calling pm_platform_helper to release display (pre-probe)"
  pm_platform_helper
fi

# SDL driver probe for bundled-Pyxel path.
if [ "$USE_SYSTEM_PYTHON" != "1" ]; then
  echo "[Pocket Curator] ==== probing SDL2 video drivers ===="
  SYS_SDL2=""
  for cand in /usr/lib/aarch64-linux-gnu/libSDL2-2.0.so.0 /usr/lib/libSDL2-2.0.so.0 \
              /lib/aarch64-linux-gnu/libSDL2-2.0.so.0 /lib/libSDL2-2.0.so.0; do
    if [ -f "$cand" ]; then
      SYS_SDL2="$cand"
      echo "[Pocket Curator] system libSDL2 found at: $SYS_SDL2"
      break
    fi
  done
  if [ -z "$SYS_SDL2" ]; then
    echo "[Pocket Curator] no system libSDL2 found; will only try bundled SDL"
  fi
  # Probe order, two principles:
  #   1. The firmware name tells us what almost certainly works - try
  #      that FIRST instead of marching through the whole ladder:
  #        ROCKNIX -> wayland; dArkOS -> kmsdrm+sysSDL (system SDL
  #        2.32.10 carries the platform display support); AmberELEC ->
  #        bundled kmsdrm (its system SDL 2.26.2 is a version downgrade
  #        vs bundled 2.28.4 and gets rejected on preload).
  #   2. A cached previous success (this firmware + device) outranks
  #      even the firmware default, and is attempted before anything.
  # The full ladder remains behind both as the safety net.
  probe_attempts=(
    "wayland|wayland|"
    "wayland+sysSDL|wayland|LD_PRELOAD=$SYS_SDL2"
    "kmsdrm|kmsdrm|"
    "kmsdrm+sysSDL|kmsdrm|LD_PRELOAD=$SYS_SDL2"
    "x11|x11|"
    "x11+sysSDL|x11|LD_PRELOAD=$SYS_SDL2"
  )
  case "${CFW_NAME,,}" in
    rocknix|jelos)
      preferred="wayland|wayland|" ;;
    darkos|arkos)
      preferred="kmsdrm+sysSDL|kmsdrm|LD_PRELOAD=$SYS_SDL2" ;;
    amberelec)
      if [ -f "$GAMEDIR/pocketcurator/libs.aarch64/pcsdl/libSDL2-2.0.so.0" ]; then
        preferred="kmsdrm+pcSDL|kmsdrm|LD_PRELOAD=$GAMEDIR/pocketcurator/libs.aarch64/pcsdl/libSDL2-2.0.so.0"
      elif [ -f "$GAMEDIR/libs.aarch64/pcsdl/libSDL2-2.0.so.0" ]; then
        preferred="kmsdrm+pcSDL|kmsdrm|LD_PRELOAD=$GAMEDIR/libs.aarch64/pcsdl/libSDL2-2.0.so.0"
      else
        preferred="kmsdrm|kmsdrm|"
      fi ;;
    *)
      preferred="" ;;
  esac
  # PortMaster-shipped SDL builds (newer than 2.28.4, kmsdrm-capable)
  # as additional preload candidates. The v0.63.1 AmberELEC log proved
  # the bundled pygame SDL simply has no kmsdrm driver and the system
  # SDL (2.26.2) is rejected as a downgrade - a PortMaster SDL is the
  # remaining path to a real display there.
  pm_sdl_count=0
  for pmsdl in $(find "$controlfolder" /roms/ports/PortMaster \
                      /opt/system/Tools/PortMaster \
                      -maxdepth 4 -name 'libSDL2-2.0.so*' -type f \
                      2>/dev/null | sort -u); do
    [ -f "$pmsdl" ] || continue
    [ "$pmsdl" = "$SYS_SDL2" ] && continue
    pm_sdl_count=$((pm_sdl_count + 1))
    echo "[Pocket Curator] PortMaster SDL found: $pmsdl (probe candidate)"
    probe_attempts+=("kmsdrm+pmSDL${pm_sdl_count}|kmsdrm|LD_PRELOAD=$pmsdl")
  done
  # The Pyxel runtime ships its OWN pygame, built by PortMaster for
  # these devices - and we normally shadow it with our bundled copy via
  # PYTHONPATH. Where our bundled pygame's SDL lacks kmsdrm (AmberELEC),
  # the runtime's own build may have it: probe with our libs.aarch64
  # dropped from PYTHONPATH so the runtime pygame loads instead.
  probe_attempts+=("kmsdrm+runtimePygame|kmsdrm|PYTHONPATH=$GAMEDIR")
  probe_attempts+=("x11+runtimePygame|x11|PYTHONPATH=$GAMEDIR")
  # Our own SDL build (libs.aarch64/pcsdl): 2.28.4 with KMSDRM in
  # dlopen mode - the answer for firmwares whose system SDL is too old
  # to preload (AmberELEC) while the pygame wheel's SDL has no kmsdrm.
  PC_SDL="$GAMEDIR/pocketcurator/libs.aarch64/pcsdl/libSDL2-2.0.so.0"
  [ -f "$PC_SDL" ] || PC_SDL="$GAMEDIR/libs.aarch64/pcsdl/libSDL2-2.0.so.0"
  if [ -f "$PC_SDL" ]; then
    probe_attempts+=("kmsdrm+pcSDL|kmsdrm|LD_PRELOAD=$PC_SDL")
  fi
  if [ -n "$preferred" ]; then
    probe_attempts=("$preferred" "${probe_attempts[@]}")
  fi
  if [ -n "$PC_CACHED_LINE" ]; then
    probe_attempts=("$PC_CACHED_LINE" "${probe_attempts[@]}")
  fi
  WORKING_DRIVER=""
  WORKING_ENV=""
  tried=""
  for attempt in "${probe_attempts[@]}"; do
    case "$tried" in *"|$attempt|"*) continue ;; esac
    tried="$tried|$attempt|"
    IFS='|' read -r label drv envkv <<< "$attempt"
    if [ -n "$envkv" ] && [[ "$envkv" == *"="* ]]; then
      envval="${envkv#*=}"
      [ -z "$envval" ] && continue
    fi
    echo "[Pocket Curator] -- probe $label (driver=$drv, env=${envkv:-none}) --"
    extra=""
    [ -n "$envkv" ] && extra="$envkv"
    env $extra SDL_VIDEODRIVER="$drv" "$PYTHON_BIN" -u "$GAMEDIR/preflight.py"
    rc=$?
    echo "[Pocket Curator] -- probe $label exit $rc --"
    if [ "$rc" = "0" ]; then
      WORKING_DRIVER="$drv"
      WORKING_ENV="$envkv"
      mkdir -p "$GAMEDIR/conf" 2>/dev/null
      printf '%s::%s\n' "$PC_PROBE_KEY" "$attempt" > "$PC_PROBE_CACHE" 2>/dev/null \
        && echo "[Pocket Curator] cached working probe '$label' for $PC_PROBE_KEY"
      break
    fi
  done
  # No dummy fallback anymore. A headless run is a black screen with an
  # invisible app eating input (RG552 ran 72s like that) - strictly
  # worse than telling the user and returning to ES.
  pc_stage "display probe complete"
  echo "[Pocket Curator] ==== probe complete: driver='${WORKING_DRIVER:-NONE}' env='${WORKING_ENV:-none}' ===="
  if [ -z "$WORKING_DRIVER" ]; then
    rm -f "$PC_PROBE_CACHE" 2>/dev/null
    # pm_message runs PortMaster's own Python UI - it must NOT inherit
    # our bundled-runtime environment (v0.63.1: pugwash died on a
    # missing libffi.so.7 and the device wedged instead of returning
    # to ES).
    unset PYTHONHOME PYTHONPATH PYTHONPYCACHEPREFIX SDL_VIDEODRIVER LD_PRELOAD
    export LD_LIBRARY_PATH="$PC_ORIG_LD_LIBRARY_PATH"
    kill -9 "$GPTK_PID" 2>/dev/null || true
    wait "$GPTK_PID" 2>/dev/null
    $ESUDO pkill -9 -f '[g]ptokeyb' 2>/dev/null || true
    if [[ "$PM_CAN_MOUNT" != "N" ]]; then
      $ESUDO umount "$py_dir" 2>/dev/null || true
    fi
    pm_message "Pocket Curator: no working display driver on this firmware. Returning to EmulationStation. (Details in pocketcurator.log)"
    sleep 3
    pm_finish
    exit 1
  fi
  export SDL_VIDEODRIVER="$WORKING_DRIVER"
  if [ -n "$WORKING_ENV" ]; then
    export $WORKING_ENV
  fi
  # Gamepad-as-keyboard translation is needed ONLY where SDL can't see
  # gptokeyb's keyboard - i.e. our own pcSDL kmsdrm path (AmberELEC),
  # where the app owns no TTY and there's no compositor. On every other
  # firmware (Knulli/ROCKNIX via wayland, dArkOS via system-SDL kmsdrm)
  # gptokeyb's keys DO reach SDL, so the translation would DOUBLE every
  # input. Gate it on the pcSDL preload, which only AmberELEC uses.
  case "${WORKING_ENV:-}" in
    *pcsdl*) export PC_PAD_INPUT=1 ;;  # AmberELEC: SDL can't see the keyboard
  esac
  pc_stage "launching the app"
# Display rotation override (0/90/180/270). Unset = the app auto-rotates
# a portrait framebuffer (e.g. the RG552's 1152x1920 panel) to landscape.
# Add a device quirk here if a panel needs a specific angle.
case "${CFW_NAME}|${DEVICE_NAME:-?}" in
  *RG552*) export PC_ROTATE="${PC_ROTATE:-270}" ;;
esac
echo "[Pocket Curator] running with SDL_VIDEODRIVER=$SDL_VIDEODRIVER extra_env='${WORKING_ENV:-none}'"
fi

# Dismiss the PortMaster loading dialog and signal that we're ready to
# take over the display. This is REQUIRED on Knulli/Batocera where ES
# renders directly to KMS/DRM with no compositor - without this call,
# PM's dialog stays on the framebuffer and our pygame app renders to a
# surface that isn't visible. On Rocknix (sway-based) it's less critical
# because multiple Wayland clients can coexist, but calling it is still
# the correct thing to do. Other firmwares may not define the function
# at all, so we type-check first.
# Restart EmulationStation so it re-reads gamelist.xml from disk. ES
# Refresh EmulationStation so it reflects our gamelist changes (deleted
# games dropped; our Ports metadata shown).
#
# PRIMARY PATH - in-place reload, no restart:
#   write the metadata (ES may be running; that's fine here), then ask
#   the running ES to re-read its gamelists from disk via its local HTTP
#   API: curl http://localhost:1234/reloadgames. A reload is disk->RAM,
#   so it adopts our on-disk changes and cannot clobber them the way a
#   restart's RAM->disk flush does. Confirmed working on ROCKNIX, and it
#   is exactly what PortMaster uses on Batocera (so it should work on
#   Knulli too, both being Batocera-based).
#
# FALLBACK - only if the reload API is unreachable: a per-firmware ES
# restart, so we never regress on a device without the API.

_pc_syspython() {
  # Echo a guaranteed-present system python3. Never $PYTHON_BIN (which on
  # Rocknix is the bundled Pyxel runtime, unmounted before refresh runs).
  local cand
  for cand in /usr/bin/python3 /usr/local/bin/python3 python3; do
    if command -v "$cand" >/dev/null 2>&1; then echo "$cand"; return 0; fi
  done
  return 1
}

_pc_reload_via_api() {
  # Ask the running ES to reload gamelists from disk. Returns 0 on success.
  command -v curl >/dev/null 2>&1 || return 1
  curl -s -m 8 http://localhost:1234/reloadgames >/dev/null 2>&1
}

_pc_fallback_restart() {
  # No reload API reachable. Restart ES per firmware so at least
  # deletions are picked up. $1 is the refresh reason; when it includes
  # metadata we re-write during the ES-down window on Batocera-family so
  # the restart's flush doesn't drop it. (This path only runs if the
  # reload API is missing - on Rocknix/Batocera it normally isn't.)
  local reason="$1"
  case "${CFW_NAME,,}" in
    rocknix|jelos|amberelec)
      if command -v systemctl >/dev/null 2>&1; then
        echo "[Pocket Curator] fallback: systemctl restart ${UI_SERVICE:-emustation}"
        $ESUDO systemctl restart oga_events 2>/dev/null &
        $ESUDO systemctl restart "${UI_SERVICE:-emustation}" 2>/dev/null \
          || $ESUDO systemctl restart emustation 2>/dev/null \
          || $ESUDO systemctl restart emulationstation 2>/dev/null
      fi
      ;;
    knulli|batocera)
      local initscript="/etc/init.d/S31emulationstation"
      if [ ! -x "$initscript" ]; then
        echo "[Pocket Curator] fallback unavailable ($initscript missing); skipping"
        return
      fi
      case "$reason" in
        metadata|both)
          # stop -> re-write metadata while down (survives the flush) -> start
          echo "[Pocket Curator] fallback: init.d stop -> write -> start"
          local helper="$GAMEDIR/tools/write_ports_metadata.py"
          local seq='
            sleep 2
            "$PC_INIT" stop
            i=0; while [ "$i" -lt 40 ]; do pgrep -f -n emulationstation >/dev/null 2>&1 || break; sleep 0.25; i=$((i+1)); done
            "$PC_PYBIN" -u "$PC_HELPER"
            "$PC_INIT" start
          '
          if command -v setsid >/dev/null 2>&1; then
            PC_INIT="$initscript" PC_PYBIN="$(_pc_syspython)" PC_HELPER="$helper" setsid bash -c "$seq" >/dev/null 2>&1 &
          else
            PC_INIT="$initscript" PC_PYBIN="$(_pc_syspython)" PC_HELPER="$helper" bash -c "$seq" >/dev/null 2>&1 &
            disown 2>/dev/null || true
          fi
          ;;
        *)
          # deletions only - just cycle ES so it re-scans; no write.
          echo "[Pocket Curator] fallback: init.d restart (deletions)"
          local seq='sleep 2; "$PC_INIT" stop; i=0; while [ "$i" -lt 40 ]; do pgrep -f -n emulationstation >/dev/null 2>&1 || break; sleep 0.25; i=$((i+1)); done; "$PC_INIT" start'
          if command -v setsid >/dev/null 2>&1; then
            PC_INIT="$initscript" setsid bash -c "$seq" >/dev/null 2>&1 &
          else
            PC_INIT="$initscript" bash -c "$seq" >/dev/null 2>&1 &
            disown 2>/dev/null || true
          fi
          ;;
      esac
      ;;
    arkos*|darkos*)
      # ArkOS family (incl. dArkOS on R36S). ES runs as a systemd service
      # (/etc/systemd/system/emulationstation.service) whose wrapper script
      # ALSO implements the RetroPie /tmp/es-restart sentinel loop. Two
      # traps shape this code:
      #
      #   1. We are a descendant of that service, so we live in its cgroup.
      #      'systemctl stop/restart' SIGTERMs the whole cgroup - us
      #      included. A stop -> write -> start sequence forked the normal
      #      way (even setsid'd) dies at its own 'stop' and strands the
      #      device on a black screen with ES down. systemd-run launches
      #      the sequence as a transient unit OUTSIDE our cgroup, so it
      #      survives the stop it issues.
      #
      #   2. (the v0.61.11 hang) ES must never be killed while the app is
      #      still running: the app holds DRM master on the kmsdrm display,
      #      and the wrapper's while-true loop relaunches ES instantly into
      #      a display it cannot acquire. By the time this function runs
      #      the app has exited and torn down SDL, so a restart is safe.
      #
      # Restart (not in-place reload) also re-reads gamelists from disk,
      # which is the whole point: dArkOS has no localhost:1234 API.
      local pc_sudo=""
      [ "$(id -u)" != "0" ] && pc_sudo="sudo -n"
      if command -v systemctl >/dev/null 2>&1 \
          && [ -f /etc/systemd/system/emulationstation.service ] \
          && { [ -z "$pc_sudo" ] || $pc_sudo true 2>/dev/null; }; then
        local writestep=':'
        case "$reason" in
          metadata|both)
            # Same hazard as Batocera: ES's clean quit flushes any dirty
            # in-RAM gamelist (e.g. ports, after our own lastplayed bump)
            # over our on-disk write. So write DURING the down window.
            # 'systemctl stop' is synchronous - when it returns, ES is
            # fully down; no pgrep polling needed.
            writestep='"$PC_PYBIN" -u "$PC_HELPER"'
            ;;
        esac
        local seq='
          sleep 3
          # ES SIGTERM handling only happens in its main UI loop, which is
          # suspended while ES waits on a launched port. If the TERM lands
          # in that window, systemd waits out TimeoutStopSec (default 90s!)
          # before SIGKILLing - the user sees a frozen "Refreshing" screen.
          # So: give ES a moment to return to its loop (sleep 3), run the
          # stop in the background, and if it has not completed within 5s,
          # SIGKILL the unit. That completes the in-flight stop job
          # immediately, and because it is an intentional stop,
          # Restart=on-failure does not re-trigger. SIGKILL is also safer
          # for us: ES cannot flush a stale in-RAM gamelist over our edits.
          systemctl stop emulationstation &
          pc_stop=$!
          i=0
          while kill -0 "$pc_stop" 2>/dev/null && [ "$i" -lt 20 ]; do
            sleep 0.25; i=$((i+1))
          done
          if kill -0 "$pc_stop" 2>/dev/null; then
            systemctl kill -s SIGKILL emulationstation 2>/dev/null
          fi
          wait "$pc_stop" 2>/dev/null
          '"$writestep"'
          systemctl start emulationstation
        '
        if command -v systemd-run >/dev/null 2>&1; then
          echo "[Pocket Curator] fallback: systemd-run ES stop -> ($reason) -> start"
          if $pc_sudo systemd-run --quiet --collect \
               --setenv=PC_PYBIN="$(_pc_syspython)" \
               --setenv=PC_HELPER="$GAMEDIR/tools/write_ports_metadata.py" \
               /bin/bash -c "$seq"; then
            return
          fi
          echo "[Pocket Curator] systemd-run failed; queueing plain restart"
        fi
        # No systemd-run (or it failed): queue a plain restart. --no-block
        # hands the job to PID 1 and returns immediately, so the SIGTERM
        # sweep that follows can't strand the job half-done when it kills
        # us. (Skips the metadata re-write, but never leaves ES down.)
        $pc_sudo systemctl restart emulationstation --no-block 2>/dev/null && return
        echo "[Pocket Curator] systemctl restart failed; trying sentinel"
      fi
      # Last resort (no usable systemd / no passwordless sudo): the
      # wrapper's native RetroPie convention - flag /tmp/es-restart, then
      # make the ES *binary* exit; the wrapper loop relaunches it and ES
      # re-reads gamelists from disk. Safe now for the same reason as
      # above: the display is already released. pgrep -f matches both the
      # wrapper (.sh) and the binary, so filter by /proc/PID/exe.
      echo "[Pocket Curator] fallback: /tmp/es-restart sentinel"
      touch /tmp/es-restart 2>/dev/null || true
      local es_pid="" p
      for p in $(pgrep -f 'emulationstation/emulationstation' 2>/dev/null); do
        case "$(readlink "/proc/$p/exe" 2>/dev/null)" in
          */emulationstation) es_pid="$p"; break ;;
        esac
      done
      if [ -n "$es_pid" ]; then
        kill "$es_pid" 2>/dev/null
      else
        echo "[Pocket Curator] could not identify the ES process; skipping refresh"
      fi
      ;;
    *)
      echo "[Pocket Curator] no fallback ES-refresh for '$CFW_NAME'; skipping"
      ;;
  esac
}

refresh_emulationstation() {
  # The metadata (if any) was already written in-app by the Settings
  # "Populate Pocket Curator metadata" action. Here we only need to make
  # the running ES re-read its gamelists from disk - which also drops any
  # games deleted this session. No Python needed, so it's unaffected by
  # the bundled runtime being unmounted by now.
  local reason="$1"

  # Try the in-place reload (the elegant, no-restart path).
  if _pc_reload_via_api; then
    echo "[Pocket Curator] refreshed EmulationStation in place (reloadgames API)"
    return
  fi

  # API unreachable -> per-firmware restart fallback.
  echo "[Pocket Curator] reloadgames API unavailable; using restart fallback"
  _pc_fallback_restart "$reason"
}

# Run the app.
"$PYTHON_BIN" -u "$GAMEDIR/main.py"
APP_EXIT=$?
pc_stage "app exited"
echo "[Pocket Curator] python exited with $APP_EXIT"

# Cleanup. Use pkill -f (like PortMaster) so we also catch gptokeyb2
# and path-launched instances that `pidof gptokeyb` would miss - a
# stray gptokeyb feeds phantom input to ES and can auto-launch games.
# The wait after kill swallows bash's asynchronous "Killed" job notice
# (which otherwise prints over the console), and the [g] bracket keeps
# pkill -f from matching - and killing - its own `sudo pkill ...` cmdline.
kill -9 "$GPTK_PID" 2>/dev/null || true
wait "$GPTK_PID" 2>/dev/null
$ESUDO pkill -9 -f '[g]ptokeyb' 2>/dev/null || true
$ESUDO pkill -9 -f '[g]ptokeyb2' 2>/dev/null || true

if [ "$USE_SYSTEM_PYTHON" != "1" ]; then
  if [[ "$PM_CAN_MOUNT" != "N" ]]; then
    $ESUDO umount "$py_dir" 2>/dev/null || true
  fi
  unset PYTHONHOME
fi
unset PYTHONPATH
unset PYTHONPYCACHEPREFIX
unset SDL_VIDEODRIVER

# ArkOS-family renders ports on the raw console; the window between the
# app releasing the display and harbourmaster painting its message shows
# leftover control-character residue (^] etc) on tty1. Reset it the same
# way dArkOS's own scripts do.
case "${CFW_NAME,,}" in
  arkos*|darkos*)
    [ -w /dev/tty1 ] && printf '\033c' > /dev/tty1 2>/dev/null
    ;;
esac

# If the app left a refresh flag (it does so after deletions), refresh ES
# in place so removed games drop out of the menu. With no flag, we exit
# cleanly - no refresh, no message. (Pocket Curator's own metadata is
# installed separately by tools/install_metadata.sh.)
if [ -f "$GAMEDIR/.es_refresh_needed" ]; then
  refresh_reason="$(cat "$GAMEDIR/.es_refresh_needed" 2>/dev/null)"
  rm -f "$GAMEDIR/.es_refresh_needed"

  case "$refresh_reason" in
    register)
      # Our gamelist entry is missing or incomplete (fresh manual
      # install, or the firmware rebuilt its lists). The metadata
      # installer schedules its own deferred write + ES refresh - and
      # that refresh re-reads every gamelist, so it covers this
      # session's deletions too. No second refresh from us.
      refresh_msg="Registering Pocket Curator with EmulationStation..."
      echo "[Pocket Curator] refresh reason='register'"
      pm_message "$refresh_msg"
      if [ -f "$GAMEDIR/tools/install_metadata.sh" ]; then
        PC_SKIP_PMFINISH=1 /bin/bash "$GAMEDIR/tools/install_metadata.sh"
      else
        echo "[Pocket Curator] tools/install_metadata.sh missing; plain refresh"
        refresh_emulationstation "deletions"
      fi
      ;;
    *)
      case "$refresh_reason" in
        deletions)
          refresh_msg="Refreshing your games list..."
          ;;
        metadata)
          refresh_msg="Setting up Pocket Curator's details..."
          ;;
        both|*)
          refresh_msg="Saving changes and refreshing your games list..."
          ;;
      esac
      echo "[Pocket Curator] refresh reason='$refresh_reason'"
      echo "[Pocket Curator] $refresh_msg"
      # The in-place API reload is sub-second and invisible - putting a
      # pm_message before it made every exit pay harbourmaster's slow
      # Python boot just to flash a message about work already done.
      # Message only when we actually fall back to a restart.
      if _pc_reload_via_api; then
        echo "[Pocket Curator] refreshed EmulationStation in place (reloadgames API)"
      else
        echo "[Pocket Curator] reloadgames API unavailable; using restart fallback"
        pm_message "$refresh_msg"
        _pc_fallback_restart "$refresh_reason"
      fi
      ;;
  esac
fi

pm_finish

# ArkOS-family prints PortMaster's "Killed" job-control notices to tty1
# as it pkills gptokeyb/pugwash during cleanup - harmless but ugly
# leftover text on screen as ES comes back. Clear the console once more
# after cleanup so the user is handed back a clean screen.
case "${CFW_NAME,,}" in
  arkos*|darkos*)
    [ -w /dev/tty1 ] && printf '\033c' > /dev/tty1 2>/dev/null
    ;;
esac

# Optional post-run sync. No-op unless conditions in the helper are met.
_pc_post_run_sync() {
  local logf="$GAMEDIR/pocketcurator.log"
  [ -s "$logf" ] || return 0
  # Use the GUARANTEED system python, never $PYTHON_BIN: the bundled Pyxel
  # runtime is unmounted during cleanup before this runs, so $PYTHON_BIN
  # would point at a python that no longer exists - which is exactly why
  # the upload was silently doing nothing.
  local pybin
  pybin="$(_pc_syspython)" || return 0

  local host fw dev stamp ver_line ver
  host="$(hostname 2>/dev/null | tr -cd 'A-Za-z0-9._-')"; [ -z "$host" ] && host="nohost"
  fw="$(echo "${CFW_NAME:-unknown}" | tr -cd 'A-Za-z0-9._-')"
  dev="$(echo "${DEVICE_NAME:-unknown}" | tr -cd 'A-Za-z0-9._-')"
  ver_line="$(grep -m1 '__version__' "$GAMEDIR/pocketcurator/curator/__init__.py" 2>/dev/null)"
  ver="$(echo "$ver_line" | sed -E 's/.*\"([^\"]+)\".*/\1/')"; [ -z "$ver" ] && ver="vUNK"
  stamp="$(date '+%Y%m%d-%H%M%S')"
  local named="$GAMEDIR/.pc_send_$$.log"
  cp -p "$logf" "$named" 2>/dev/null || return 0
  local final="$GAMEDIR/pocketcurator__${host}__${fw}__${dev}__v${ver}__${stamp}.log"
  mv -f "$named" "$final" 2>/dev/null || final="$logf"
  "$pybin" "$GAMEDIR/pocketcurator/tools/pc_send.py" "$final" "logs" >/dev/null 2>&1 || true
  [ "$final" != "$logf" ] && rm -f "$final" 2>/dev/null
}

# Restore stdout (close the tee pipe) so the log is fully flushed before
# we read it, then run the sync in the FOREGROUND. Backgrounding it (&)
# meant the script exited and the job was reaped before the upload could
# finish - that was the bug. It runs after the screen is already handed
# back, so a brief foreground wait is fine.
exec >/dev/tty 2>&1 || exec >/dev/null 2>&1
_pc_post_run_sync

exit "${APP_EXIT:-0}"

} # Added by Tom to force bash to load this whole script into RAM
