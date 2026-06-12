"""
The copy confirmation: a short wrapped title, per-option sizes
computed up front, the count of games already on the device, and the
destination's free space along the bottom - with a hard stop when the
selected copy wouldn't fit.

    Copy w/ Scrapings (78.4 MB)
    Copy (ROMs only)  (52.3 MB)
    Cancel

When some marked games already exist in the destination folder, a
follow-up offers Overwrite / Skip for those.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Callable, List

import pygame

from ..webdav import RemoteEntry, format_size
from .remote_flow import _MenuScreen


class RemoteConfirmScreen(_MenuScreen):
    def __init__(self, app, system: dict, marked: List[RemoteEntry],
                 rom_bytes: int, media_bytes: int,
                 on_choice: Callable[[bool, bool], None]):
        super().__init__(
            app,
            f"Copy {len(marked)} game{'s' if len(marked) != 1 else ''} "
            f"to {system['display']}?")
        self.system = system
        self.marked = marked
        self.on_choice = on_choice
        self.rom_bytes = rom_bytes
        self.media_bytes = media_bytes
        dest = Path(system["path"])
        self.existing = [e for e in marked if (dest / e.name).exists()]
        try:
            self.free = shutil.disk_usage(dest).free
        except OSError:
            self.free = None
        self.items = [
            f"Copy w/ Scrapings ({format_size(rom_bytes + media_bytes)})",
            f"Copy (ROMs only) ({format_size(rom_bytes)})",
            "Cancel",
        ]

    def _needed(self, with_media: bool) -> int:
        return self.rom_bytes + (self.media_bytes if with_media else 0)

    def _fits(self, with_media: bool) -> bool:
        return (self.free is None
                or self._needed(with_media) + 32 * 1024 * 1024 <= self.free)

    def _activate(self, index: int) -> None:
        if index == 2:
            self.app.pop_screen()
            return
        with_media = index == 0
        if not self._fits(with_media):
            self.status = (f"NOT ENOUGH SPACE - that copy needs "
                           f"{format_size(self._needed(with_media))} but "
                           f"only {format_size(self.free)} is free.")
            return
        if self.existing:
            self.app.pop_screen()
            self.app.push_screen(_ExistingScreen(
                self.app, self.existing, len(self.marked),
                with_media, self.on_choice))
        else:
            self.app.pop_screen()
            self.on_choice(with_media, False)

    def draw(self, surface: pygame.Surface) -> None:
        if not self.status.startswith("NOT ENOUGH"):
            bits = []
            if self.existing:
                bits.append(f"{len(self.existing)} of these are already "
                            f"on this handheld.")
            if self.free is not None:
                fit = ("" if self._fits(True)
                       else " - scrapings copy will NOT fit")
                bits.append(f"Free space: {format_size(self.free)}{fit}")
            self.status = "   ".join(bits)
        super().draw(surface)


class _ExistingScreen(_MenuScreen):
    """Follow-up: what to do with games already on the device."""

    def __init__(self, app, existing: List[RemoteEntry], n_total: int,
                 with_media: bool, on_choice: Callable[[bool, bool], None]):
        super().__init__(
            app,
            f"{len(existing)} of {n_total} are already on this handheld")
        self.with_media = with_media
        self.on_choice = on_choice
        self.items = ["Overwrite Them", "Skip Them", "Cancel"]
        names = ", ".join(e.name for e in existing[:4])
        if len(existing) > 4:
            names += f", +{len(existing) - 4} more"
        self.status = f"Already here: {names}"

    def _activate(self, index: int) -> None:
        self.app.pop_screen()
        if index == 0:
            self.on_choice(self.with_media, False)
        elif index == 1:
            self.on_choice(self.with_media, True)
