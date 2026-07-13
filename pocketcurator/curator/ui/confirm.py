"""
Confirmation modal for batch deletion. Renders semi-transparent over the
underlying screen and gates the actual filesystem unlinking.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, List, Optional

import pygame

from ..deleter import delete_paths
from ..gamelist import Game
from ..gamelist_merge import backup_gamelist, prune_entries
from ..media import (
    gather_files_to_delete_batch,
    humanize_bytes,
    total_bytes,
)


class ConfirmDeleteScreen:
    """
    Modal-style overlay. Computes the deletion plan once at construction
    so the user sees an accurate byte count before they confirm.
    """

    def __init__(self,
                 app,
                 system: dict,
                 games_to_delete: List[Game],
                 on_committed: Optional[Callable[[List[Game]], None]] = None,
                 on_cancelled: Optional[Callable[[], None]] = None,
                 scope: str = "games"):
        """
        scope:
            "games"  - delete only the selected games and their media
                       (per-game flow from the game list screen)
            "system" - delete every game in the system plus the
                       gamelist.xml itself (called from the carousel
                       via X). The confirmation message is louder.
        """
        self.app = app
        self.system = system
        self.games = games_to_delete
        self.on_committed = on_committed
        self.on_cancelled = on_cancelled
        self.scope = scope

        # Build the deletion plan up-front. Batch gather scans each
        # media dir once instead of once-per-game, which on slow SD
        # cards is the difference between sub-second and several seconds.
        beh = app.config.get("behavior", {})
        plans = gather_files_to_delete_batch(
            games_to_delete, system["path"],
            include_scraped_media=beh.get("include_scraped_media", True),
        )
        self._plan: List[tuple] = list(zip(games_to_delete, plans))

        # The deletion plan never includes gamelist.xml itself - we only
        # remove ROMs and their referenced media. EmulationStation is
        # refreshed automatically on exit (in-place reload), which drops
        # the now-missing entries from the menu.
        self._extra_files: List[Path] = []

        all_files: List[Path] = [p for _, files in self._plan for p in files]
        all_files.extend(self._extra_files)
        self._total_bytes = total_bytes(all_files)
        self._total_files = len(all_files)

        self._busy = False
        self._result_summary: Optional[str] = None

    def handle_event(self, event: pygame.event.Event) -> None:
        if self._busy:
            return
        if event.type != pygame.KEYDOWN:
            return

        if event.key == pygame.K_ESCAPE:
            if self._result_summary is not None:
                # Already finished; closing dismisses
                self.app.pop_screen()
            else:
                self._cancel()
        elif event.key == pygame.K_RETURN:
            if self._result_summary is not None:
                # Confirmation of the finished state
                self.app.pop_screen()
            else:
                self._commit()
        elif event.key == pygame.K_x:
            # X also commits in case the user reflexively re-presses it
            if self._result_summary is None:
                self._commit()

    def _cancel(self) -> None:
        if self.on_cancelled:
            self.on_cancelled()
        self.app.pop_screen()

    def _commit(self) -> None:
        self._busy = True
        dry = bool(self.app.config.get("behavior", {})
                   .get("deletion_dry_run", False))

        total_games = len(self._plan)
        file_deleted = file_failed = file_skipped = 0
        deleted_games: List[Game] = []
        failed_games: List[Game] = []

        print(f"[delete] start system={self.system.get('shortname')} "
              f"games={total_games} dry_run={dry}")

        # Delete per-game (synchronously - so this can never be interrupted
        # by a normal exit, which is blocked while we're in here), drawing
        # progress as we go. A frozen dialog during an 800-game batch is
        # exactly what gets force-quit mid-delete, stranding ROMs; showing
        # live progress stops that.
        for idx, (game, files) in enumerate(self._plan, start=1):
            result = delete_paths(list(files), dry_run=dry)
            file_deleted += len(result.deleted)
            file_failed += len(result.failed)
            file_skipped += len(result.skipped)
            # A game is "removed" when its ROM is actually gone afterwards
            # (or, in a dry run, would have been). Checking the ROM itself
            # - not merely "no failures" - means a media-only hiccup never
            # keeps a successfully-removed ROM in the list, and a genuine
            # ROM-unlink failure is never reported as success.
            rom_gone = dry or not (game.rom_path and game.rom_path.exists())
            if rom_gone:
                deleted_games.append(game)
            else:
                failed_games.append(game)
                print(f"[delete] ROM NOT removed: {game.rom_path}")
            if idx == 1 or idx % 8 == 0 or idx == total_games:
                self._draw_deleting(idx, total_games)

        print(f"[delete] done system={self.system.get('shortname')} "
              f"games_marked={total_games} games_removed={len(deleted_games)} "
              f"games_failed={len(failed_games)} files_deleted={file_deleted} "
              f"files_skipped={file_skipped} files_failed={file_failed}")

        # Keep gamelist.xml TRUE. It is the source of truth - for ES and
        # for us - so a ROM we removed must not keep its <game> entry, or
        # the system count reads high and the dead entry lingers. Prune
        # only the games whose ROM is really gone; a failed delete keeps
        # its entry, exactly as it should. Backup first (same convention
        # as a fetch merge), and never let a gamelist problem undo the
        # deletion that already succeeded. ES picks the change up via the
        # reload/refresh Pocket Curator already triggers on exit.
        pruned = 0
        if not dry and deleted_games:
            try:
                backup_gamelist(Path(self.app.port_dir), self.system)
                pruned = prune_entries(
                    Path(self.system["path"]),
                    [g.rom_path for g in deleted_games],
                )
            except Exception as exc:  # noqa: BLE001
                print(f"[delete] gamelist prune failed (ROMs are still "
                      f"deleted): {exc}")
        print(f"[delete] gamelist entries pruned={pruned}")

        # Flag for the launcher's exit-time ES refresh: only when this was
        # a real run that actually removed something.
        if not dry and file_deleted:
            self.app.deletions_occurred = True

        # Prune ONLY the games actually removed. Anything that failed stays
        # visible instead of silently vanishing from the view and then
        # reappearing next session (the old code removed every marked game
        # regardless of whether its file was really deleted).
        if self.on_committed:
            self.on_committed(deleted_games)

        if dry:
            summary = (f"Dry run complete.\n"
                       f"Would have removed {len(deleted_games)} game"
                       f"{'s' if len(deleted_games) != 1 else ''} "
                       f"({humanize_bytes(self._total_bytes)}).")
        elif failed_games:
            summary = (f"Removed {len(deleted_games)} of {total_games} "
                       f"game{'s' if total_games != 1 else ''} "
                       f"({file_deleted} files).\n"
                       f"{len(failed_games)} could NOT be removed - see the "
                       f"newest PC_*.log.")
        else:
            extra = f" ({file_skipped} already gone)" if file_skipped else ""
            summary = (f"Removed {len(deleted_games)} game"
                       f"{'s' if len(deleted_games) != 1 else ''} "
                       f"({file_deleted} files){extra}.\n"
                       f"Freed approximately {humanize_bytes(self._total_bytes)}.")

        self._result_summary = summary
        self._busy = False

    def _draw_deleting(self, done: int, total: int) -> None:
        """Live progress while a delete batch runs. Called from _commit on
        the main thread; flips the display directly so the user sees the
        batch advancing instead of a frozen confirm dialog."""
        surface = self.app.surface
        theme = self.app.config["theme"]
        base = self.app.config["ui"]["font_size_base"]
        overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 210))
        surface.blit(overlay, (0, 0))
        title_font = self.app.fonts.get(int(base * 1.2))
        body_font = self.app.fonts.get(base)
        small_font = self.app.fonts.get(max(11, int(base * 0.75)))
        cx = surface.get_width() // 2
        cy = surface.get_height() // 2
        t = title_font.render("Deleting...", True, tuple(theme["text_color"]))
        surface.blit(t, (cx - t.get_width() // 2, cy - t.get_height() - 24))
        c = body_font.render(f"{done} / {total}", True,
                             tuple(theme["text_color"]))
        surface.blit(c, (cx - c.get_width() // 2, cy - c.get_height() // 2))
        bar_w = min(surface.get_width() - 120, 600)
        bar = pygame.Rect(cx - bar_w // 2, cy + 24, bar_w, 10)
        pygame.draw.rect(surface, tuple(theme["muted_color"]), bar, 1)
        if total:
            fill = pygame.Rect(bar.x, bar.y, int(bar_w * done / total), 10)
            pygame.draw.rect(surface, tuple(theme["highlight_color"]), fill)
        w = small_font.render("Do not power off until this finishes.", True,
                              tuple(theme["accent_color"]))
        surface.blit(w, (cx - w.get_width() // 2, bar.bottom + 16))
        self.app._present()

    def draw(self, surface: pygame.Surface) -> None:
        # Render whatever is below us, then a darkened overlay.
        below = self.app.screen_below(self)
        if below is not None:
            below.draw(surface)

        overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        surface.blit(overlay, (0, 0))

        cfg = self.app.config
        theme = cfg["theme"]
        ui = cfg["ui"]

        # Box size scales with the current font so the dialog actually
        # holds the text on high-res screens. Old hard caps (720x360)
        # were tuned for 480p and overflow on 1920x1152.
        base = ui["font_size_base"]
        target_w = max(720, base * 36)
        target_h = max(360, base * 18)
        box_w = min(target_w, surface.get_width() - 80)
        box_h = min(target_h, surface.get_height() - 80)
        box = pygame.Rect(
            (surface.get_width() - box_w) // 2,
            (surface.get_height() - box_h) // 2,
            box_w, box_h,
        )
        pygame.draw.rect(surface, tuple(theme["panel_bg_color"]), box)
        pygame.draw.rect(surface, tuple(theme["highlight_color"]), box, width=2)

        title_font = self.app.fonts.get(int(base * 1.2))
        body_font = self.app.fonts.get(base)
        small_font = self.app.fonts.get(max(11, int(base * 0.75)))

        pad = max(24, base)
        y = box.y + pad

        if self._result_summary is not None:
            # Post-deletion result
            title = title_font.render("Done", True, tuple(theme["text_color"]))
            surface.blit(title, (box.x + pad, y))
            y += title.get_height() + 12
            for line in self._result_summary.split("\n"):
                surf = body_font.render(line, True, tuple(theme["text_color"]))
                surface.blit(surf, (box.x + pad, y))
                y += surf.get_height() + 4
            hint = small_font.render("Press A or B to continue.",
                                     True, tuple(theme["muted_color"]))
            surface.blit(hint, (box.x + pad,
                                box.bottom - hint.get_height() - pad))
            return

        # Confirm prompt - title varies by scope
        if self.scope == "system":
            title_text = f"Delete entire {self.system['display']}?"
        else:
            title_text = "Delete games?"
        title = title_font.render(title_text, True,
                                  tuple(theme["accent_color"]
                                        if self.scope == "system"
                                        else theme["text_color"]))
        surface.blit(title, (box.x + pad, y))
        y += title.get_height() + 12

        if self.scope == "system":
            line1 = body_font.render(
                f"This will remove ALL {len(self.games)} game"
                f"{'s' if len(self.games) != 1 else ''}",
                True, tuple(theme["text_color"]))
            surface.blit(line1, (box.x + pad, y))
            y += line1.get_height() + 4
            line1b = body_font.render(
                f"in {self.system['display']} and their scraped media.",
                True, tuple(theme["text_color"]))
            surface.blit(line1b, (box.x + pad, y))
            y += line1b.get_height() + 6
        else:
            line1 = body_font.render(
                f"{len(self.games)} game{'s' if len(self.games) != 1 else ''} "
                f"flagged in {self.system['display']}.",
                True, tuple(theme["text_color"]))
            surface.blit(line1, (box.x + pad, y))
            y += line1.get_height() + 6

        line2 = body_font.render(
            f"This will remove {self._total_files} file"
            f"{'s' if self._total_files != 1 else ''} "
            f"({humanize_bytes(self._total_bytes)}).",
            True, tuple(theme["text_color"]))
        surface.blit(line2, (box.x + pad, y))
        y += line2.get_height() + 16

        # First few names
        sample_font = small_font
        sample_h = sample_font.get_linesize()
        # Compute how many lines fit
        available_h = box.bottom - pad - 40 - y
        max_lines = max(1, available_h // sample_h)
        names = [g.name for g in self.games]
        if len(names) <= max_lines:
            shown = names
        else:
            shown = names[:max_lines - 1] + [f"\u2026 and {len(names) - (max_lines - 1)} more"]
        for nm in shown:
            surf = sample_font.render("- " + nm, True,
                                      tuple(theme["muted_color"]))
            surface.blit(surf, (box.x + pad, y))
            y += sample_h

        # Footer
        if self.app.config.get("behavior", {}).get("deletion_dry_run"):
            warn = small_font.render("(Dry run mode - nothing will actually be deleted)",
                                     True, tuple(theme["accent_color"]))
            surface.blit(warn,
                         (box.x + pad, box.bottom - warn.get_height() - pad - 24))

        hint = body_font.render("A / X: confirm   -   B: cancel",
                                True, tuple(theme["text_color"]))
        surface.blit(hint, (box.x + pad, box.bottom - hint.get_height() - pad))
