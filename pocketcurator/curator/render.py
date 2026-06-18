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
