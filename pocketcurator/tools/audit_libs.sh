#!/bin/bash
# ============================================================================
# audit_libs.sh - identify which native libraries in pygame.libs/ are actually
# loaded into memory when Pocket Curator runs. Everything NOT shown as "USED"
# is a candidate to strip from the next build.
#
# HOW TO USE
#   1. SSH into the device.
#   2. cd /storage/roms/ports/pocketcurator/tools
#   3. ./audit_libs.sh
#   4. Paste the output back. Anything tagged UNUSED can be removed.
#
# WHAT IT DOES
#   - Locates PortMaster's control folder (same logic as the main launcher).
#   - Mounts the Pyxel runtime if it isn't mounted already.
#   - Runs Python with the same PYTHONPATH/LD_LIBRARY_PATH as a real launch.
#   - Initializes pygame's display, font, image subsystems - which is what
#     dlopen()s the native .so files.
#   - Reads /proc/self/maps to see which pygame.libs files actually got
#     loaded into memory.
#   - Lists USED and UNUSED files side-by-side.
#
# This audit reflects ONE startup path. If you later add audio playback,
# video, or anything else to the app, re-run the audit before stripping
# libs - some currently-unused ones may become required.
# ============================================================================

set -u

# Find the port dir from script location (tools/ -> port root)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PORT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
echo "[audit] port dir: $PORT_DIR"

# Find PortMaster control folder (same logic as Pocket Curator.sh)
CONTROL=""
for c in /opt/system/Tools/PortMaster /opt/tools/PortMaster \
         "${XDG_DATA_HOME:-$HOME/.local/share}/PortMaster" \
         /roms/ports/PortMaster /roms2/ports/PortMaster; do
  if [ -f "$c/control.txt" ]; then
    CONTROL="$c"
    break
  fi
done
if [ -z "$CONTROL" ]; then
  echo "[audit] ERROR: PortMaster not found"
  exit 1
fi
echo "[audit] controlfolder: $CONTROL"

RUNTIME_NAME="pyxel_2.2.8_python_3.11"
RUNTIME_FILE="$CONTROL/libs/${RUNTIME_NAME}.squashfs"
PY_DIR="$HOME/pyxel"

if [ ! -f "$RUNTIME_FILE" ]; then
  echo "[audit] ERROR: Pyxel runtime not present at $RUNTIME_FILE"
  echo "[audit] Run Pocket Curator at least once before auditing."
  exit 1
fi

# Detect architecture (audit only on bundled-Pyxel devices for now)
ARCH="$(uname -m)"
case "$ARCH" in
  aarch64|arm64) LIBS_DIR="$PORT_DIR/libs.aarch64" ;;
  armv7l|armhf)  LIBS_DIR="$PORT_DIR/libs.armhf" ;;
  *)
    echo "[audit] ERROR: unsupported architecture $ARCH"
    exit 1
    ;;
esac
PYGAME_LIBS="$LIBS_DIR/pygame.libs"
if [ ! -d "$PYGAME_LIBS" ]; then
  echo "[audit] ERROR: $PYGAME_LIBS does not exist"
  exit 1
fi
echo "[audit] pygame.libs dir: $PYGAME_LIBS"

# Mount the runtime if it's not already mounted
DID_MOUNT=0
if ! grep -qs " $PY_DIR " /proc/mounts; then
  echo "[audit] mounting Pyxel runtime..."
  sudo mkdir -p "$PY_DIR"
  if ! sudo mount "$RUNTIME_FILE" "$PY_DIR"; then
    echo "[audit] ERROR: mount failed"
    exit 1
  fi
  DID_MOUNT=1
else
  echo "[audit] runtime already mounted"
fi

export PYTHONHOME="$PY_DIR"
export PYTHONPATH="$LIBS_DIR:$PORT_DIR"
export LD_LIBRARY_PATH="$LIBS_DIR:/usr/lib/compat"
export PYGAME_HIDE_SUPPORT_PROMPT=1

# Use SDL dummy driver so we don't need a real display. We just want to
# trigger the dlopen calls, not actually render anything.
export SDL_VIDEODRIVER=dummy
export SDL_AUDIODRIVER=dummy

PYGAME_LIBS_DIR="$PYGAME_LIBS" "$PY_DIR/bin/python3" << 'PYEOF'
import os, sys
print(f"\n[audit] Python: {sys.version.split()[0]}")

# Exercise the parts of pygame that our app actually uses, so the
# corresponding native .so files get dlopen()'d.
print("[audit] importing and initializing pygame...")
import pygame
print(f"[audit] pygame {pygame.version.ver} import OK")

pygame.init()
pygame.display.init()
pygame.font.init()

# Force-load image codec native code
import pygame.image
import pygame.font
import pygame.transform
import pygame.draw

# Try a 1x1 set_mode just to fully wire up the display backend
try:
    pygame.display.set_mode((1, 1))
except Exception as exc:
    print(f"[audit] (set_mode failed under dummy driver: {exc})")

# Read /proc/self/maps to find which .so files are mapped into memory
used = set()
with open("/proc/self/maps") as f:
    for line in f:
        parts = line.split()
        if len(parts) >= 6:
            path = parts[-1]
            if "pygame.libs" in path:
                used.add(os.path.basename(path))

# List every file in pygame.libs/ on disk
libs_dir = os.environ["PYGAME_LIBS_DIR"]
on_disk = set()
for name in os.listdir(libs_dir):
    full = os.path.join(libs_dir, name)
    if os.path.isfile(full) or os.path.islink(full):
        on_disk.add(name)

unused = on_disk - used
both = used & on_disk
ghost = used - on_disk  # loaded but not in our directory (system libs we shouldn't strip)

print()
print("=" * 70)
print(f"{'USED':6} libraries actually loaded by pygame at runtime")
print("=" * 70)
for n in sorted(both):
    size = os.path.getsize(os.path.join(libs_dir, n))
    print(f"  USED   {n}  ({size/1024:.0f} KB)")

print()
print("=" * 70)
print(f"{'UNUSED':6} libraries on disk but NOT loaded - candidates to strip")
print("=" * 70)
total_savings = 0
for n in sorted(unused):
    size = os.path.getsize(os.path.join(libs_dir, n))
    total_savings += size
    print(f"  UNUSED {n}  ({size/1024:.0f} KB)")

if ghost:
    print()
    print("=" * 70)
    print("(Libraries loaded from outside pygame.libs - system libs, ignore)")
    print("=" * 70)
    for n in sorted(ghost):
        print(f"  EXTRA  {n}")

print()
print("=" * 70)
print(f"SUMMARY: {len(both)} used, {len(unused)} unused, potential savings: {total_savings/1024/1024:.1f} MB")
print("=" * 70)
PYEOF

# Unmount only if we did the mount ourselves
if [ "$DID_MOUNT" = "1" ]; then
  echo
  echo "[audit] unmounting runtime..."
  sudo umount "$PY_DIR" 2>/dev/null
fi

echo "[audit] done"
