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
        # name (any folder name in any firmware col, plus pc_id) -> row
        self._by_name: Dict[str, dict] = {}
        for row in rows:
            pc_id = (row.get("pc_id") or "").strip().lower()
            if pc_id:
                self._by_name.setdefault(pc_id, row)
            for col in FIRMWARE_COLUMNS:
                val = (row.get(col) or "").strip().lower()
                if val:
                    self._by_name.setdefault(val, row)

    # ------------------------------------------------------------------

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
        row = self._by_name.get(name.strip().lower())
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
        row = self._by_name.get((name or "").strip().lower())
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
        return sorted(names)

    def known(self) -> bool:
        return bool(self._rows)


_MATRIX: Optional[SystemMatrix] = None


def get_matrix() -> SystemMatrix:
    global _MATRIX
    if _MATRIX is None:
        _MATRIX = SystemMatrix.load()
    return _MATRIX
