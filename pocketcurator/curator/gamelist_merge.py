"""
Merge fetched games' metadata into the destination system's
gamelist.xml - so a game copied with its scrapings arrives fully
described (name, description, image, video, rating, genre...) instead
of waiting for a rescrape.

This is the second place in Pocket Curator allowed to write a
gamelist.xml (the first is ports_gamelist.py, our own Ports entry),
and it follows the same proven principles:

- BACKUP FIRST, ALWAYS. Before the first merge touches a system's
  gamelist in a session, the original is copied to
  <port_dir>/backups/gamelists/<system>/gamelist-<timestamp>.xml.
  The three most recent backups per system are kept, and Settings ->
  Restore Gamelist Backup puts one back exactly as it was.
- ADDITIVE ONLY. Entries are inserted for the games we copied; no
  existing entry is modified unless the user explicitly chose
  Overwrite for a game that already existed - and even then only that
  game's entry is replaced.
- ORDERED INSERTION, NEVER A BLIND APPEND. New <game> elements are
  inserted alphabetically by <name> among the existing <game>
  elements (ES sorts its UI itself, but the file's order is preserved
  for the entries the user already had, and ours land where a human
  would file them).
- ATOMIC. Temp file + rename; a crash mid-write can never leave a
  half-written gamelist.
- DEFENSIVE. Every failure is logged and swallowed; a merge problem
  must never break the copy that already succeeded.

Only media-relevant fields are carried over from the source entry:
the source's playcount/lastplayed/favorite and any unknown tags are
dropped, because those describe the SOURCE's history, not this
handheld's.
"""

from __future__ import annotations

import shutil
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Optional

CARRIED_FIELDS = (
    "path", "name", "desc", "rating", "releasedate", "developer",
    "publisher", "genre", "players", "region", "lang",
    "image", "thumbnail", "marquee", "video", "manual",
)
KEEP_BACKUPS = 3


def _log(msg: str) -> None:
    print(f"[gamelist-merge] {msg}")


def backups_root(port_dir: Path) -> Path:
    return Path(port_dir) / "backups" / "gamelists"


def backup_gamelist(port_dir: Path, system: dict) -> Optional[Path]:
    """Copy the system's current gamelist.xml aside. Returns the backup
    path, or None when there's nothing to back up / it failed."""
    gl = Path(system["path"]) / "gamelist.xml"
    if not gl.is_file():
        return None
    dest_dir = backups_root(port_dir) / system["shortname"]
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        dest = dest_dir / f"gamelist-{stamp}.xml"
        shutil.copy2(gl, dest)
        old = sorted(dest_dir.glob("gamelist-*.xml"))
        for stale in old[:-KEEP_BACKUPS]:
            stale.unlink(missing_ok=True)
        _log(f"backed up {system['shortname']} gamelist -> {dest.name}")
        return dest
    except OSError as exc:
        _log(f"backup FAILED for {system['shortname']}: {exc}")
        return None


def list_backups(port_dir: Path) -> List[dict]:
    """[{shortname, path, stamp}] newest-first per system."""
    out: List[dict] = []
    root = backups_root(port_dir)
    if not root.is_dir():
        return out
    for sysdir in sorted(root.iterdir()):
        if not sysdir.is_dir():
            continue
        files = sorted(sysdir.glob("gamelist-*.xml"), reverse=True)
        if files:
            out.append({"shortname": sysdir.name, "path": files[0],
                        "stamp": files[0].stem.replace("gamelist-", "")})
    return out


def restore_backup(system_dir: Path, backup: Path) -> bool:
    """Put a backup back as the live gamelist.xml, atomically."""
    target = Path(system_dir) / "gamelist.xml"
    tmp = target.with_name("gamelist.xml.pc-restore-tmp")
    try:
        shutil.copy2(backup, tmp)
        tmp.replace(target)
        _log(f"restored {target} from {backup.name}")
        return True
    except OSError as exc:
        _log(f"restore FAILED: {exc}")
        tmp.unlink(missing_ok=True)
        return False


# ----------------------------------------------------------------------
# Merging
# ----------------------------------------------------------------------

def _sanitize(source_xml: str) -> Optional[ET.Element]:
    """Parse a source <game> entry and rebuild it with only the fields
    we carry, in canonical order."""
    try:
        src = ET.fromstring(source_xml)
    except ET.ParseError:
        return None
    if src.tag != "game":
        return None
    out = ET.Element("game")
    for tag in CARRIED_FIELDS:
        val = (src.findtext(tag) or "").strip()
        if val:
            ET.SubElement(out, tag).text = val
    if out.find("path") is None:
        return None
    return out


def _entry_name(el: ET.Element) -> str:
    return (el.findtext("name") or el.findtext("path") or "").strip().lower()


def merge_entries(system_dir: Path, entry_xmls: List[str],
                  overwrite: bool) -> int:
    """Insert (or, with overwrite, replace) entries in the system's
    gamelist.xml. Returns how many entries were written."""
    gl = Path(system_dir) / "gamelist.xml"
    try:
        if gl.is_file():
            tree = ET.parse(str(gl))
            root = tree.getroot()
        else:
            root = ET.Element("gameList")
            tree = ET.ElementTree(root)
    except (ET.ParseError, OSError) as exc:
        _log(f"can't read {gl}: {exc} - skipping merge")
        return 0

    existing_by_path = {}
    for g in root.findall("game"):
        p = (g.findtext("path") or "").strip()
        if p:
            existing_by_path[p] = g

    written = 0
    for xml_str in entry_xmls:
        new = _sanitize(xml_str)
        if new is None:
            continue
        path = new.findtext("path").strip()
        old = existing_by_path.get(path)
        if old is not None:
            if not overwrite:
                continue            # user said Skip: their entry stands
            idx = list(root).index(old)
            root.remove(old)
            root.insert(idx, new)   # replace in place, order preserved
            existing_by_path[path] = new
            written += 1
            continue
        # Sorted insertion among the existing <game> elements: before
        # the first game whose name sorts after ours. Non-game children
        # (provider blocks etc.) are left exactly where they are.
        name = _entry_name(new)
        children = list(root)
        insert_at = len(children)
        for i, child in enumerate(children):
            if child.tag == "game" and _entry_name(child) > name:
                insert_at = i
                break
        root.insert(insert_at, new)
        existing_by_path[path] = new
        written += 1

    if not written:
        return 0
    tmp = gl.with_name("gamelist.xml.pc-merge-tmp")
    try:
        tree.write(str(tmp), encoding="utf-8", xml_declaration=True)
        tmp.replace(gl)
        _log(f"wrote {written} entr{'y' if written == 1 else 'ies'} "
             f"into {gl}")
    except OSError as exc:
        _log(f"write FAILED for {gl}: {exc}")
        tmp.unlink(missing_ok=True)
        return 0
    return written
