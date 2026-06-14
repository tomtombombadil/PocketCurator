#!/bin/bash
# =====================================================================
#  Pocket Curator - dArkOS DOWN-WINDOW write probe  (Method E only)
# =====================================================================
#  Single focused test: does writing our metadata WHILE EmulationStation
#  is STOPPED (then starting it again) make the description stick on
#  dArkOS? The earlier probe proved that at menu-idle the write already
#  survives - the only thing that clobbers it is ES's game-exit flush.
#  Writing during a down-window means there is no in-RAM copy to flush
#  over us, so it should stick. This proves it on YOUR device.
#
#  RUN FROM A SHELL (SSH), not from EmulationStation:
#        cd /roms/ports          # where "Pocket Curator.sh" lives
#        bash pc_downwindow_probe.sh
#
#  ES WILL RESTART during this test (that's the point). When it comes
#  back, LOOK at the Pocket Curator entry's description:
#     * shows "PCPROBE_... DOWN-WINDOW write"  -> METHOD WORKS
#     * shows the normal description            -> it got clobbered
#  Tell me which, and send pc_downwindow_probe.log.
#
#  Your real description is backed up to gamelist.xml.pcprobe.bak. The
#  script prints the exact command to restore it at the end.
# =====================================================================

set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
LOG="$HERE/pc_downwindow_probe.log"
PC_PATH="./Pocket Curator.sh"
MARKER="PCPROBE_$(date +%s)_$$"

: > "$LOG"
log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG"; }
hr()  { echo "----------------------------------------------------------" | tee -a "$LOG"; }

log "dArkOS down-window write probe"
log "ports dir: $HERE   marker: $MARKER"
hr

# --- preconditions ---
if ! command -v systemctl >/dev/null 2>&1 || [ ! -f /etc/systemd/system/emulationstation.service ]; then
  log "!! This device has no systemd emulationstation.service - this probe"
  log "   is for dArkOS/ArkOS-family. Nothing done."
  exit 1
fi

PYBIN=""
for c in python3 /usr/bin/python3 /home/ark/pyxel/bin/python3; do
  command -v "$c" >/dev/null 2>&1 && { PYBIN="$c"; break; }
done
[ -z "$PYBIN" ] && { log "!! no python found"; exit 1; }
log "python: $PYBIN"

GL="$HERE/gamelist.xml"
[ -f "$GL" ] || { log "!! $GL not found"; exit 1; }
grep -qF "$PC_PATH" "$GL" || { log "!! no '$PC_PATH' entry in $GL (run Pocket Curator once first)"; exit 1; }

PC_SUDO=""
[ "$(id -u)" != "0" ] && PC_SUDO="sudo -n"
log "user: $(whoami) (uid=$(id -u))   sudo prefix: '${PC_SUDO:-none}'"

# --- back up and show current description ---
cp -p "$GL" "$GL.pcprobe.bak" && log "backed up: $GL -> $GL.pcprobe.bak"
CUR="$("$PYBIN" - "$GL" "$PC_PATH" <<'PY'
import sys,xml.etree.ElementTree as ET
f,p=sys.argv[1],sys.argv[2]
g=[x for x in ET.parse(f).getroot().findall('game') if (x.findtext('path') or '').strip()==p]
print((g[0].findtext('desc') or '').strip() if g else '<none>')
PY
)"
log "current description: ${CUR:0:70}..."
hr

# --- the down-window helper (real file; robust quoting) ---
DW="$HERE/.pc_downwrite.py"
cat > "$DW" <<PY
import sys, xml.etree.ElementTree as ET
PATH="$PC_PATH"
ND="$MARKER DOWN-WINDOW write"
f=sys.argv[1]
t=ET.parse(f); r=t.getroot()
g=[x for x in r.findall('game') if (x.findtext('path') or '').strip()==PATH]
if g:
    d=g[0].find('desc')
    if d is None: d=ET.SubElement(g[0],'desc')
    d.text=ND
    t.write(f)
    open("$HERE/.pc_downwrite.done","w").write("written")
PY

# --- the sequence: stop ES -> write while down -> start ES ---
# Run via systemd-run so it lives OUTSIDE ES's cgroup and survives the
# stop it issues (same trick the real launcher uses).
rm -f "$HERE/.pc_downwrite.done"
SEQ="
  sleep 2
  systemctl stop emulationstation &
  p=\$!
  i=0
  while kill -0 \"\$p\" 2>/dev/null && [ \"\$i\" -lt 20 ]; do sleep 0.25; i=\$((i+1)); done
  kill -0 \"\$p\" 2>/dev/null && systemctl kill -s SIGKILL emulationstation 2>/dev/null
  wait \"\$p\" 2>/dev/null
  \"$PYBIN\" \"$DW\" \"$GL\"
  systemctl start emulationstation
"

log "## METHOD E: stop ES -> write marker while DOWN -> start ES"
log "issuing the sequence now (ES will restart in ~2s)..."
if command -v systemd-run >/dev/null 2>&1; then
  if $PC_SUDO systemd-run --quiet --collect /bin/bash -c "$SEQ"; then
    log "systemd-run accepted the sequence."
  else
    log "systemd-run failed; trying detached setsid."
    setsid bash -c "$SEQ" >/dev/null 2>&1 &
  fi
else
  log "no systemd-run; using detached setsid."
  setsid bash -c "$SEQ" >/dev/null 2>&1 &
fi

# Give the sequence time to do its thing (stop+write+start), then report
# what the on-disk file holds. (ES may restart this shell's session; the
# log is already on disk line-by-line via tee.)
log "waiting ~20s for stop -> write -> start to complete..."
sleep 20

if [ -f "$HERE/.pc_downwrite.done" ]; then
  log "down-window write helper REPORTED success."
else
  log "down-window write helper did NOT report success (may still be mid-restart)."
fi

NOW="$("$PYBIN" - "$GL" "$PC_PATH" <<'PY'
import sys,xml.etree.ElementTree as ET
f,p=sys.argv[1],sys.argv[2]
g=[x for x in ET.parse(f).getroot().findall('game') if (x.findtext('path') or '').strip()==p]
print((g[0].findtext('desc') or '').strip() if g else '<none>')
PY
)"
log "on-disk description after sequence: ${NOW:0:70}..."
if printf '%s' "$NOW" | grep -qF "$MARKER"; then
  log "RESULT: marker is ON DISK. Now CHECK THE SCREEN - does the Pocket"
  log "        Curator entry show 'PCPROBE_...DOWN-WINDOW write'? If yes,"
  log "        the down-window method is the dArkOS fix."
else
  log "RESULT: marker NOT on disk - the write was clobbered or ES re-flushed."
fi
hr
log "RESTORE your real description when done with:"
log "    cp '$GL.pcprobe.bak' '$GL'"
log "(left in place so you can see Method E's result on screen first.)"
rm -f "$DW" "$HERE/.pc_downwrite.done" 2>/dev/null
log "done."
exit 0
