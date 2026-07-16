"""
Shared rendering primitives: font cache, image cache, text helpers.

Everything that needs to know how to draw text or images lives here so
the screen modules stay focused on layout.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pygame


Color = Tuple[int, int, int]


# ---------------------------------------------------------------------------
# Fonts
# ---------------------------------------------------------------------------

class FontCache:
    """
    Cache of pygame.font.Font objects keyed by (path, size).

    Supports a regular and a bold TTF (Oxanium-Medium and Oxanium-Bold by
    default). If a requested TTF can't be loaded we fall back to pygame's
    built-in font, which is ugly but always present.
    """

    def __init__(self, regular_path: Optional[Path] = None,
                 bold_path: Optional[Path] = None):
        self._regular = (regular_path if (regular_path and regular_path.is_file())
                         else None)
        self._bold = (bold_path if (bold_path and bold_path.is_file())
                      else None)
        self._cache: Dict[Tuple[Optional[str], int, bool], pygame.font.Font] = {}

    def get(self, size: int, bold: bool = False) -> pygame.font.Font:
        path = self._bold if bold else self._regular
        # If bold was asked for but we have no bold TTF, fall back to
        # regular and ask pygame to synthesise bold.
        synth_bold = bold and path is None and self._regular is not None
        if synth_bold:
            path = self._regular

        key = (str(path) if path else None, size, bold)
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        if path is not None:
            try:
                font = pygame.font.Font(str(path), size)
            except (OSError, pygame.error):
                font = pygame.font.Font(None, size)
        else:
            font = pygame.font.Font(None, size)

        if synth_bold:
            try:
                font.set_bold(True)
            except (pygame.error, AttributeError):
                pass

        self._cache[key] = font
        return font


# ---------------------------------------------------------------------------
# Images
# ---------------------------------------------------------------------------

class ImageCache:
    """
    LRU-ish image cache. We don't strictly LRU; instead we cap the entry
    count and evict in insertion order. Game lists rarely exceed a few
    hundred entries so a simple FIFO is fine and avoids tracking access
    time.
    """

    def __init__(self, max_entries: int = 64):
        self._cache: Dict[str, Optional[pygame.Surface]] = {}
        self._max = max_entries

    def load_scaled(self, path: Path, max_w: int, max_h: int) -> Optional[pygame.Surface]:
        if not path or not path.is_file():
            return None
        key = f"{path}|{max_w}x{max_h}"
        if key in self._cache:
            return self._cache[key]

        try:
            raw = pygame.image.load(str(path))
        except (pygame.error, OSError) as exc:
            print(f"[render] image load failed for {path}: {exc}")
            self._cache[key] = None
            return None

        try:
            raw = raw.convert_alpha()
        except pygame.error:
            # Display surface might not be ready; fall back to convert()
            try:
                raw = raw.convert()
            except pygame.error:
                pass

        rect = raw.get_rect()
        if rect.width == 0 or rect.height == 0:
            self._cache[key] = None
            return None

        # No cap on the upscale: scraped box art is commonly 256x256, and
        # on a 1280-wide handheld screen that's barely visible. Let the
        # image grow to fit the panel; smoothscale handles bilinear
        # interpolation well enough for typical box art and screenshots.
        ratio = min(max_w / rect.width, max_h / rect.height)
        new_size = (max(1, int(rect.width * ratio)),
                    max(1, int(rect.height * ratio)))
        try:
            scaled = pygame.transform.smoothscale(raw, new_size)
        except (pygame.error, ValueError):
            scaled = pygame.transform.scale(raw, new_size)

        self._cache[key] = scaled
        self._evict_if_needed()
        return scaled

    def _evict_if_needed(self) -> None:
        while len(self._cache) > self._max:
            # Pop oldest insertion - dict preserves insertion order in 3.7+
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------

def render_clipped_text(surface: pygame.Surface,
                        text: str,
                        font: pygame.font.Font,
                        color: Color,
                        rect: pygame.Rect,
                        x_offset: int = 0) -> int:
    """
    Render ``text`` left-aligned within ``rect``, clipped to ``rect.width``.

    ``x_offset`` slides the text leftwards - used by the marquee scroller.
    Returns the full text surface width in pixels (so callers can decide
    whether scrolling is needed at all).
    """
    text_surf = font.render(text, True, color)
    text_w = text_surf.get_width()

    # Source area inside text_surf to copy
    src_x = max(0, x_offset)
    src_rect = pygame.Rect(src_x, 0,
                           min(rect.width, max(0, text_w - src_x)),
                           text_surf.get_height())

    if src_rect.width > 0:
        surface.blit(text_surf, (rect.x, rect.y), src_rect)
    return text_w


def wrap_text(text: str, font: pygame.font.Font, max_width: int) -> List[str]:
    """Greedy word-wrap. Empty input yields a single empty line so callers
    can iterate without special-casing."""
    if not text:
        return [""]

    out: List[str] = []
    for paragraph in text.replace("\r\n", "\n").split("\n"):
        if not paragraph.strip():
            out.append("")
            continue
        words = paragraph.split(" ")
        line: List[str] = []
        for word in words:
            line.append(word)
            if font.size(" ".join(line))[0] > max_width:
                line.pop()
                if line:
                    out.append(" ".join(line))
                line = [word]
                # If a single word is wider than max_width, accept the
                # overflow rather than infinite-loop. Could break at chars
                # later if it ever matters.
        if line:
            out.append(" ".join(line))
    return out


def draw_wrapped_text(surface: pygame.Surface,
                      lines: List[str],
                      font: pygame.font.Font,
                      color: Color,
                      rect: pygame.Rect,
                      y_offset: int = 0) -> int:
    """
    Draw ``lines`` (each already wrapped to fit ``rect.width``) starting
    at ``rect.top - y_offset``. Returns the total content height so callers
    can compute scrollbar position.
    """
    line_h = font.get_linesize()
    total_h = line_h * len(lines)

    clip_prev = surface.get_clip()
    surface.set_clip(rect)
    try:
        y = rect.top - y_offset
        for line in lines:
            if y + line_h < rect.top:
                y += line_h
                continue
            if y > rect.bottom:
                break
            if line:
                surf = font.render(line, True, color)
                surface.blit(surf, (rect.left, y))
            y += line_h
    finally:
        surface.set_clip(clip_prev)
    return total_h


# ---------------------------------------------------------------------------
# Star rating
# ---------------------------------------------------------------------------

def draw_stars(surface: pygame.Surface,
               x: int, y: int,
               rating: float,
               accent: Color,
               muted: Color,
               star_size: int = 14,
               gap: int = 2,
               star_count: int = 5) -> int:
    """
    Draw ``star_count`` star polygons filled by ``rating`` (0.0..1.0).

    Returns the total pixel width consumed so the caller can place the
    next element to the right of the stars.
    """
    rating = max(0.0, min(1.0, rating))
    filled_units = rating * star_count   # e.g. 4.25 stars

    for i in range(star_count):
        cx = x + i * (star_size + gap) + star_size // 2
        cy = y + star_size // 2
        fraction = max(0.0, min(1.0, filled_units - i))
        _draw_one_star(surface, cx, cy, star_size, fraction, accent, muted)

    return star_count * star_size + (star_count - 1) * gap


def _draw_one_star(surface: pygame.Surface,
                   cx: int, cy: int, size: int,
                   fraction: float,
                   accent: Color, muted: Color) -> None:
    """
    Draw a 5-point star at (cx, cy). ``fraction`` (0..1) of the star is
    painted in ``accent``, the remainder in ``muted``. We approximate
    fractional fill by drawing the muted star first and then a
    horizontally-clipped accent star on top.
    """
    import math
    points = []
    outer = size / 2
    inner = outer * 0.45
    for i in range(10):
        angle = -math.pi / 2 + i * math.pi / 5
        r = outer if i % 2 == 0 else inner
        points.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))

    # Background (empty star)
    pygame.draw.polygon(surface, muted, points)

    if fraction <= 0:
        return
    if fraction >= 1:
        pygame.draw.polygon(surface, accent, points)
        return

    # Partial: clip to the left portion
    clip_w = int(size * fraction)
    prev_clip = surface.get_clip()
    surface.set_clip(pygame.Rect(cx - size // 2, cy - size // 2, clip_w, size))
    try:
        pygame.draw.polygon(surface, accent, points)
    finally:
        surface.set_clip(prev_clip)


HEADER_DELETE_BG = (178, 34, 34)    # white-on-red: destructive mode
HEADER_FETCH_BG = (24, 100, 52)     # white-on-dark-green: acquisitive mode


def draw_screen_header(surface: pygame.Surface, app, theme, ui,
                       text: str, bg) -> int:
    """Large, centered, color-coded title strip across the top of the
    full-screen lists - MARK FOR DELETE (white on red) and FETCH FROM
    WebDAV (white on dark green) - so the look-alike screens are
    instantly tellable apart. Returns the strip height so callers can
    shift their panels down by it."""
    font = app.fonts.get(max(14, int(ui["font_size_base"] * 0.95)))
    h = font.get_linesize() + 8
    rect = pygame.Rect(0, 0, surface.get_width(), h)
    pygame.draw.rect(surface, bg, rect)
    label = font.render(text, True, (255, 255, 255))
    surface.blit(label, ((rect.w - label.get_width()) // 2,
                         rect.y + (h - label.get_height()) // 2))
    return h


def split_layout(surface_w, content_top, content_h, list_width_pct, side):
    """Modular two-pane layout for the games-list screens.

    Returns (list_rect, panel_rect) for the given side ("left" or
    "right"). "left" keeps the historical layout (list on the left,
    preview/details on the right); "right" mirrors it. Adding a third
    arrangement later is just another branch here - the screens don't
    need to know which side they're on.
    """
    list_w = int(surface_w * list_width_pct)
    panel_w = surface_w - list_w
    if side == "right":
        panel_rect = pygame.Rect(0, content_top, panel_w, content_h)
        list_rect = pygame.Rect(panel_w, content_top, list_w, content_h)
    else:  # "left" (default)
        list_rect = pygame.Rect(0, content_top, list_w, content_h)
        panel_rect = pygame.Rect(list_w, content_top, panel_w, content_h)
    return list_rect, panel_rect


# =====================================================================
#  Button-hint rendering: chips for face buttons (A/B/X/Y) and named
#  buttons (L1/R1/SEL/ST), plus un-chipped navigation symbols drawn in
#  the highlight colour - a d-pad cross for "navigate all ways" and
#  opposing-triangle pairs for up/down and left/right (four-way triangles
#  blur together at footer size, so the d-pad stays for the all-ways one).
#  Shared by the bottom hint bars and the in-window prompt lines so every
#  button reference in the app looks the same.
# =====================================================================

def _draw_dpad(surface, x, cy, side, color):
    size = int(side * 0.9); size -= size % 2; bar = max(3, size // 3)
    cx = x + side // 2
    pygame.draw.rect(surface, color,
                     pygame.Rect(cx - bar // 2, cy - size // 2, bar, size), border_radius=2)
    pygame.draw.rect(surface, color,
                     pygame.Rect(cx - size // 2, cy - bar // 2, size, bar), border_radius=2)


def _tri(surface, cx, cy, base, height, direction, color):
    b = base // 2
    if direction == "up":
        pts = [(cx, cy - height // 2), (cx - b, cy + height // 2), (cx + b, cy + height // 2)]
    elif direction == "down":
        pts = [(cx, cy + height // 2), (cx - b, cy - height // 2), (cx + b, cy - height // 2)]
    elif direction == "left":
        pts = [(cx - height // 2, cy), (cx + height // 2, cy - b), (cx + height // 2, cy + b)]
    else:  # right
        pts = [(cx + height // 2, cy), (cx - height // 2, cy - b), (cx - height // 2, cy + b)]
    pygame.draw.polygon(surface, color, pts)


def _draw_updown(surface, x, cy, side, color):
    cx = x + side // 2; th = int(side * 0.34); gap = max(2, int(side * 0.12)); bw = int(side * 0.62)
    _tri(surface, cx, cy - gap - th // 2, bw, th, "up", color)
    _tri(surface, cx, cy + gap + th // 2, bw, th, "down", color)


def _draw_leftright(surface, x, cy, side, color):
    cx = x + side // 2; th = int(side * 0.34); gap = max(2, int(side * 0.12)); bh = int(side * 0.62)
    _tri(surface, cx - gap - th // 2, cy, bh, th, "left", color)
    _tri(surface, cx + gap + th // 2, cy, bh, th, "right", color)


_NAV_SYMBOLS = {"dpad": _draw_dpad, "updown": _draw_updown, "leftright": _draw_leftright}


def _seg_width(kind, val, sz, reg, bold, side):
    if kind == "chip":
        return max(side, bold.size(val)[0] + max(6, int(sz * 0.5)))
    if kind in _NAV_SYMBOLS:
        return side
    return reg.size(val)[0]


def _draw_seg(surface, x, cy, kind, val, sz, reg, bold, side, hi, label_c):
    """Draw one segment at (x, vertical-centre cy); return its width."""
    if kind == "chip":
        w = max(side, bold.size(val)[0] + max(6, int(sz * 0.5)))
        chip = pygame.Rect(x, cy - side // 2, w, side)
        pygame.draw.rect(surface, hi, chip, border_radius=3)
        g = bold.render(val, True, (0, 0, 0))
        surface.blit(g, (chip.centerx - g.get_width() // 2, chip.centery - g.get_height() // 2))
        return w
    if kind in _NAV_SYMBOLS:
        _NAV_SYMBOLS[kind](surface, x, cy, side, hi)
        return side
    t = reg.render(val, True, label_c)
    surface.blit(t, (x, cy - t.get_height() // 2))
    return t.get_width()


def draw_hint_bar(surface, rect, fonts, base_font_size, theme, hints):
    """Bottom hint / legend bar.

    ``hints`` is a list of hints; each hint is a list of (kind, value)
    segments::

        [("dpad",), ("txt", "Navigate")]                  -> d-pad + label
        [("chip", "A"), ("txt", "Enter")]                 -> [A] Enter
        [("updown",), ("txt", "Change")]                  -> up/down + label
        [("chip", "L1"), ("txt", "/"), ("chip", "R1"),
         ("txt", "PgUp/Dn")]                               -> [L1]/[R1] PgUp/Dn

    Chips are highlight-coloured with a BOLD black glyph; nav symbols
    (dpad/updown/leftright) are drawn in the highlight colour, un-chipped.
    Hints are separated by a wide gap; within a hint the gap is small, and
    a "/" segment hugs its neighbours tighter. Auto-shrinks the font to a
    readable floor so it fits 4:3 / 1:1 widths. Presentational only.
    """
    hi = tuple(theme["highlight_color"])
    label_c = tuple(theme["legend_text_color"])
    avail = max(1, rect.width - 16)
    top = max(11, int(base_font_size * 0.7))
    floor = max(10, int(base_font_size * 0.52))

    def _layout(sz):
        reg = fonts.get(sz); bold = fonts.get(sz, bold=True)
        gap_grp = max(10, int(sz * 0.85)); gap_seg = max(4, int(sz * 0.34)); gap_tight = max(2, int(sz * 0.16))
        side = int(reg.get_height() * 0.9)
        placed = []; x = 0
        for h_i, hint in enumerate(hints):
            if h_i:
                x += gap_grp
            prev = None
            for s_i, seg in enumerate(hint):
                kind = seg[0]; val = seg[1] if len(seg) > 1 else ""
                if s_i:
                    x += gap_tight if (val == "/" or prev == "/") else gap_seg
                w = _seg_width(kind, val, sz, reg, bold, side)
                placed.append((kind, val, x, w)); x += w; prev = val
        return placed, x, reg, bold, side

    sz = top
    while sz > floor and _layout(sz)[1] > avail:
        sz -= 1
    placed, _, reg, bold, side = _layout(sz)
    ox = rect.x + 8; cy = rect.y + rect.height // 2
    for kind, val, x, w in placed:
        _draw_seg(surface, ox + x, cy, kind, val, sz, reg, bold, side, hi, label_c)


def render_button_line(fonts, size, theme, segments):
    """Render a single in-window prompt line (e.g. 'Press [B] to close.')
    to a Surface the caller can blit wherever it likes. ``segments`` is a
    flat list of (kind, value): ("txt", "..."), ("chip", "B"),
    ("dpad",)/("updown",)/("leftright",). Text carries its own spacing;
    chips/symbols get a hair of padding so they don't touch the words."""
    reg = fonts.get(size); bold = fonts.get(size, bold=True)
    side = int(reg.get_height() * 0.9)
    pad = max(2, int(size * 0.14))
    hi = tuple(theme["highlight_color"])
    label_c = tuple(theme.get("legend_text_color", theme.get("text_color", (230, 230, 230))))

    total = 0
    for kind, *rest in segments:
        val = rest[0] if rest else ""
        w = _seg_width(kind, val, size, reg, bold, side)
        total += w + (2 * pad if kind != "txt" else 0)
    h = max(side, reg.get_height())
    surf = pygame.Surface((max(1, total), h), pygame.SRCALPHA)
    x = 0; cy = h // 2
    for kind, *rest in segments:
        val = rest[0] if rest else ""
        if kind != "txt":
            x += pad
        w = _draw_seg(surf, x, cy, kind, val, size, reg, bold, side, hi, label_c)
        x += w + (pad if kind != "txt" else 0)
    return surf


_PROMPT_BUTTONS = {
    "A": "A", "B": "B", "X": "X", "Y": "Y",
    "L1": "L1", "R1": "R1", "L2": "L2", "R2": "R2",
    "Start": "ST", "Select": "SEL", "Sel": "SEL",
}


def render_prompt(font, theme, text):
    """Render an in-window prompt string to a Surface, drawing recognised
    gamepad button tokens (A/B/X/Y/L1/R1/Start/Select) as chips and the
    rest as plain text. Takes the caller's own font (works with auto-fitted
    fonts). Tokens match exactly and case-sensitively, so the article 'a'
    and lowercase labels like 'select' stay text. Whitespace is preserved."""
    import re
    side = int(font.get_height() * 0.9)
    hi = tuple(theme["highlight_color"])
    label_c = tuple(theme.get("legend_text_color",
                              theme.get("text_color", (230, 230, 230))))

    segs = []
    for p in re.split(r"(\s+)", text):
        if not p:
            continue
        core = p.rstrip(".,:;!")
        tail = p[len(core):]
        if core in _PROMPT_BUTTONS:
            segs.append(("chip", _PROMPT_BUTTONS[core]))
            if tail:
                segs.append(("txt", tail))
        else:
            segs.append(("txt", p))

    def _chip_w(glyph):
        font.set_bold(True); w = font.size(glyph)[0]; font.set_bold(False)
        return max(side, w + max(6, int(font.get_height() * 0.5)))

    total = sum(_chip_w(v) if k == "chip" else font.size(v)[0] for k, v in segs)
    h = max(side, font.get_height())
    surf = pygame.Surface((max(1, total), h), pygame.SRCALPHA)
    x = 0; cy = h // 2
    for kind, val in segs:
        if kind == "chip":
            w = _chip_w(val)
            r = pygame.Rect(x, cy - side // 2, w, side)
            pygame.draw.rect(surf, hi, r, border_radius=3)
            font.set_bold(True)
            g = font.render(val, True, (0, 0, 0))
            font.set_bold(False)
            surf.blit(g, (r.centerx - g.get_width() // 2, r.centery - g.get_height() // 2))
            x += w
        else:
            t = font.render(val, True, label_c)
            surf.blit(t, (x, cy - t.get_height() // 2))
            x += t.get_width()
    return surf
