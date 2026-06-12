"""
User-selectable colors for the UI - a small, self-contained palette
layer on top of the active theme.

The user can pick a Font Color (the bright text color) and a Highlight
Color (the selection-bar color, which must be dark enough that the
bright font color stays readable on top of it). Both are chosen from
fixed, named palettes so we never end up with an unreadable
combination, and both wrap (infinite scroll) in the settings UI.

These are applied as OVERRIDES on top of whatever theme is loaded:
apply_user_colors() copies the chosen RGBs into the theme dict's
text/accent and highlight slots. Selecting "Theme Default" for either
leaves the theme's own value untouched.
"""

from __future__ import annotations

from typing import List, Tuple

RGB = Tuple[int, int, int]

# Bright, legible foreground colors. "Theme Default" first so an
# untouched install looks exactly as the theme intended.
FONT_COLORS: List[Tuple[str, RGB]] = [
    ("Theme Default", None),
    ("White", (240, 240, 240)),
    ("Red", (255, 80, 80)),
    ("Orange", (255, 150, 50)),
    ("Yellow", (240, 220, 60)),
    ("Green", (90, 220, 110)),
    ("Blue", (90, 160, 240)),
    ("Purple", (185, 120, 235)),
]

# Darker-but-not-dark selection colors, chosen so the bright font
# colors above stay readable on top. "Theme Default" first.
HIGHLIGHT_COLORS: List[Tuple[str, RGB]] = [
    ("Theme Default", None),
    ("Grey", (90, 90, 96)),
    ("Red", (150, 40, 40)),
    ("Orange", (165, 85, 25)),
    ("Yellow", (150, 130, 25)),
    ("Green", (40, 120, 60)),
    ("Blue", (40, 80, 150)),
    ("Purple", (95, 55, 135)),
]


def font_color_names() -> List[str]:
    return [name for name, _ in FONT_COLORS]


def highlight_color_names() -> List[str]:
    return [name for name, _ in HIGHLIGHT_COLORS]


def _lookup(palette, name):
    for n, rgb in palette:
        if n == name:
            return rgb
    return None


def apply_user_colors(config: dict) -> None:
    """Copy the user's chosen font/highlight colors into the live theme
    dict. Call once after settings load and again whenever either value
    changes. 'Theme Default' (or a missing key) leaves the theme alone.
    """
    ui = config.setdefault("ui", {})
    theme = config.setdefault("theme", {})

    # Snapshot the theme's own values once, so toggling back to
    # 'Theme Default' can restore them rather than keeping the last
    # user pick.
    base = config.setdefault("_theme_base", {})
    for key in ("text_color", "accent_color", "highlight_color"):
        if key not in base and key in theme:
            base[key] = list(theme[key])

    font_name = ui.get("font_color", "Theme Default")
    rgb = _lookup(FONT_COLORS, font_name)
    if rgb is not None:
        theme["text_color"] = list(rgb)
        theme["accent_color"] = list(rgb)
    elif "text_color" in base:
        theme["text_color"] = list(base["text_color"])
        theme["accent_color"] = list(base.get("accent_color",
                                               base["text_color"]))

    hl_name = ui.get("highlight_color", "Theme Default")
    hrgb = _lookup(HIGHLIGHT_COLORS, hl_name)
    if hrgb is not None:
        theme["highlight_color"] = list(hrgb)
    elif "highlight_color" in base:
        theme["highlight_color"] = list(base["highlight_color"])


def swatch_rgb_font(name: str, theme: dict) -> RGB:
    """The RGB to show in a settings swatch for a font-color choice."""
    rgb = _lookup(FONT_COLORS, name)
    if rgb is not None:
        return rgb
    return tuple(theme.get("_default_text", theme.get("text_color",
                                                       (230, 230, 230))))


def swatch_rgb_highlight(name: str, theme: dict) -> RGB:
    rgb = _lookup(HIGHLIGHT_COLORS, name)
    if rgb is not None:
        return rgb
    return tuple(theme.get("highlight_color", (255, 85, 85)))
