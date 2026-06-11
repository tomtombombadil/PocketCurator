"""
On-screen keyboard. A modal screen that collects a line of text via
d-pad + buttons and hands it to a callback.

Two layout families, toggled with X:

  - "keypad": a numeric pad purpose-built for server addresses, with
    chord keys that type whole fragments in one press - the private
    subnet prefixes ('192.168.', '172.16.', '10.') and the ports file
    servers actually live on (':5005' rclone/Synology WebDAV, ':8080',
    ':80'). Default when the caller is asking for an address.

  - "full": qwerty in three pages (lower / UPPER / symbols), for
    usernames, passwords, and share paths.

Buttons: d-pad moves, A presses the key, B backspaces (hold to clear
faster), X toggles keypad/full, Y cycles shift/symbols on the full
layout, Start = OK, Select/Escape = cancel. mask=True renders dots
(passwords) while keeping the real text.
"""

from __future__ import annotations

from typing import Callable, List, Optional

import pygame

OK, BSP, CANCEL, TOGGLE, SHIFT, SPACE = (
    "\x01OK", "\x01BSP", "\x01CANCEL", "\x01TOGGLE", "\x01SHIFT", "\x01SPC")

KEYPAD: List[List[str]] = [
    ["1", "2", "3", "192.168."],
    ["4", "5", "6", "172.16."],
    ["7", "8", "9", "10."],
    [".", "0", ":", "/"],
    [":5005", ":8080", ":80", BSP],
    [TOGGLE, CANCEL, OK, OK],
]

FULL_LOWER: List[List[str]] = [
    list("1234567890"),
    list("qwertyuiop"),
    list("asdfghjkl-"),
    list("zxcvbnm._/"),
    [SHIFT, SPACE, BSP, TOGGLE, CANCEL, OK],
]
FULL_UPPER: List[List[str]] = [
    list("1234567890"),
    list("QWERTYUIOP"),
    list("ASDFGHJKL_"),
    list("ZXCVBNM:@/"),
    [SHIFT, SPACE, BSP, TOGGLE, CANCEL, OK],
]
FULL_SYMBOL: List[List[str]] = [
    list("!#$%&'()*+"),
    list(",-./:;<=>?"),
    list("@[]^_`{|}~"),
    list("\"\\         ")[:10],
    [SHIFT, SPACE, BSP, TOGGLE, CANCEL, OK],
]

_LABELS = {OK: "OK", BSP: "DEL", CANCEL: "Cancel",
           TOGGLE: "ABC/123", SHIFT: "Shift", SPACE: "Space"}


class OSKScreen:
    def __init__(self, app, title: str,
                 on_done: Callable[[Optional[str]], None],
                 initial: str = "", mask: bool = False,
                 layout: str = "keypad"):
        self.app = app
        self.title = title
        self.on_done = on_done
        self.text = initial
        self.mask = mask
        self.family = layout            # "keypad" | "full"
        self.full_page = 0              # 0 lower, 1 upper, 2 symbols
        self.row = 0
        self.col = 0

    # ------------------------------------------------------------------

    def _grid(self) -> List[List[str]]:
        if self.family == "keypad":
            return KEYPAD
        return (FULL_LOWER, FULL_UPPER, FULL_SYMBOL)[self.full_page]

    def _clamp(self) -> None:
        grid = self._grid()
        self.row = max(0, min(self.row, len(grid) - 1))
        self.col = max(0, min(self.col, len(grid[self.row]) - 1))

    def _press(self) -> None:
        key = self._grid()[self.row][self.col]
        if key == OK:
            self.app.pop_screen()
            self.on_done(self.text)
        elif key == CANCEL:
            self.app.pop_screen()
            self.on_done(None)
        elif key == BSP:
            self.text = self.text[:-1]
        elif key == TOGGLE:
            self.family = "full" if self.family == "keypad" else "keypad"
            self.row = self.col = 0
        elif key == SHIFT:
            self.full_page = (self.full_page + 1) % 3
        elif key == SPACE:
            self.text += " "
        elif not key.strip() and key != " ":
            pass
        else:
            self.text += key

    # ------------------------------------------------------------------

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type != pygame.KEYDOWN:
            return
        k = event.key
        if k == pygame.K_UP:
            self.row -= 1; self._clamp()
        elif k == pygame.K_DOWN:
            self.row += 1; self._clamp()
        elif k == pygame.K_LEFT:
            self.col -= 1; self._clamp()
        elif k == pygame.K_RIGHT:
            self.col += 1; self._clamp()
        elif k == pygame.K_RETURN:           # A
            self._press()
        elif k == pygame.K_ESCAPE:           # B
            self.text = self.text[:-1]
        elif k == pygame.K_x:                # X
            self.family = "full" if self.family == "keypad" else "keypad"
            self.row = self.col = 0
        elif k == pygame.K_y:                # Y
            if self.family == "full":
                self.full_page = (self.full_page + 1) % 3
        elif k == pygame.K_TAB:              # Start = OK
            self.app.pop_screen()
            self.on_done(self.text)
        elif k == pygame.K_F1:               # Select = cancel
            self.app.pop_screen()
            self.on_done(None)

    # ------------------------------------------------------------------

    def draw(self, surface: pygame.Surface) -> None:
        below = self.app.screen_below(self)
        if below is not None:
            below.draw(surface)
        overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 200))
        surface.blit(overlay, (0, 0))

        cfg = self.app.config
        theme = cfg["theme"]
        base = cfg["ui"]["font_size_base"]
        text_c = tuple(theme["text_color"])
        muted = tuple(theme["muted_color"])
        hi = tuple(theme["highlight_color"])
        panel = tuple(theme["panel_bg_color"])

        box_w = min(surface.get_width() - 40, max(620, base * 30))
        box_h = min(surface.get_height() - 40, max(380, base * 16))
        box = pygame.Rect((surface.get_width() - box_w) // 2,
                          (surface.get_height() - box_h) // 2, box_w, box_h)
        pygame.draw.rect(surface, panel, box)
        pygame.draw.rect(surface, hi, box, width=2)

        font = self.app.fonts.get(base)
        small = self.app.fonts.get(max(11, int(base * 0.7)))
        pad = max(16, int(base * 0.8))
        y = box.y + pad
        surface.blit(font.render(self.title, True, muted), (box.x + pad, y))
        y += font.get_linesize() + 4

        # entry field
        shown = ("\u2022" * len(self.text)) if self.mask else self.text
        field = pygame.Rect(box.x + pad, y, box.w - pad * 2,
                            font.get_linesize() + 10)
        pygame.draw.rect(surface, (0, 0, 0), field)
        pygame.draw.rect(surface, hi, field, width=1)
        ts = font.render(shown + "_", True, text_c)
        # right-align overflowing text so the caret end stays visible
        tx = field.x + 6
        if ts.get_width() > field.w - 12:
            tx = field.right - 6 - ts.get_width()
        clip = surface.get_clip()
        surface.set_clip(field.inflate(-4, -2))
        surface.blit(ts, (tx, field.y + 5))
        surface.set_clip(clip)
        y = field.bottom + pad

        # key grid
        grid = self._grid()
        rows = len(grid)
        grid_h = box.bottom - pad - small.get_linesize() - 6 - y
        cell_h = grid_h // rows
        for r, row in enumerate(grid):
            # merged keys (same token repeated) get one wide cell
            spans: List[tuple] = []
            c = 0
            while c < len(row):
                c2 = c
                while c2 + 1 < len(row) and row[c2 + 1] == row[c]:
                    c2 += 1
                spans.append((c, c2, row[c]))
                c = c2 + 1
            ncols = len(row)
            cell_w = (box.w - pad * 2) // ncols
            for c0, c1, key in spans:
                rect = pygame.Rect(box.x + pad + c0 * cell_w,
                                   y + r * cell_h,
                                   cell_w * (c1 - c0 + 1) - 4, cell_h - 4)
                selected = (r == self.row and c0 <= self.col <= c1)
                pygame.draw.rect(surface, hi if selected else (0, 0, 0), rect)
                pygame.draw.rect(surface, muted, rect, width=1)
                label = _LABELS.get(key, key)
                kf = font if len(label) <= 2 else small
                ks = kf.render(label, True,
                               panel if selected else text_c)
                surface.blit(ks, (rect.centerx - ks.get_width() // 2,
                                  rect.centery - ks.get_height() // 2))

        legend = ("A select   B delete   X 123/ABC   Y shift   "
                  "Start OK   Select cancel")
        ls = small.render(legend, True, muted)
        surface.blit(ls, (box.x + pad, box.bottom - pad // 2 - ls.get_height()))
