#!/bin/bash
# =====================================================================
#  Pocket Curator - metadata write/refresh DIAGNOSTIC
# =====================================================================
#  This is a STANDALONE TEST TOOL. It is not part of a release. It does
#  not modify Pocket Curator. Its only job is to prove, on YOUR device,
#  which way of writing our <game> metadata into the Ports gamelist
#  actually STICKS after EmulationStation does its game-exit flush.
#
#  HOW TO USE
#    1. Copy this file into  /roms/ports/  (or /storage/roms/ports/ on
#       ROCKNIX), next to "Pocket Curator.sh".
#    2. From a shell on the device (SSH or a terminal port), run:
#           cd /roms/ports            # or /storage/roms/ports
#           bash pc_metadata_probe.sh
#       You do NOT need to launch it from EmulationStation. Running it
#       from a shell while ES is up is exactly the scenario we care
#       about (ES is the live process that will flush/clobber).
#    3. It writes a full transcript to  pc_metadata_probe.log  next to
#       itself. Send me that file.
#
#  WHAT IT DOES (read-only-ish, and reversible)
#    - Finds every gamelist.xml ES might read for the Ports system.
#    - BACKS UP each one (.pcprobe.bak) before touching it.
#    - Writes a UNIQUE marker description into our <game> entry.
#    - Tries one refresh method (or all), then re-reads after delays to
#      see whether the marker survived or got clobbered.
#    - At the end it RESTORES the original description from backup, so
#      your real Pocket Curator description is left as it was.
#
#  It changes ONLY the <desc> of the "./Pocket Curator.sh" entry, and
#  restores it. It never touches any other game or field.
# =====================================================================

set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
LOG="$HERE/pc_metadata_probe.log"
PORTS_DIR="$HERE"
PC_PATH="./Pocket Curator.sh"
MARKER="PCPROBE_$(date +%s)_$$"

# ---- logging ---------------------------------------------------------
: > "$LOG"
log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG"; }
hr()  { echo "----------------------------------------------------------" | tee -a "$LOG"; }

log "Pocket Curator metadata probe starting"
log "ports dir : $PORTS_DIR"
log "marker    : $MARKER"
hr

# ---- 0. environment facts -------------------------------------------
log "## ENVIRONMENT"
log "whoami           : $(whoami 2>/dev/null) (uid=$(id -u 2>/dev/null))"
log "CFW (guess)      : ${CFW_NAME:-unknown}"
for v in HOME XDG_RUNTIME_DIR WAYLAND_DISPLAY SDL_VIDEODRIVER; do
  log "$v = ${!v:-(unset)}"
done
log "curl present     : $(command -v curl >/dev/null && echo yes || echo no)"
log "systemctl present: $(command -v systemctl >/dev/null && echo yes || echo no)"
log "es-restart sentinel convention dir writable (/tmp): $([ -w /tmp ] && echo yes || echo no)"
# Is the ES reload API live right now?
if command -v curl >/dev/null 2>&1; then
  if curl -s -m 5 http://localhost:1234/reloadgames >/dev/null 2>&1; then
    log "reloadgames API  : RESPONDS (HTTP localhost:1234)"
    API_LIVE=1
  else
    log "reloadgames API  : no response"
    API_LIVE=0
  fi
else
  API_LIVE=0
fi
# Is ES running, and how is it managed?
ES_PIDS="$(pgrep -f emulationstation 2>/dev/null | tr '\n' ' ')"
log "emulationstation PIDs: ${ES_PIDS:-none}"
if command -v systemctl >/dev/null 2>&1; then
  log "systemd ES unit  : $(systemctl is-active emulationstation 2>/dev/null || echo 'n/a') / present=$( [ -f /etc/systemd/system/emulationstation.service ] && echo yes || echo no)"
fi
hr

# ---- 1. find candidate gamelists ------------------------------------
log "## CANDIDATE GAMELISTS (everywhere ES might read the Ports list)"
CANDIDATES=()
add_candidate() { [ -f "$1" ] && CANDIDATES+=("$1") && log "  found: $1"; }

add_candidate "$PORTS_DIR/gamelist.xml"
for es in \
    /storage/.emulationstation \
    /storage/.config/emulationstation \
    /userdata/system/.emulationstation \
    /home/ark/.emulationstation \
    "$HOME/.emulationstation" \
    /etc/emulationstation ; do
  add_candidate "$es/gamelists/ports/gamelist.xml"
done

if [ "${#CANDIDATES[@]}" -eq 0 ]; then
  log "!! No gamelist.xml with a Ports entry found. Is Pocket Curator installed?"
  exit 1
fi

# Which candidates actually contain our entry?
OURS=()
for f in "${CANDIDATES[@]}"; do
  if grep -qF "$PC_PATH" "$f" 2>/dev/null; then
    OURS+=("$f")
    log "  -> contains our entry: $f"
  fi
done
if [ "${#OURS[@]}" -eq 0 ]; then
  log "!! None of the gamelists contain a '$PC_PATH' entry."
  log "   (Pocket Curator may not be registered yet. Run it once, then re-run this.)"
  exit 1
fi
hr

# ---- helpers to read/write the <desc> of our entry -------------------
# We use python for safe XML editing; find a python the same way the app would.
PYBIN=""
for cand in python3 /usr/bin/python3 /home/ark/pyxel/bin/python3 /storage/pyxel/bin/python3; do
  command -v "$cand" >/dev/null 2>&1 && { PYBIN="$cand"; break; }
done
log "python for XML edits: ${PYBIN:-NONE FOUND}"
[ -z "$PYBIN" ] && { log "!! no python available; cannot continue"; exit 1; }
hr

read_desc() {  # $1=file -> prints current desc of our entry
  "$PYBIN" - "$1" "$PC_PATH" <<'PY'
import sys, xml.etree.ElementTree as ET
f, path = sys.argv[1], sys.argv[2]
try:
    g=[x for x in ET.parse(f).getroot().findall('game')
       if (x.findtext('path') or '').strip()==path]
    if g:
        d=g[0].findtext('desc')
        print((d or '').strip())
except Exception as e:
    print('<<read-error: %s>>' % e)
PY
}

write_desc() {  # $1=file $2=new desc text
  "$PYBIN" - "$1" "$PC_PATH" "$2" <<'PY'
import sys, xml.etree.ElementTree as ET
f, path, newdesc = sys.argv[1], sys.argv[2], sys.argv[3]
t=ET.parse(f); r=t.getroot()
g=[x for x in r.findall('game') if (x.findtext('path') or '').strip()==path]
if not g:
    print('NO_ENTRY'); sys.exit(0)
d=g[0].find('desc')
if d is None:
    d=ET.SubElement(g[0],'desc')
d.text=newdesc
t.write(f, encoding='unicode' if sys.version_info<(3,8) else 'utf-8')
print('OK')
PY
}

# ---- 2. back up + record originals ----------------------------------
log "## BACKUP + ORIGINAL DESCRIPTIONS"
declare -A ORIG
for f in "${OURS[@]}"; do
  cp -p "$f" "$f.pcprobe.bak" 2>/dev/null && log "  backed up: $f -> $f.pcprobe.bak"
  ORIG["$f"]="$(read_desc "$f")"
  log "  original desc [$f]:"
  log "      ${ORIG["$f"]:0:80}..."
done
hr

restore_all() {
  log "## RESTORE originals from backup"
  for f in "${OURS[@]}"; do
    if [ -f "$f.pcprobe.bak" ]; then
      cp -p "$f.pcprobe.bak" "$f" && log "  restored: $f"
    fi
  done
}
trap 'restore_all' EXIT

# ---- 3. probe a refresh method --------------------------------------
# Each probe: write MARKER into every copy, run the method, then sample
# the desc at 0s/3s/8s/15s to see if/when it gets clobbered.
sample() {  # $1=label
  local label="$1" t
  for t in 0 3 8 15; do
    [ "$t" -gt 0 ] && sleep "$( [ "$t" = 3 ] && echo 3 || ([ "$t" = 8 ] && echo 5 || echo 7) )"
    for f in "${OURS[@]}"; do
      local cur; cur="$(read_desc "$f")"
      if printf '%s' "$cur" | grep -qF "$MARKER"; then
        log "    [$label +${t}s] SURVIVED in $f"
      else
        log "    [$label +${t}s] CLOBBERED in $f  (now: ${cur:0:40}...)"
      fi
    done
  done
}

write_marker_everywhere() {
  for f in "${OURS[@]}"; do
    local r; r="$(write_desc "$f" "$MARKER this is the probe marker description")"
    log "  wrote marker into $f -> $r"
  done
}

log "## METHOD A: write only (no refresh) - baseline for ES's own flush"
write_marker_everywhere
log "  (now watching whether ES flushes over it on its own)"
sample "A:write-only"
hr

log "## METHOD B: write + reloadgames API"
write_marker_everywhere
if command -v curl >/dev/null 2>&1; then
  curl -s -m 8 http://localhost:1234/reloadgames >/dev/null 2>&1 \
    && log "  curl reloadgames: sent" || log "  curl reloadgames: failed/no-API"
fi
sample "B:api-reload"
hr

log "## METHOD C: write + /tmp/es-restart sentinel (RetroPie/ArkOS convention)"
write_marker_everywhere
echo "" > /tmp/es-restart 2>/dev/null && log "  touched /tmp/es-restart" || log "  could not write /tmp/es-restart"
sample "C:es-restart-sentinel"
hr

if command -v systemctl >/dev/null 2>&1 && [ -f /etc/systemd/system/emulationstation.service ]; then
  PC_SUDO=""
  [ "$(id -u)" != "0" ] && PC_SUDO="sudo -n"

  # ---- METHOD E: the one we actually expect to work on dArkOS --------
  # Stop ES, write the marker WHILE ES IS DOWN (so there's no in-RAM copy
  # to flush over it), then start ES. Run via systemd-run so the sequence
  # lives OUTSIDE our cgroup and survives the stop it issues. This mirrors
  # the launcher's metadata/both path. The marker should survive because
  # ES reads it fresh from disk on start and never had a stale RAM copy.
  log "## METHOD E: stop ES -> write while DOWN -> start ES (systemd-run)"
  log "   THIS IS THE KEY TEST FOR dArkOS. ES will restart. The sequence"
  log "   writes the marker while ES is down, then starts ES. After ES"
  log "   comes back, open the Pocket Curator entry: does it show the"
  log "   marker text 'PCPROBE_...' as its description? Tell me yes/no."
  log "   (We also leave the marker in place for method E so you can SEE"
  log "    it on-screen; the backups are still here to restore by hand:"
  log "    each  *.pcprobe.bak  next to its gamelist.)"
  write_marker_everywhere
  log "  sampling immediately before the stop/start (ES still up):"
  sample "E:pre-stopstart"

  # Write a small helper that stamps the DOWN-WINDOW marker into every
  # gamelist copy. A real file avoids fragile nested-heredoc quoting.
  DOWNWRITE="$HERE/.pcprobe_downwrite.py"
  {
    echo "import sys, xml.etree.ElementTree as ET"
    echo "path='$PC_PATH'"
    echo "nd='$MARKER DOWN-WINDOW write'"
    echo "for f in sys.argv[1:]:"
    echo "    try:"
    echo "        t=ET.parse(f); r=t.getroot()"
    echo "        g=[x for x in r.findall('game') if (x.findtext('path') or '').strip()==path]"
    echo "        if g:"
    echo "            d=g[0].find('desc')"
    echo "            if d is None: d=ET.SubElement(g[0],'desc')"
    echo "            d.text=nd; t.write(f)"
    echo "    except Exception:"
    echo "        pass"
  } > "$DOWNWRITE"

  FILES_ARG=""
  for f in "${OURS[@]}"; do FILES_ARG="$FILES_ARG \"$f\""; done

  ESEQ="
    sleep 2
    systemctl stop emulationstation &
    p=\$!
    i=0
    while kill -0 \"\$p\" 2>/dev/null && [ \"\$i\" -lt 20 ]; do sleep 0.25; i=\$((i+1)); done
    kill -0 \"\$p\" 2>/dev/null && systemctl kill -s SIGKILL emulationstation 2>/dev/null
    wait \"\$p\" 2>/dev/null
    \"$PYBIN\" \"$DOWNWRITE\" $FILES_ARG
    systemctl start emulationstation
  "
  log "  launching stop->write->start via systemd-run (outside our cgroup)..."
  if command -v systemd-run >/dev/null 2>&1; then
    if $PC_SUDO systemd-run --quiet --collect /bin/bash -c "$ESEQ"; then
      log "  systemd-run accepted the sequence."
    else
      log "  systemd-run FAILED; falling back to plain restart for this test."
      $PC_SUDO systemctl restart emulationstation --no-block 2>/dev/null
    fi
  else
    log "  no systemd-run; using a detached setsid sequence instead."
    setsid bash -c "$ESEQ" >/dev/null 2>&1 &
  fi
  log ""
  log ">>> ES is restarting now. When it returns, LOOK at the Pocket"
  log ">>> Curator entry's description. If it shows 'PCPROBE_...DOWN-WINDOW"
  log ">>> write', METHOD E WORKS and that's the fix for dArkOS."
  log ">>> To put your real description back afterwards, run:"
  for f in "${OURS[@]}"; do
    log ">>>     cp '$f.pcprobe.bak' '$f'"
  done
  log "probe complete (method E issued; backups left in place)."
  # Do NOT auto-restore here: we want you to SEE method E's result on
  # screen. The trap is cleared so the restore doesn't run under us.
  trap - EXIT
  exit 0
else
  log "## METHODS D/E skipped (no systemd emulationstation unit on this firmware)"
fi

hr
log "All non-destructive methods probed. Originals will be restored now."
log "Send me  $LOG"
exit 0
