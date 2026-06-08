"""
Jump-to-letter overlay - lets the user jump to the first game whose name starts
with a chosen letter or digit.

This is a "first-letter jump" rather than a full text search. Typing on a
handheld is awkward, and for the curation workflow this app is built for,
"jump to S" is almost always what the user actually wants when they're
in a 1500-game list.

D-pad to move the cursor on the grid. A picks the highlighted letter
and jumps the game list to the first match. B dismisses without jumping.
"""

from __future__ import annotations

from typing import Callable, List, Optional

import pygame


# Two rows of letters + a row of digits. Layout is roughly QWERTY-friendly
# in terms of visual scanning - all letters in alphabetical order in a
# 7-wide grid.
LETTERS: List[str] = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
DIGITS: List[str] = list("0123456789")
SYMBOLS: List[str] = ["#"]  # catches games starting with non-alpha-num


def _build_grid() -> List[List[str]]:
    """Return rows of chars for the picker grid."""
    cols = 7
    rows: List[List[str]] = []
    chars = LETTERS + DIGITS + SYMBOLS
    for i in range(0, len(chars), cols):
        rows.append(chars[i:i + cols])
    return rows


class JumpScreen:
    def __init__(self, app, games, on_pick: Callable[[int], None]):
        self.app = app
        self.games = games
        self.on_pick = on_pick
        self.grid = _build_grid()
        self.row = 0
        self.col = 0

    def handle_event(self, event):
        if event.type != pygame.KEYDOWN:
            return
        if event.key == pygame.K_UP:
            self.row = max(0, self.row - 1)
            self.col = min(self.col, len(self.grid[self.row]) - 1)
        elif event.key == pygame.K_DOWN:
            self.row = min(len(self.grid) - 1, self.row + 1)
            self.col = min(self.col, len(self.grid[self.row]) - 1)
        elif event.key == pygame.K_LEFT:
            if self.col > 0:
                self.col -= 1
            elif self.row > 0:
                self.row -= 1
                self.col = len(self.grid[self.row]) - 1
        elif event.key == pygame.K_RIGHT:
            if self.col < len(self.grid[self.row]) - 1:
                self.col += 1
            elif self.row < len(self.grid) - 1:
                self.row += 1
                self.col = 0
        elif event.key == pygame.K_RETURN:
            self._pick()
        elif event.key == pygame.K_ESCAPE:
            self.app.pop_screen()

    def _selected_char(self) -> str:
        return self.grid[self.row][self.col]

    def _pick(self) -> None:
        target = self._selected_char()
        idx = self._first_match_index(target)
        if idx is not None:
            self.on_pick(idx)
        self.app.pop_screen()

    def _first_match_index(self, ch: str) -> Optional[int]:
        ch_l = ch.lower()
        if ch == "#":
            # Anything that doesn't start with a letter or digit
            for i, g in enumerate(self.games):
                name = g.name.lstrip()
                if name and not (name[0].isalpha() or name[0].isdigit()):
                    return i
            return None
        for i, g in enumerate(self.games):
            name = g.name.lstrip()
            if name and name[0].lower() == ch_l:
                return i
        return None

    def draw(self, surface):
        # Render whatever's below us, then a darkened overlay so the
        # search reads as a transient modal.
        below = self.app.screen_below(self)
        if below is not None:
            below.draw(surface)

        overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        surface.blit(overlay, (0, 0))

        cfg = self.app.config
        theme = cfg["theme"]
        ui = cfg["ui"]

        base = ui["font_size_base"]
        # Box big enough to comfortably hold a 7x4 grid of upscaled
        # letter cells plus title and readout. Old fixed 560x280 cap
        # was tuned for small screens and overflowed on the RG552.
        target_w = max(560, base * 28)
        target_h = max(280, base * 15)
        box_w = min(target_w, surface.get_width() - 48)
        box_h = min(target_h, surface.get_height() - 48)
        box = pygame.Rect(
            (surface.get_width() - box_w) // 2,
            (surface.get_height() - box_h) // 2,
            box_w, box_h,
        )
        pygame.draw.rect(surface, tuple(theme["panel_bg_color"]), box)
        pygame.draw.rect(surface, tuple(theme["highlight_color"]), box, width=2)

        title_font = self.app.fonts.get(int(base * 1.1), bold=True)
        cell_font = self.app.fonts.get(int(base * 1.2), bold=True)
        small_font = self.app.fonts.get(max(11, int(base * 0.70)))

        # Title - reserve header band that scales with the title font
        header_h = title_font.get_height() + 24
        title = title_font.render("Jump to letter", True,
                                  tuple(theme["text_color"]))
        surface.blit(title,
                     (box.x + 16, box.y + 12))

        # Selected-char readout on the right (positioned in the header band)
        sel_char = self._selected_char()
        match_idx = self._first_match_index(sel_char)
        if match_idx is not None:
            preview = self.games[match_idx].name
            if len(preview) > 28:
                preview = preview[:27] + "..."
            readout = f"{sel_char} -> {preview}"
            color = tuple(theme["accent_color"])
        else:
            readout = f"{sel_char} -> (no match)"
            color = tuple(theme["muted_color"])
        rsurf = small_font.render(readout, True, color)
        surface.blit(rsurf,
                     (box.right - rsurf.get_width() - 16,
                      box.y + 12 + (title_font.get_height() - small_font.get_height()) // 2))

        # Grid - starts below the header band, ends above a footer band
        # (we already had ~30px footer reserved via the -80 in the old code;
        # keep that logic by reserving header_h + footer band of similar size).
        footer_h = 30
        rows_n = len(self.grid)
        cols_n = max(len(r) for r in self.grid)
        cell_w = (box_w - 32) // cols_n
        cell_h = max(28, (box_h - header_h - footer_h) // rows_n)
        grid_x = box.x + 16
        grid_y = box.y + header_h

        for r, row in enumerate(self.grid):
            for c, ch in enumerate(row):
                cx = grid_x + c * cell_w
                cy = grid_y + r * cell_h
                cell_rect = pygame.Rect(cx + 2, cy + 2, cell_w - 4, cell_h - 4)
                is_sel = (r == self.row and c == self.col)
                if is_sel:
                    pygame.draw.rect(surface,
                                     tuple(theme["highlight_color"]),
                                     cell_rect)
                    text_color = tuple(theme["highlight_text_color"])
                else:
                    pygame.draw.rect(surface,
                                     tuple(theme["list_bg_color"]),
                                     cell_rect)
                    text_color = tuple(theme["text_color"])
                surf = cell_font.render(ch, True, text_color)
                surface.blit(surf,
                             (cell_rect.centerx - surf.get_width() // 2,
                              cell_rect.centery - surf.get_height() // 2))

        # Hint
        hint = small_font.render(
            "A: jump     -     B: cancel",
            True, tuple(theme["muted_color"]))
        surface.blit(hint,
                     (box.centerx - hint.get_width() // 2,
                      box.bottom - hint.get_height() - 12))
