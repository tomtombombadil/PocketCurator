"""
Self-register Pocket Curator in the Ports system's gamelist.xml.

EmulationStation maintains a per-system gamelist.xml that controls how a
"game" (port, in our case) is presented in the menu: name, description,
artwork, genre, etc. On first install, ES auto-discovers our .sh file
but leaves the metadata blank. This module fills in a curated entry so
users see a proper description and artwork instead of just the filename.

DESIGN PRINCIPLES

- IDEMPOTENT. Re-runs that find nothing to do are no-ops.
- PER-FIELD MERGE. If our <game> element exists already, we check each
  field individually. Missing or empty fields get populated from our
  template; fields with existing content are NEVER overwritten. The
  important fields (desc, image) get filled in even if the user happens
  to have edited the name or rating.
- ATOMIC. We write to a sibling temp file and rename, so a crash mid-
  write can never leave a half-written gamelist.xml.
- DEFENSIVE. Any failure (permission denied, malformed XML, race with
  ES, anything) is logged and swallowed. This is housekeeping; it must
  never block the app launch.
- RESPECTS OTHER ENTRIES. We use ElementTree, which preserves other
  <game> elements' content. Whitespace/formatting of other entries may
  get normalized when ET rewrites the file, but that's harmless - ES
  itself rewrites this file frequently.
"""

from __future__ import annotations

import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional


# The path string EmulationStation uses to identify our entry (relative
# to the ports directory).
POCKET_CURATOR_PATH = "./Pocket Curator.sh"

# The fields we manage. Order matters for FRESH inserts (controls XML
# child order in new <game> elements); on per-field merge into an
# existing element we don't reorder anything that's already there.
OUR_FIELDS: "dict[str, str]" = {
    "name": "Pocket Curator",
    "desc": (
        "Pocket Curator uses an Emulation Station-like interface "
        "allowing you to visually copy and delete games and whole "
        "systems without removing your SD card. You can see the "
        "screenshot, description, rating, genre, and origin of the "
        "game. Letting you make informed decisions before copying or "
        "deleting. It lets you curate your collection right from the "
        "convenience of your device. Connect to WebDAV servers to copy "
        "games direct to your device!"
    ),
    "genre": "Various, Utilities",
    "developer": "tomtombombadil",
    "rating": "1",
    "releasedate": "20260607T000000",
    "image": "./pocketcurator/assets/Screenshot-GamesList.jpg",
    "thumbnail": "./pocketcurator/assets/Screenshot-GamesList.jpg",
    "titleshot": "./pocketcurator/assets/Screenshot-Systems.jpg",
    "marquee": "./pocketcurator/assets/splash.jpg",
    "video": "./pocketcurator/assets/PocketCurator.mp4",
}


def _log(msg: str) -> None:
    """Print to stderr so it lands in the launcher log alongside bash output."""
    print(f"[ports_gamelist] {msg}", file=sys.stderr)


def entry_exists(ports_dir: Path) -> bool:
    """True if a Pocket Curator <game> node already exists in any gamelist
    ES might read. Distinguishes 'our entry is present but a field needs
    updating' (write straight to disk + reload) from 'no entry at all'
    (let ES create the bare node first via the deferred installer)."""
    try:
        ports_dir = Path(ports_dir)
    except Exception:
        return False
    for path in _gamelist_locations(ports_dir):
        if not path.exists():
            continue
        try:
            tree = ET.parse(path)
        except ET.ParseError:
            continue
        root = tree.getroot()
        if root.tag != "gameList":
            continue
        if _find_our_game(root) is not None:
            return True
    return False


def entry_needs_metadata(ports_dir: Path) -> bool:
    """
    Read-only check: does our Pocket Curator entry need enrichment in any
    gamelist EmulationStation might read?

    Returns True if, in the primary gamelist that exists, our entry is
    missing entirely or is missing/empty for any field in OUR_FIELDS.
    Does NOT write anything - writing while ES is running is futile
    because ES rewrites our node from its in-RAM FileData on its next
    flush (see ES's Gamelist.cpp updateGamelist). The launcher performs
    the actual write during the window when ES is stopped.
    """
    try:
        ports_dir = Path(ports_dir)
    except Exception:
        return False

    for path in _gamelist_locations(ports_dir):
        if not path.exists():
            continue
        try:
            tree = ET.parse(path)
        except ET.ParseError:
            continue
        root = tree.getroot()
        if root.tag != "gameList":
            continue
        our_game = _find_our_game(root)
        if our_game is None:
            return True
        for field_name, field_value in OUR_FIELDS.items():
            existing = our_game.find(field_name)
            if existing is None or (existing.text or "").strip() != field_value:
                return True
        # Entry exists and every managed field matches our canonical value.
        return False
    # No gamelist exists yet -> nothing parsed us, so enrichment is
    # warranted once one appears (ES will create the bare entry).
    return False


def ensure_entry(ports_dir: Path) -> bool:
    """
    Ensure a Pocket Curator entry exists with all our managed fields
    populated in every gamelist.xml location EmulationStation might read.

    EmulationStation typically prioritizes its own override location
    (e.g. /storage/.emulationstation/gamelists/ports/gamelist.xml on
    Rocknix) over the ROM-folder gamelist. Different firmwares put the
    .emulationstation folder in different places. We update every
    candidate location that exists, so the change shows up regardless
    of which one ES happens to read from.

    NOTE TO USERS: EmulationStation holds gamelist.xml in RAM after it
    starts. Changes made on disk while ES is running may not appear
    until ES restarts or refreshes. ES also writes its in-memory copy
    back to disk on shutdown, which can clobber our changes if it was
    already in RAM with no Pocket Curator entry. After the FIRST run
    of Pocket Curator on a fresh install, an ES restart (Start menu ->
    Quit -> Restart Emulation Station, or full reboot) is recommended
    so ES picks up our entry.

    Returns True if any file was updated, False otherwise.
    """
    try:
        ports_dir = Path(ports_dir)
    except Exception as exc:
        _log(f"bad ports_dir argument: {exc}")
        return False

    locations = _gamelist_locations(ports_dir)
    if not locations:
        _log("no plausible gamelist.xml locations found")
        return False

    changed_any = False
    for path in locations:
        try:
            if _update_one(path):
                changed_any = True
        except Exception as exc:
            _log(f"failed at {path}: {type(exc).__name__}: {exc}")
            # Keep trying other locations even if one fails
            continue

    return changed_any


def _gamelist_locations(ports_dir: Path) -> "list[Path]":
    """
    Return the list of gamelist.xml paths we should ensure are updated.

    Always includes the ROM-folder location. Adds the ES override
    location(s) if their parent .emulationstation folder exists.
    """
    locations = [ports_dir / "gamelist.xml"]

    # Same .emulationstation candidates that curator/es_config.py knows
    # about. Kept in sync manually to avoid an awkward import cycle from
    # ports_gamelist (called very early in startup) into es_config.
    es_homes = [
        Path("/storage/.emulationstation"),         # Rocknix / JELOS / AmberELEC
        Path("/storage/.config/emulationstation"),  # variants
        Path("/userdata/system/.emulationstation"), # Batocera / Knulli
        Path("/home/ark/.emulationstation"),        # ArkOS / dArkOS
        Path.home() / ".emulationstation",          # user-home fallback
    ]
    for es_home in es_homes:
        if es_home.is_dir():
            override_path = es_home / "gamelists" / "ports" / "gamelist.xml"
            if override_path not in locations:
                locations.append(override_path)

    return locations


def _update_one(gamelist: Path) -> bool:
    """
    Ensure a properly-populated Pocket Curator entry exists in the given
    gamelist.xml file. Creates the parent directory and the file if
    neither exists. Returns True if any change was written.
    """
    # Case A: file doesn't exist. Create the dir tree if needed, then
    # write a fresh file with our entry.
    if not gamelist.exists():
        # Only create the parent dir if it's already nested in some
        # gamelists/ structure that ES owns; never go creating random
        # /storage/.emulationstation trees that don't already exist.
        parent = gamelist.parent
        if not parent.exists():
            grandparent = parent.parent  # ...gamelists/ folder
            if not grandparent.is_dir():
                _log(f"skipping {gamelist}: parent tree doesn't exist")
                return False
            parent.mkdir(parents=True, exist_ok=True)

        content = _build_fresh_file()
        _atomic_write_text(gamelist, content)
        _log(f"created {gamelist} with full Pocket Curator entry")
        return True

    # Case B: file exists. Parse and inspect.
    try:
        tree = ET.parse(gamelist)
    except ET.ParseError as exc:
        _log(f"refusing to modify malformed {gamelist}: {exc}")
        return False

    root = tree.getroot()
    if root.tag != "gameList":
        _log(f"unexpected root <{root.tag}> in {gamelist}; not touching")
        return False

    our_game = _find_our_game(root)

    if our_game is None:
        _append_full_entry(root)
        _atomic_write_tree(gamelist, tree)
        _log(f"added full Pocket Curator entry to {gamelist}")
        return True

    # Per-field merge against existing entry
    added = _merge_missing_fields(our_game)
    if added:
        _atomic_write_tree(gamelist, tree)
        _log(f"wrote/updated fields {added} in {gamelist}")
        return True

    return False


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _find_our_game(root: ET.Element) -> Optional[ET.Element]:
    """Return the <game> element whose <path> matches Pocket Curator, or None."""
    for game in root.findall("game"):
        path = game.find("path")
        if path is not None and (path.text or "").strip() == POCKET_CURATOR_PATH:
            return game
    return None


def _merge_missing_fields(game_elem: ET.Element) -> "list[str]":
    """
    For each field in OUR_FIELDS:
      - if the child element doesn't exist, add it with our value
      - if it exists but its text differs from our canonical value
        (empty, old artwork path, outdated genre, etc.), overwrite it
      - if it already matches our canonical value, leave it alone

    Our managed fields are authoritative for our own port: when we ship
    updated metadata (new artwork, video, release date...), the change
    propagates to installs that already have older values. We only ever
    touch fields in OUR_FIELDS - elements ES maintains (playcount,
    lastplayed, gametime, md5, scrap, ...) are never read or modified.

    Returns the list of field names that were changed (empty == no-op).
    """
    changed: "list[str]" = []

    # Detect indentation style from existing children so new additions
    # don't look out of place.
    children = list(game_elem)
    if children:
        inner_indent = children[0].tail or "\n\t\t"
        closing_indent = children[-1].tail or "\n\t"
    else:
        inner_indent = "\n\t\t"
        closing_indent = "\n\t"

    for field_name, field_value in OUR_FIELDS.items():
        existing = game_elem.find(field_name)

        if existing is not None and (existing.text or "").strip() == field_value:
            # Already matches our canonical value - nothing to do.
            continue

        if existing is None:
            # The child that's currently last becomes a non-last child,
            # so its tail goes from "closing" to "inner". Then we append
            # a new child whose tail becomes the new "closing".
            current_children = list(game_elem)
            if current_children:
                current_children[-1].tail = inner_indent
            new_child = ET.SubElement(game_elem, field_name)
            new_child.text = field_value
            new_child.tail = closing_indent
        else:
            # Element exists but is empty or holds a stale value: set ours.
            existing.text = field_value

        changed.append(field_name)

    return changed


def _build_fresh_file() -> str:
    """
    Build a brand-new gamelist.xml containing only our entry. Used when
    no file exists yet. Hand-built text for clean formatting.
    """
    lines = ["<?xml version=\"1.0\"?>", "<gameList>", "\t<game>",
             f"\t\t<path>{POCKET_CURATOR_PATH}</path>"]
    for field_name, field_value in OUR_FIELDS.items():
        # Escape XML special characters in the value
        escaped = _xml_escape(field_value)
        lines.append(f"\t\t<{field_name}>{escaped}</{field_name}>")
    lines.extend(["\t</game>", "</gameList>", ""])
    return "\n".join(lines)


def _append_full_entry(root: ET.Element) -> None:
    """
    Add a complete new <game> element to root with all our fields. The
    other entries in the file are untouched.
    """
    # Detect indentation style from existing children
    existing_games = list(root.findall("game"))
    if existing_games:
        game_indent = existing_games[0].tail or "\n\t"
        first = existing_games[0]
        first_children = list(first)
        if first_children:
            inner_indent = first_children[0].tail or "\n\t\t"
            close_indent = first_children[-1].tail or "\n\t"
        else:
            inner_indent = "\n\t\t"
            close_indent = "\n\t"
    else:
        # Root has no <game> children at all
        game_indent = "\n\t"
        inner_indent = "\n\t\t"
        close_indent = "\n\t"
        if root.text is None or not root.text.strip():
            root.text = game_indent

    # The previous last game's tail goes from "before </gameList>" to "between games"
    if existing_games:
        existing_games[-1].tail = game_indent

    new_game = ET.SubElement(root, "game")
    new_game.tail = "\n"  # before </gameList>

    # Children: <path> first, then OUR_FIELDS in order
    path_elem = ET.SubElement(new_game, "path")
    path_elem.text = POCKET_CURATOR_PATH

    field_list = list(OUR_FIELDS.items())
    children_to_add = [("path", POCKET_CURATOR_PATH)] + field_list

    # Re-add path properly and add all the fields
    # (We need to clear and rebuild since we appended <path> as a probe above)
    for child in list(new_game):
        new_game.remove(child)

    new_game.text = inner_indent  # whitespace before first child
    for i, (name, value) in enumerate(children_to_add):
        c = ET.SubElement(new_game, name)
        c.text = value
        is_last = (i == len(children_to_add) - 1)
        c.tail = close_indent if is_last else inner_indent


def _xml_escape(text: str) -> str:
    """Escape XML special characters in text."""
    return (text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;"))


def _atomic_write_text(target: Path, content: str) -> None:
    """Write text content to target via temp file + rename."""
    tmp = target.with_name(target.name + ".pcr-tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, target)


def _atomic_write_tree(target: Path, tree: ET.ElementTree) -> None:
    """Write ElementTree to target via temp file + rename."""
    tmp = target.with_name(target.name + ".pcr-tmp")
    tree.write(tmp, encoding="utf-8", xml_declaration=True)
    os.replace(tmp, target)
