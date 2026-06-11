"""
The copy confirmation. Shows what's about to transfer (names + sizes +
total) and offers the two copy modes from the design:

    Copy                  - the ROM files only
    Copy w/ Scrapings     - ROMs plus their images / videos / manuals,
                            resolved from the server's gamelist.xml
                            when it has one, else by filename match

Defaults to Copy w/ Scrapings (the thing nearly everyone wants), with
an explicit Cancel - B also backs out, consistent with the whole app.
"""

from __future__ import annotations

from typing import Callable, List

import pygame

from ..webdav import RemoteEntry, format_size
from .remote_flow import _MenuScreen


class RemoteConfirmScreen(_MenuScreen):
    def __init__(self, app, system: dict, marked: List[RemoteEntry],
                 on_choice: Callable[[bool], None]):
        total = sum(e.size for e in marked)
        super().__init__(
            app,
            f"Copy {len(marked)} game{'s' if len(marked) != 1 else ''} "
            f"to {system['display']}?  ({format_size(total)} + scrapings)")
        self.marked = marked
        self.on_choice = on_choice
        self.items = ["Copy w/ Scrapings", "Copy (ROMs only)", "Cancel"]

    def _activate(self, index: int) -> None:
        self.app.pop_screen()
        if index == 0:
            self.on_choice(True)
        elif index == 1:
            self.on_choice(False)

    def draw(self, surface: pygame.Surface) -> None:
        # the file list renders as the status block under the options
        names = [f"{e.name}  ({format_size(e.size)})" for e in self.marked[:6]]
        if len(self.marked) > 6:
            names.append(f"...and {len(self.marked) - 6} more")
        self.status = "   ".join(names)
        super().draw(surface)
