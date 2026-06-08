"""
File deletion. Wrapped in a single function so we can route everything
through one log line, honour the dry-run flag, and surface errors back to
the UI for display.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List


@dataclass
class DeletionResult:
    """Outcome of a delete batch. Always returned, even on partial failure."""
    deleted: List[Path]
    failed: List[tuple]   # list of (Path, error_message)
    skipped: List[Path]   # files that no longer existed

    @property
    def ok(self) -> bool:
        return not self.failed

    @property
    def bytes_freed(self) -> int:
        # Caller already knows; we don't double-stat after deletion.
        return 0


def delete_paths(paths: List[Path], dry_run: bool = False) -> DeletionResult:
    """
    Remove every path in ``paths``. ``dry_run=True`` logs the intended
    removal but doesn't touch the filesystem - useful for the first time
    a user runs the tool on a precious SD card.
    """
    deleted: List[Path] = []
    failed: List[tuple] = []
    skipped: List[Path] = []

    for p in paths:
        try:
            if not p.exists():
                skipped.append(p)
                continue
            if dry_run:
                print(f"[deleter:DRY] would unlink {p}")
                deleted.append(p)
                continue
            if p.is_dir():
                # We never gather directories, but defend in depth.
                failed.append((p, "refused to remove a directory"))
                continue
            p.unlink()
            print(f"[deleter] unlinked {p}")
            deleted.append(p)
        except OSError as exc:
            print(f"[deleter] FAILED {p}: {exc}")
            failed.append((p, str(exc)))

    return DeletionResult(deleted=deleted, failed=failed, skipped=skipped)
