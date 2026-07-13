"""
Firmware roms-folder matrix.

system_matrix.csv is the authoritative map from a Pocket Curator system
ID to the actual roms/ folder each firmware uses, plus the regional
display names. It exists because every firmware names its folders a
little differently (Batocera uses ``megadrive`` and ``jaguar`` where
ROCKNIX uses ``genesis`` and ``atarijaguar``; Batocera splits Amiga into
``amiga500``/``amiga1200``), and guessing with a flat alias list kept
sending fetched games to the wrong place - or refusing them outright.

The CSV is human-maintained (hand-corrected against each firmware's
docs). This module just loads it and answers two questions:

  * For a remote folder/system name, what is this device's roms folder?
  * What are the alias names a given Pocket Curator system answers to?

If the CSV is missing or unreadable we degrade gracefully to an empty
matrix and the caller falls back to its built-in alias groups, so a
packaging slip can never break fetch entirely.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, List, Optional

FIRMWARE_COLUMNS = ("rocknix", "knulli", "darkos", "amberelec", "batocera")

# Regions we route by. Everything a device might report collapses into
# one of these three buckets.
_REGION_BUCKETS = {
    "na": "na", "us": "na", "usa": "na", "ntsc": "na", "ca": "na",
    "eu": "eu", "europe": "eu", "pal": "eu", "world": "eu", "uk": "eu",
    "fr": "eu", "de": "eu", "es": "eu", "it": "eu", "pt": "eu",
    "nl": "eu", "se": "eu", "au": "eu", "br": "eu",
    "jp": "jp", "jpn": "jp", "japan": "jp", "asia": "jp", "kr": "jp",
    "korea": "jp", "cn": "jp", "china": "jp", "tw": "jp",
}


def region_bucket(region: Optional[str]) -> Optional[str]:
    """Collapse an ES/theme region string into na / eu / jp, or None when
    we can't tell. None is meaningful: it means 'don't guess', and the
    caller falls back to matching the folder name literally."""
    if not region:
        return None
    return _REGION_BUCKETS.get(str(region).strip().lower())


def norm(name: str) -> str:
    """Fold a system/folder name to its comparable form: lowercase, and
    punctuation removed. 'PC-Engine', 'pc engine', 'PC_Engine' and
    'pcengine' are the same system; so are 'tg-16' and 'tg16'. Without
    this, every server folder someone names with a hyphen or a space is
    a fresh routing failure."""
    return "".join(ch for ch in (name or "").lower() if ch.isalnum())

# Map the firmware NAME the launcher reports -> the CSV column.
_FIRMWARE_ALIASES = {
    "rocknix": "rocknix",
    "jelos": "rocknix",          # JELOS shares ROCKNIX folder conventions
    "knulli": "knulli",
    "darkos": "darkos",
    "arkos": "darkos",
    "amberelec": "amberelec",
    "batocera": "batocera",
}


def _csv_path() -> Path:
    return Path(__file__).resolve().parent / "system_matrix.csv"


class SystemMatrix:
    def __init__(self, rows: List[dict]):
        self._rows = rows
        # normalised name -> row.
        #
        # TWO PASSES, and the order matters. Real names (pc_id, firmware
        # folder names) claim their keys FIRST; aliases only fill the
        # gaps afterwards. Otherwise an alias steals a name that belongs
        # to a genuine row: `pcengine` lists `tg16` among its aliases, so
        # a single pass could make row_for("tg16") return the PC Engine
        # row - and with it the PC Engine's regions (eu,jp), which would
        # send a US device's TurboGrafx games to the wrong folder.
        self._by_name: Dict[str, dict] = {}
        for row in rows:                        # tier 1: canonical ids
            key = norm(row.get("pc_id") or "")
            if key:
                self._by_name.setdefault(key, row)
        for row in rows:                        # tier 2: firmware folders
            for col in FIRMWARE_COLUMNS:
                key = norm(row.get(col) or "")
                if key:
                    self._by_name.setdefault(key, row)
        for row in rows:                        # tier 3: aliases
            for n in (row.get("aliases") or "").split():
                key = norm(n)
                if key:
                    self._by_name.setdefault(key, row)

    # ------------------------------------------------------------------

    def row_for(self, name: str) -> Optional[dict]:
        return self._by_name.get(norm(name))

    def family_for(self, name: str) -> Optional[str]:
        """The hardware family a name belongs to - the thing that makes
        'genesis' and 'megadrive' the same console under two regional
        names. Only families whose firmwares ship BOTH folders carry a
        value; everything else is empty (no routing decision to make)."""
        row = self.row_for(name)
        if row is None:
            return None
        return (row.get("family") or "").strip().lower() or None

    def regions_for(self, name: str) -> List[str]:
        """Regions for which this folder is the right destination, e.g.
        genesis -> ['na'], megadrive -> ['eu', 'jp']."""
        row = self.row_for(name)
        if row is None:
            return []
        raw = (row.get("regions") or "").strip().lower()
        return [r.strip() for r in raw.split(",") if r.strip()]

    def family_members(self, family: str) -> List[dict]:
        fam = (family or "").strip().lower()
        if not fam:
            return []
        return [r for r in self._rows
                if (r.get("family") or "").strip().lower() == fam]

    @classmethod
    def load(cls) -> "SystemMatrix":
        rows: List[dict] = []
        try:
            with _csv_path().open(newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    rows.append(row)
        except (OSError, csv.Error):
            rows = []
        return cls(rows)

    # ------------------------------------------------------------------

    def folder_for(self, name: str, firmware: str) -> Optional[str]:
        """The roms-folder leaf this FIRMWARE uses for the system that
        ``name`` refers to (name may be a pc_id or any firmware's folder
        name). Returns None if the matrix has no row, or the firmware
        column is blank (system not supported on that firmware)."""
        if not name:
            return None
        row = self._by_name.get(norm(name))
        if row is None:
            return None
        col = _FIRMWARE_ALIASES.get((firmware or "").strip().lower())
        if col is None:
            return None
        leaf = (row.get(col) or "").strip()
        return leaf or None

    def aliases_for(self, name: str) -> List[str]:
        """Every folder name (across all firmwares) plus the pc_id that
        refer to the same system as ``name``. Used to broaden matching of
        a remote folder against the device's systems."""
        row = self._by_name.get(norm(name))
        if row is None:
            return []
        names = set()
        pc_id = (row.get("pc_id") or "").strip().lower()
        if pc_id:
            names.add(pc_id)
        for col in FIRMWARE_COLUMNS:
            v = (row.get(col) or "").strip().lower()
            if v:
                names.add(v)
        # The alias column folds in the locale/nickname names that used to
        # live in a second, hand-maintained list in remote_browser.py -
        # one table now, so the two can't drift apart.
        names |= {a for a in (row.get("aliases") or "").split() if a}
        return sorted(names)

    def known(self) -> bool:
        return bool(self._rows)


_MATRIX: Optional[SystemMatrix] = None


def get_matrix() -> SystemMatrix:
    global _MATRIX
    if _MATRIX is None:
        _MATRIX = SystemMatrix.load()
    return _MATRIX
