"""
The copy confirmation. Shows what's about to transfer (names + sizes +
total) and offers the two copy modes:

    Copy w/ Scrapings     - ROMs plus their images / videos / manuals
    Copy (ROMs only)      - just the ROM files

When some of the marked games already exist in the destination system
folder, a follow-up question offers Overwrite or Skip for those - so
re-fetching a folder you half-own doesn't silently re-download (or
silently clobber) anything.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, List

import pygame

from ..webdav import RemoteEntry, format_size
from .remote_flow import _MenuScreen


class RemoteConfirmScreen(_MenuScreen):
    def __init__(self, app, system: dict, marked: List[RemoteEntry],
                 on_choice: Callable[[bool, bool], None]):
        total = sum(e.size for e in marked)
        super().__init__(
            app,
            f"Copy {len(marked)} game{'s' if len(marked) != 1 else ''} "
            f"to {system['display']}?  ({format_size(total)} + scrapings)")
        self.system = system
        self.marked = marked
        self.on_choice = on_choice
        dest = Path(system["path"])
        self.existing = [e for e in marked if (dest / e.name).exists()]
        self.items = ["Copy w/ Scrapings", "Copy (ROMs only)", "Cancel"]

    def _activate(self, index: int) -> None:
        if index == 2:
            self.app.pop_screen()
            return
        with_media = index == 0
        if self.existing:
            self.app.pop_screen()
            self.app.push_screen(_ExistingScreen(
                self.app, len(self.existing), len(self.marked),
                with_media, self.on_choice))
        else:
            self.app.pop_screen()
            self.on_choice(with_media, False)

    def draw(self, surface: pygame.Surface) -> None:
        names = [f"{e.name}  ({format_size(e.size)})"
                 for e in self.marked[:6]]
        if len(self.marked) > 6:
            names.append(f"...and {len(self.marked) - 6} more")
        note = "   ".join(names)
        if self.existing:
            note = (f"{len(self.existing)} of these are already on this "
                    f"handheld.   " + note)
        self.status = note
        super().draw(surface)


class _ExistingScreen(_MenuScreen):
    """Follow-up: what to do with games already on the device."""

    def __init__(self, app, n_existing: int, n_total: int,
                 with_media: bool, on_choice: Callable[[bool, bool], None]):
        super().__init__(
            app,
            f"{n_existing} of {n_total} are already on this handheld")
        self.with_media = with_media
        self.on_choice = on_choice
        self.items = ["Overwrite Them", "Skip Them", "Cancel"]
        self.status = ("Overwrite replaces the copies on the handheld; "
                       "Skip copies only the games you don't have yet.")

    def _activate(self, index: int) -> None:
        self.app.pop_screen()
        if index == 0:
            self.on_choice(self.with_media, False)
        elif index == 1:
            self.on_choice(self.with_media, True)
