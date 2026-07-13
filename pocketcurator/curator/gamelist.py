"""
Parser for EmulationStation gamelist.xml files.

We accept the format variations that show up in the wild:
    - <rating> as a float 0.0-1.0 (ES standard)
    - <rating> as "4.5/5" or "85%" (some scrapers)
    - <region> tag, OR region embedded in the filename "(USA)", "(Europe)"
    - relative media paths starting with "./", or with absolute "/roms/..."

This module is the READ path: it only parses gamelist.xml and never
writes it. The two places allowed to write a gamelist are
ports_gamelist.py (Pocket Curator's own Ports entry) and
gamelist_merge.py (carrying a fetched game's scraped metadata into its
destination system); neither is reached from here. Deletions performed
in the app are surfaced to ES by triggering a reload/refresh on exit,
not by rewriting other systems' gamelists in place.
"""

from __future__ import annotations

import os
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


# Filename region codes recognised by ScreenScraper/no-intro filenames.
_REGION_HINTS = {
    "usa": "USA",
    "us": "USA",
    "u": "USA",
    "europe": "EUR",
    "eur": "EUR",
    "e": "EUR",
    "japan": "JPN",
    "jpn": "JPN",
    "jp": "JPN",
    "j": "JPN",
    "world": "WLD",
    "w": "WLD",
    "germany": "GER",
    "ger": "GER",
    "france": "FRA",
    "fra": "FRA",
    "spain": "SPA",
    "spa": "SPA",
    "italy": "ITA",
    "ita": "ITA",
    "korea": "KOR",
    "kor": "KOR",
    "australia": "AUS",
    "aus": "AUS",
    "brazil": "BRA",
    "bra": "BRA",
}


@dataclass
class Game:
    """A single game entry, normalised for the UI to consume."""
    rom_path: Path                          # absolute path to the ROM file
    name: str                                # display name
    desc: str = ""                           # description / synopsis
    image: Optional[Path] = None             # boxart or hero image
    thumbnail: Optional[Path] = None
    marquee: Optional[Path] = None
    video: Optional[Path] = None
    manual: Optional[Path] = None
    rating: Optional[float] = None           # normalised 0.0..1.0
    region: Optional[str] = None             # short code, e.g. "USA"
    genre: Optional[str] = None
    developer: Optional[str] = None
    publisher: Optional[str] = None
    releasedate: Optional[str] = None        # raw string from xml
    extra_media: List[Path] = field(default_factory=list)  # populated by media.py

    @property
    def has_image(self) -> bool:
        return self.image is not None and self.image.exists()


def load_gamelist(system_dir: Path,
                  rom_extensions: Optional[List[str]] = None) -> List[Game]:
    """
    Parse the gamelist.xml in ``system_dir`` and return the games it
    lists, minus any whose ROM file no longer exists on disk.

    gamelist.xml is treated as the single source of truth. Files on disk
    that aren't in the gamelist are NOT surfaced as games - that's the
    firmware's "orphan cleanup" feature's job, not ours. This keeps us
    out of the business of guessing what's a ROM vs a save state vs a
    BIOS file vs a scraper cache.

    The one filesystem touch we keep is the ghost filter: gamelist
    entries whose <path> file is gone. That set grows as the user
    deletes ROMs in this session (the on-disk gamelist.xml for other
    systems isn't rewritten until EmulationStation reloads, which Pocket
    Curator triggers on exit). Filtering ghosts here is what stops
    freshly-deleted games from reappearing in the list mid-session.

    The ``rom_extensions`` parameter is accepted but ignored; kept in
    the signature so callers don't have to change.

    Returns a list sorted by display name.
    """
    games: dict[str, Game] = {}  # keyed by resolved rom path string
    t_start = time.monotonic()

    xml_path = system_dir / "gamelist.xml"
    t_parse = time.monotonic()
    if xml_path.is_file():
        try:
            for game in _parse_xml(xml_path, system_dir):
                games[str(game.rom_path)] = game
        except ET.ParseError as exc:
            print(f"[gamelist] {xml_path}: parse error {exc}")
    t_parse = time.monotonic() - t_parse

    # Ghost filter: drop entries whose ROM file is gone. One scandir
    # per unique parent directory, no recursion.
    t_filter = time.monotonic()
    existing = _files_in_parents_of(games.values())
    alive = [g for g in games.values() if str(g.rom_path) in existing]
    dropped = len(games) - len(alive)
    if dropped:
        print(f"[gamelist] dropped {dropped} entries with missing ROM file "
              f"under {system_dir.name}")
        # Name them. A gamelist entry with no ROM behind it is exactly
        # the drift that makes our count disagree with ES (ES hides
        # these; a raw entry count does not), so knowing WHICH games are
        # affected is the difference between diagnosing and guessing.
        # Capped so a badly-out-of-sync system can't flood the log.
        missing = [g for g in games.values() if str(g.rom_path) not in existing]
        for g in missing[:25]:
            print(f"[gamelist]   no ROM on disk: {g.rom_path}")
        if len(missing) > 25:
            print(f"[gamelist]   ... and {len(missing) - 25} more")
    t_filter = time.monotonic() - t_filter

    t_total = time.monotonic() - t_start
    print(f"[gamelist] {system_dir.name}: "
          f"parsed={t_parse * 1000:.0f}ms, "
          f"ghost_filter={t_filter * 1000:.0f}ms, "
          f"total={t_total * 1000:.0f}ms, "
          f"games={len(alive)}")

    return sorted(alive, key=lambda g: g.name.lower())


def _files_in_parents_of(games) -> set:
    """
    Return a set of every file path that lives in any directory that
    contains at least one of the supplied games' rom_paths. One
    scandir() per unique parent directory, no recursion. ROMs almost
    always sit at one or two unique paths under a system dir, so this
    is essentially a constant-time operation regardless of game count.
    """
    parents = set()
    for g in games:
        parents.add(g.rom_path.parent)

    out: set = set()
    for parent in parents:
        try:
            with os.scandir(parent) as it:
                for entry in it:
                    try:
                        if entry.is_file(follow_symlinks=False):
                            out.add(entry.path)
                    except OSError:
                        continue
        except OSError:
            continue
    return out


def _parse_xml(xml_path: Path, system_dir: Path) -> List[Game]:
    tree = ET.parse(xml_path)
    root = tree.getroot()
    out: List[Game] = []

    for elem in root.findall("game"):
        path_text = _text(elem, "path")
        if not path_text:
            continue

        rom = _resolve(path_text, system_dir)
        if rom is None:
            continue

        name = _text(elem, "name") or rom.stem
        desc = _text(elem, "desc") or ""

        # Rating: ES uses 0.0-1.0 float. Tolerate "4.5/5" and "85%".
        rating = _parse_rating(_text(elem, "rating"))

        region = (_text(elem, "region")
                  or _guess_region_from_name(name)
                  or _guess_region_from_name(path_text))
        if region:
            region = _REGION_HINTS.get(region.strip().lower(), region.upper()[:3])

        out.append(Game(
            rom_path=rom,
            name=name,
            desc=desc,
            image=_resolve(_text(elem, "image"), system_dir),
            thumbnail=_resolve(_text(elem, "thumbnail"), system_dir),
            marquee=_resolve(_text(elem, "marquee"), system_dir),
            video=_resolve(_text(elem, "video"), system_dir),
            manual=_resolve(_text(elem, "manual"), system_dir),
            rating=rating,
            region=region,
            genre=_text(elem, "genre"),
            developer=_text(elem, "developer"),
            publisher=_text(elem, "publisher"),
            releasedate=_text(elem, "releasedate"),
        ))

    return out


def _text(elem: ET.Element, tag: str) -> Optional[str]:
    child = elem.find(tag)
    if child is None or child.text is None:
        return None
    return child.text.strip() or None


def _resolve(value: Optional[str], system_dir: Path) -> Optional[Path]:
    """
    Resolve a gamelist path entry to an absolute path.

    Gamelist entries are usually ``./images/foo.png`` (relative to the
    system dir) but absolute paths show up in scraped data from older tools.

    Performance note: do NOT call ``Path.resolve()`` here. resolve() does
    a stat() per path component to follow symlinks, which on slow SD
    cards costs ~5 stat calls per path. Multiplied by ~6 paths per game
    and 1500 games, that's ~45k stat calls and 30+ seconds of wall time
    just parsing a gamelist. The constructed path is already absolute
    (system_dir is absolute) and that's all we need.
    """
    if not value:
        return None
    p = Path(value)
    if p.is_absolute():
        return p
    # Strip leading "./" that ES always writes
    if value.startswith("./"):
        value = value[2:]
    return system_dir / value


def _parse_rating(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    s = value.strip()
    # "4.5/5" -> 0.9
    m = re.match(r"^([\d.]+)\s*/\s*([\d.]+)$", s)
    if m:
        try:
            num = float(m.group(1))
            den = float(m.group(2))
            return max(0.0, min(1.0, num / den)) if den > 0 else None
        except ValueError:
            return None
    # "85%" -> 0.85
    if s.endswith("%"):
        try:
            return max(0.0, min(1.0, float(s[:-1]) / 100.0))
        except ValueError:
            return None
    # plain float - ES standard is 0.0..1.0
    try:
        v = float(s)
    except ValueError:
        return None
    if v > 1.0:
        # Some scrapers store 0..5 or 0..10. Heuristic normalise.
        if v <= 5.0:
            return v / 5.0
        if v <= 10.0:
            return v / 10.0
        if v <= 100.0:
            return v / 100.0
    return max(0.0, min(1.0, v))


def _guess_region_from_name(name: str) -> Optional[str]:
    """Pull the first parenthesised region hint out of a filename-style title."""
    for token in re.findall(r"\(([^)]+)\)", name):
        key = token.strip().lower()
        if key in _REGION_HINTS:
            return key
    return None
