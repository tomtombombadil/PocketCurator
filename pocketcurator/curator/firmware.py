"""
Firmware detection and ROM path resolution.

We look in the standard ROM root directories used by the major handheld
firmwares and return the first one that exists. The PC-development override
``POCKETCURATOR_ROMS_DIR`` lets you point at a fake roms folder while iterating
on your desktop.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional, List

from .es_config import (
    find_es_config_dir,
    load_es_systems,
    load_hidden_systems,
)


# Probed in priority order. Most firmwares ship one of these.
#
# /userdata/roms          - Batocera, Knulli (Batocera-based)
# /storage/roms           - JELOS, AmberELEC, Rocknix (LibreELEC-based)
# /roms                   - ArkOS, dArkOS, RetroOZ, TheRA
# /mnt/mmc/MUOS/info/...  - MuOS has a different shape; handled separately
# /roms2                  - ArkOS second SD card (RG351V/MP/etc.)
CANDIDATE_ROOTS: List[str] = [
    "/userdata/roms",
    "/storage/roms",
    "/roms",
    "/roms2",
    # MuOS specifically:
    "/mnt/mmc/MUOS/info/roms",
    "/mnt/mmc/ROMS",
]


def detect_roms_dir(override: Optional[str] = None) -> Optional[Path]:
    """
    Return the first ROM root that exists, or ``None`` if none are found.

    ``override`` wins over autodetection. The environment variable
    ``POCKETCURATOR_ROMS_DIR`` wins over everything else, so you can override
    on the command line without editing settings.json.
    """
    env = os.environ.get("POCKETCURATOR_ROMS_DIR")
    if env:
        p = Path(env).expanduser()
        return p if p.is_dir() else None

    if override:
        p = Path(override).expanduser()
        if p.is_dir():
            return p

    for c in CANDIDATE_ROOTS:
        p = Path(c)
        if p.is_dir():
            return p

    return None


def detect_firmware_name() -> str:
    """
    Best-effort firmware identification for display and the log.

    Prefers the launcher-provided ``POCKETCURATOR_CFW`` (PortMaster's
    ``$CFW_NAME``), which is authoritative. Falls back to filesystem
    markers only when that's absent (e.g. running on desktop for dev).
    """
    cfw = os.environ.get("POCKETCURATOR_CFW", "").strip()
    if cfw:
        # Normalize to friendly casing for the few we know; otherwise
        # return as-is so unusual firmwares still display something real.
        pretty = {
            "knulli": "Knulli",
            "batocera": "Batocera",
            "rocknix": "ROCKNIX",
            "jelos": "JELOS",
            "amberelec": "AmberELEC",
            "arkos": "ArkOS",
            "muos": "muOS",
        }
        return pretty.get(cfw.lower(), cfw)

    # Filesystem-marker fallback (dev/desktop or missing env)
    if Path("/storage/.config/distribution/name").exists():
        try:
            return Path("/storage/.config/distribution/name").read_text().strip()
        except OSError:
            pass
    if Path("/etc/jelos-release").exists():
        return "JELOS"
    if Path("/etc/amberelec-release").exists():
        return "AmberELEC"
    if Path("/etc/rocknix-release").exists():
        return "ROCKNIX"
    if Path("/etc/knulli-release").exists():
        return "Knulli"
    if Path("/userdata/system/batocera.conf").exists():
        return "Batocera"
    if Path("/mnt/mmc/MUOS").is_dir() or Path("/opt/muos").is_dir():
        return "muOS"
    if Path("/etc/arkos.conf").exists():
        return "ArkOS"
    return "unknown"


def load_systems_db(package_dir: Path) -> dict:
    """Read the bundled systems.json that maps shortnames -> metadata."""
    path = package_dir / "systems.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        # Don't kill the app over the systems DB - just degrade gracefully.
        print(f"[firmware] failed to load systems.json: {exc}")
        return {}


_last_all_targets: List[dict] = []


def all_fetch_targets() -> List[dict]:
    """Every ES system with a real roms folder on disk - including
    empty ones - usable as a fetch destination. Populated by the most
    recent discover_systems() call."""
    return list(_last_all_targets)


def discover_systems(roms_dir: Path, systems_db: dict) -> List[dict]:
    """
    Return the list of systems Pocket Curator should offer to manage.

    Primary path: read EmulationStation's own config. ES already knows
    which systems exist, where their ROMs live, what extensions they
    use, and which ones the user has hidden from their menu. We use
    that as the source of truth.

    Fallback path: if no ES config is reachable (dev environment, a
    weird firmware), scan ``roms_dir`` directly using the legacy
    heuristics. This path keeps the app usable but is strictly worse.

    Each returned dict has::

        {
            "shortname":  str,     # ES short name, e.g. "snes"
            "display":    str,     # ES fullname, e.g. "Super Nintendo..."
            "path":       Path,    # absolute path to the system directory
            "extensions": [str],   # lower-case, leading-dot file extensions
            "theme":      str,     # ES theme key for logo lookup
            "rom_count":  int,     # number of ROMs we counted
        }
    """
    es_dir = find_es_config_dir()
    if es_dir is not None:
        print(f"[discover] using ES config at {es_dir}")
        return _discover_from_es(es_dir, roms_dir)

    print("[discover] no ES config found - falling back to filesystem scan")
    return _discover_from_filesystem(roms_dir, systems_db)


# Systems that legitimately appear in es_systems.cfg but aren't ROM
# collections we should offer to manage:
#   ports, tools, emulators - launcher scripts for standalone games,
#                      utilities, and emulator front-ends; not ROM
#                      collections.
#   favorites etc.   - "auto-collections" that ES synthesizes from other
#                      systems; the actual ROMs live in their real systems.
#   prboom, mrboom, sdlpop, doom, openbor - bundled game engines that
#                      look like systems to ES but represent a single
#                      game's variants (Doom WADs, Bomberman, Prince of
#                      Persia, OpenBOR mods).
#   odcommander, vaixterm, pygame - utility "systems" (file manager,
#                      terminal, pygame runtime category) that aren't
#                      ROM collections.
ES_NON_GAME_SYSTEMS = {
    "ports", "tools", "emulators",
    "favorites", "recent", "lastplayed", "allgames",
    "2players", "4players", "kidgames", "music",
    "custom-collections", "all", "collections",
    "prboom", "doom", "mrboom", "openbor", "sdlpop", "easyrpg",
    "stratagus", "tic80", "wasm4", "j2me", "lutris",
    "odcommander", "vaixterm", "pygame",
    # Knulli/Batocera screenshot viewer and other firmware utilities
    "imageviewer", "screenshots",
    # Single-game engines often shipped as "systems" in es_systems.cfg
    "cannonball", "devilutionx", "solarus", "duke3d",
    "quake", "wolf3d", "ecwolf", "rott",
    # Batocera/Knulli single-game port "systems" (engines that present
    # as a system but are one game, not a ROM collection).
    "halflife", "hlsp", "halflife2", "hl2", "xash3d",
    "sonicretro", "sonic-mania", "sonicmania", "sm64", "supermario64",
    "cdogs", "cgenius", "commandergenius", "dxx-rebirth", "dxxrebirth",
    "eduke32", "fallout1", "fallout2", "flatpak", "fury",
    "gzdoom", "hcl", "hurrican", "ioquake3", "jazz2", "jazzjackrabbit",
    "minecraft", "mrboom", "openjazz", "opentyrian", "openttd",
    "pico8", "pico-8", "prboomplus", "ruffle", "sdlpop2",
    "tyrian", "uqm", "uracer", "vvvvvv", "xrick", "znez",
}


def _is_auto_collection(shortname: str) -> bool:
    """ES synthesizes auto-collections; their entries live elsewhere."""
    return shortname.startswith("auto-") or shortname in ES_NON_GAME_SYSTEMS


def _discover_from_es(es_dir: Path,
                      roms_dir: Optional[Path] = None) -> List[dict]:
    """Authoritative system list from EmulationStation's config."""
    raw_systems = load_es_systems(es_dir, roms_dir)
    hidden = load_hidden_systems(es_dir)
    if hidden:
        print(f"[discover] honoring ES hidden systems: {sorted(hidden)}")

    out: List[dict] = []
    skipped_special: List[str] = []
    for sys in raw_systems:
        if sys["shortname"] in hidden:
            continue
        if _is_auto_collection(sys["shortname"]):
            skipped_special.append(sys["shortname"])
            continue
        path = sys["path"]
        if not path.is_dir():
            continue
        rom_count = _count_candidates(path, sys["extensions"])
        if rom_count == 0:
            continue
        out.append({
            "shortname":  sys["shortname"],
            "display":    sys["display"],
            "path":       path,
            "extensions": sys["extensions"],
            "theme":      sys["theme"],
            "rom_count":  rom_count,
        })

    _last_all_targets.clear()
    for sys in raw_systems:
        if _is_auto_collection(sys["shortname"]):
            continue
        path = sys["path"]
        # A fetch DESTINATION only needs a real folder on disk - not
        # any ROMs yet. The device's empty roms/atarijaguar is a valid
        # place to copy a Jaguar game even though discovery (which
        # needs >=1 ROM to SHOW a system) skipped it.
        if not path.is_dir():
            continue
        _last_all_targets.append({
            "shortname":  sys["shortname"],
            "display":    sys["display"],
            "path":       path,
            "extensions": sys["extensions"],
            "theme":      sys["theme"],
            "rom_count":  0,
        })

    if skipped_special:
        print(f"[discover] skipping non-game ES systems: "
              f"{sorted(skipped_special)}")

    # Sort by display name so the carousel order matches a user's
    # general expectation.
    out.sort(key=lambda s: s["display"].lower())
    return out


def _discover_from_filesystem(roms_dir: Path, systems_db: dict) -> List[dict]:
    """Legacy heuristic scanner. Used only when ES config is missing."""
    systems: List[dict] = []
    _last_all_targets.clear()
    try:
        children = sorted(roms_dir.iterdir(), key=lambda p: p.name.lower())
    except OSError:
        return systems

    skip_names = {
        ".", "..",
        "ports", "tools", "emulators", "system", "userdata",
        "media", "themes", "screenshots",
        "downloaded_images", "downloaded_videos", "downloaded_videos_cache",
        "bios", "BIOS",
        "boxart", "marquees", "manuals", "thumbnails", "videos", "images",
        "lost+found", ".tmp", ".cache", ".trash-0", ".trash-1000",
        "doom", "prboom", "openbor", "mrboom", "stratagus",
        "lutris", "j2me", "tic80", "wasm4", "easyrpg",
    }
    skip_lower = {n.lower() for n in skip_names}
    systems_db_lower = {k.lower(): v for k, v in systems_db.items()}

    for entry in children:
        if not entry.is_dir():
            continue
        if entry.name.lower() in skip_lower or entry.name.startswith("."):
            continue

        meta = systems_db_lower.get(entry.name.lower(), {})
        display = meta.get("display", entry.name)
        extensions = [ext.lower() for ext in meta.get("extensions", [])]
        known_system = entry.name.lower() in systems_db_lower

        # A known-DB folder is a valid fetch destination even with no
        # ROMs yet (empty atarijaguar), mirroring the ES path.
        if known_system:
            _last_all_targets.append({
                "shortname":  entry.name,
                "display":    display,
                "path":       entry,
                "extensions": extensions,
                "theme":      entry.name,
                "rom_count":  0,
            })

        rom_count = _count_candidates(entry, extensions)
        if rom_count == 0:
            continue

        if not known_system:
            gl_count = _count_from_gamelist(entry)
            if gl_count < 2:
                continue

        systems.append({
            "shortname":  entry.name,
            "display":    display,
            "path":       entry,
            "extensions": extensions,
            "theme":      entry.name,
            "rom_count":  rom_count,
        })

    return systems


def _count_candidates(system_dir: Path, extensions: List[str]) -> int:
    """
    Return the number of games for a system.

    gamelist.xml is the sole source of truth. If a system has no
    gamelist.xml, it has no games as far as Pocket Curator is concerned -
    even if the directory contains files that look like ROMs by extension.
    Those "ROMs" are almost always bios files, save states, or other
    emulator scaffolding that we'd be wrong to surface as games. EmulationStation
    itself only shows systems with a populated gamelist.xml; we follow
    the same rule.

    The ``extensions`` parameter is kept for API compatibility but is
    deliberately unused - the previous filesystem-walk-by-extension
    fallback was the source of bogus "1 game" / "3 games" entries for
    systems that had only bios .zip files in their rom folders.
    """
    del extensions  # not used; see docstring
    return _count_from_gamelist(system_dir)



def _count_from_gamelist(system_dir: Path) -> int:
    """
    Count <game> entries in the gamelist that have a <path>. Does not
    stat the path - if the user has gone to the trouble of scraping a
    gamelist, we trust it lists real games. Per-entry stat checks made
    this O(N) in disk seeks on slow SD cards for no real benefit during
    discovery.
    """
    gl = system_dir / "gamelist.xml"
    if not gl.is_file():
        return 0

    try:
        import xml.etree.ElementTree as ET
        tree = ET.parse(str(gl))
    except (ET.ParseError, OSError):
        return 0

    paths = []
    for game in tree.getroot().iter("game"):
        path_el = game.find("path")
        if path_el is not None and path_el.text and path_el.text.strip():
            paths.append(path_el.text.strip())
    count = len(paths)

    # Ghost-system guard. Some firmwares (notably Batocera) ship a few
    # stock gamelist entries whose ROM files don't actually exist -
    # Megadrive "Old Towers", PCEngine "Reflectron"/"Santatlanean", and
    # single-game ports like Half-Life. They make an otherwise-empty
    # system look "live" with 1-5 games, but entering it shows nothing.
    # gamelist.xml stays our source of truth for normal systems, but for
    # a SMALL system (<=5 games) we cheaply confirm at least one listed
    # ROM exists on disk; if none do, treat the system as empty so it
    # isn't offered. We cap the check at 5 so big libraries never pay the
    # per-file stat cost during discovery.
    if 0 < count <= 5:
        any_exists = False
        for rel in paths:
            rom = (system_dir / rel) if not Path(rel).is_absolute() else Path(rel)
            try:
                if rom.exists():
                    any_exists = True
                    break
            except OSError:
                continue
        if not any_exists:
            print(f"[discover] {system_dir.name}: {count} gamelist "
                  f"entr{'y' if count == 1 else 'ies'} but no ROM files "
                  f"on disk - treating as empty (ghost system).")
            return 0
    return count
