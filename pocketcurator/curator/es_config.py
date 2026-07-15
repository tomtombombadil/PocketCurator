"""
Read EmulationStation's authoritative configuration to discover systems.

ES already knows:
  - which systems exist (es_systems.cfg)
  - where their ROMs live (per-system <path>)
  - what file extensions to recognize (per-system <extension>)
  - their display name (per-system <fullname>)
  - which theme name to use for logo lookup (per-system <theme>)
  - which ones the user has hidden from the menu (es_settings.cfg HiddenSystems)

Reading this directly replaces a pile of fragile heuristics: no folder-name
guessing, no "is this 'Bomberman' a system or a game", no case sensitivity
games, no hard-coded skip list, no shortname aliases. ES has done the work;
we just consume it.

The fallback path (scanning roms_dir directly) still exists for dev/test
environments and any firmware that doesn't ship es_systems.cfg, but on
real handhelds the ES path runs.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Optional, Set


# Candidate locations for ES's config dir, in firmware preference order.
# The first one that has es_systems.cfg wins.
ES_CONFIG_CANDIDATES: List[Path] = [
    Path("/storage/.emulationstation"),                # Rocknix / JELOS / AmberELEC
    Path("/storage/.config/emulationstation"),         # variants
    Path("/userdata/system/configs/emulationstation"),  # Batocera / Knulli (live config)
    Path("/userdata/system/.emulationstation"),        # older Batocera layout
    Path("/home/ark/.emulationstation"),               # ArkOS / dArkOS
    Path("/usr/share/emulationstation"),               # distro-generated full system list
    Path("/etc/emulationstation"),                     # last-resort bundled stub
]


def find_es_config_dir() -> Optional[Path]:
    """Return the directory holding es_systems.cfg, or None if not found."""
    for d in ES_CONFIG_CANDIDATES:
        if (d / "es_systems.cfg").is_file():
            return d
    return None


def load_es_systems(config_dir: Path,
                    roms_dir: Optional[Path] = None) -> List[dict]:
    """
    Parse ``es_systems.cfg`` into a list of system dicts. Each dict has::

        {
            "shortname":  "snes",              # <name>
            "display":    "Super Nintendo...", # <fullname>, falls back to shortname
            "path":       Path("/storage/roms/snes"),  # <path>, ~ expanded
            "extensions": [".smc", ".sfc", ...],       # <extension> split on whitespace
            "theme":      "snes",              # <theme>, falls back to shortname
        }

    Returns ``[]`` only if both the standard parse and the fallback
    recovery fail. Otherwise returns whatever systems we could extract -
    a single malformed <system> block no longer takes down the whole file
    (ArkOS ships an es_systems.cfg with bad bytes around line 2162; before
    this fallback, the whole config got thrown away and the app appeared
    to have no systems).
    """
    path = config_dir / "es_systems.cfg"

    # Fast path: standard XML parse. Works for well-formed configs
    # (Rocknix, Knulli, Batocera all parse cleanly here).
    systems: List[dict] = []
    try:
        tree = ET.parse(str(path))
        for system in tree.getroot().iter("system"):
            extracted = _extract_system(system, roms_dir)
            if extracted is not None:
                systems.append(extracted)
        return systems
    except (ET.ParseError, OSError) as exc:
        print(f"[es_config] {path}: parse error ({exc}); trying per-system fallback")

    # Fallback path: pull <system>...</system> blocks out of the file
    # with a regex and parse each independently. A single malformed
    # block gets skipped instead of poisoning the whole config.
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        print(f"[es_config] {path}: cannot read file ({exc})")
        return []

    # Non-greedy match so we get one system block at a time, even when
    # the file has bad bytes between blocks.
    block_re = re.compile(r"<system\b[^>]*>.*?</system>", re.DOTALL)
    matched = 0
    skipped = 0
    for block_match in block_re.finditer(raw):
        block_xml = block_match.group(0)
        try:
            system_el = ET.fromstring(block_xml)
        except ET.ParseError:
            skipped += 1
            continue
        extracted = _extract_system(system_el, roms_dir)
        if extracted is not None:
            systems.append(extracted)
            matched += 1

    print(f"[es_config] fallback recovered {matched} systems"
          f"{f' ({skipped} skipped due to bad XML)' if skipped else ''}")
    return systems


def _extract_system(system_el, roms_dir: Optional[Path] = None) -> Optional[dict]:
    """Pull the fields we care about out of a parsed <system> element.
    Returns None for entries that lack a usable shortname or path - those
    aren't worth surfacing as carousel entries even if the XML parsed."""
    shortname = _text(system_el, "name")
    if not shortname:
        return None
    rom_path = _text(system_el, "path") or ""
    rom_dir = _resolve_rom_path(rom_path, roms_dir)
    if rom_dir is None:
        return None

    ext_raw = _text(system_el, "extension") or ""
    exts: List[str] = []
    for chunk in ext_raw.replace(",", " ").split():
        chunk = chunk.strip().lower()
        if not chunk:
            continue
        if not chunk.startswith("."):
            chunk = "." + chunk
        exts.append(chunk)

    return {
        "shortname":  shortname,
        "display":    _text(system_el, "fullname") or shortname,
        "path":       rom_dir,
        "extensions": exts,
        "theme":      _text(system_el, "theme") or shortname,
    }


def load_hidden_systems(config_dir: Path) -> Set[str]:
    """
    Parse ``es_settings.cfg`` for the ``HiddenSystems`` value. ES stores
    it as a semicolon-separated list of shortnames.

    On Batocera/Knulli the same info also lives in
    ``/userdata/system/batocera.conf`` as ``global.hiddenSystems=a;b;c``,
    but the es_settings.cfg copy is canonical on every fork we target.
    """
    path = config_dir / "es_settings.cfg"
    if not path.is_file():
        return set()
    try:
        tree = ET.parse(str(path))
    except (ET.ParseError, OSError):
        return set()

    for el in tree.getroot().iter("string"):
        if el.get("name") == "HiddenSystems":
            value = el.get("value", "") or ""
            return {s.strip() for s in value.split(";") if s.strip()}
    return set()


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

def _resolve_rom_path(rom_path: str, roms_dir: Optional[Path]):
    """Turn an es_systems.cfg <path> into an absolute directory.

    Batocera (and Knulli) write paths like "%ROMPATH%/amiga500" or a
    bare "./snes"; left untouched these resolve against the process cwd
    (the port directory), which is how fetched games ended up dumped in
    roms/ports/pocketcurator. We expand %ROMPATH% / $ROMPATH and anchor
    any still-relative path to the device's roms dir so destinations are
    always absolute and correct.
    """
    if not rom_path:
        return None
    s = rom_path.strip()
    # Normalize the ROMPATH variable in its common spellings.
    anchor = str(roms_dir) if roms_dir else None
    if anchor:
        for token in ("%ROMPATH%", "${ROMPATH}", "$ROMPATH"):
            if token in s:
                s = s.replace(token, anchor)
    try:
        p = Path(s).expanduser()
    except (TypeError, ValueError):
        return None
    if not p.is_absolute():
        # Strip a leading "./" then anchor to roms_dir (or leave as-is
        # if we have no anchor, preserving old behavior for dev runs).
        rel = s[2:] if s.startswith("./") else s
        if anchor:
            p = Path(anchor) / rel
        else:
            p = Path(rel)
    return p


def _text(elem, tag: str) -> str:
    """Return stripped text of a child element, or empty string."""
    child = elem.find(tag)
    if child is None or child.text is None:
        return ""
    return child.text.strip()
