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
import threading
from pathlib import Path
from typing import Callable, List

import pygame

from ..webdav import RemoteEntry, format_size
from .remote_flow import _MenuScreen


class RemoteConfirmScreen(_MenuScreen):
    def __init__(self, app, system: dict, marked: List[RemoteEntry],
                 rom_bytes: int,
                 on_choice: Callable[[bool, bool], None],
                 media_sizer: Callable[[], int] = None,
                 media_bytes: int = None):
        super().__init__(
            app,
            f"Copy {len(marked)} game{'s' if len(marked) != 1 else ''} "
            f"to {system['display']}?")
        self.system = system
        self.marked = marked
        self.on_choice = on_choice
        self.rom_bytes = rom_bytes
        # media_bytes may be known up front (legacy callers) or computed
        # in the background from media_sizer. None => still calculating.
        self.media_bytes = media_bytes
        self._sizing = media_bytes is None and media_sizer is not None
        dest = Path(system["path"])
        self.existing = [e for e in marked if (dest / e.name).exists()]
        # disk_usage needs an existing path; an empty-but-new system
        # folder may not be on disk yet, so walk up to the nearest
        # real ancestor (the roms mount), which shares the filesystem
        # the copy will land on.
        probe = dest
        while not probe.exists() and probe != probe.parent:
            probe = probe.parent
        try:
            self.free = shutil.disk_usage(probe).free
        except OSError:
            self.free = None
        self._rebuild_items()
        if self._sizing:
            threading.Thread(target=self._compute_media, args=(media_sizer,),
                             daemon=True).start()

    def _rebuild_items(self) -> None:
        if self._sizing or self.media_bytes is None:
            with_scrapings = "Copy w/ Scrapings (Calculating File Sizes...)"
            roms_only = f"Copy (ROMs only) ({format_size(self.rom_bytes)})"
        else:
            with_scrapings = ("Copy w/ Scrapings "
                              f"({format_size(self.rom_bytes + self.media_bytes)})")
            roms_only = f"Copy (ROMs only) ({format_size(self.rom_bytes)})"
        self.items = [with_scrapings, roms_only, "Cancel"]

    def _compute_media(self, sizer: Callable[[], int]) -> None:
        try:
            total = sizer()
        except Exception:  # noqa: BLE001 - sizing must never crash the dialog
            total = 0
        self.media_bytes = max(0, total)
        self._sizing = False
        self._rebuild_items()

    def _needed(self, with_media: bool) -> int:
        media = self.media_bytes or 0
        return self.rom_bytes + (media if with_media else 0)

    def _fits(self, with_media: bool) -> bool:
        if with_media and self.media_bytes is None:
            return True  # unknown yet; don't show a false "won't fit"
        return (self.free is None
                or self._needed(with_media) + 32 * 1024 * 1024 <= self.free)

    def _activate(self, index: int) -> None:
        if index == 2:
            self.app.pop_screen()
            return
        with_media = index == 0
        # Block the scrapings copy until media sizes are known, so we
        # never start a copy we haven't size/fit-checked.
        if with_media and (self._sizing or self.media_bytes is None):
            self.status = "Still calculating file sizes - one moment..."
            return
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
        # While media sizing runs in the background, keep the menu label
        # in sync (Calculating... -> real size) each frame.
        if self._sizing:
            self._rebuild_items()
        if not self.status.startswith("NOT ENOUGH") and not self.status.startswith("Still calculating"):
            bits = []
            if self.existing:
                bits.append(f"{len(self.existing)} of these are already "
                            f"on this handheld.")
            if self.free is not None:
                if self._sizing or self.media_bytes is None:
                    fit = ""
                else:
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
