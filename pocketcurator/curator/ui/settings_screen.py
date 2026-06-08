"""
Settings screen. Edits a handful of values in app.config in-memory; B-back
saves them to disk via app.save_settings().

Kept intentionally small in this first version. Adding new entries is a
matter of appending to OPTIONS - the screen handles rendering and
mutation generically.
"""

from __future__ import annotations

import pygame


# Each option: (label, kind, mutator, accessor, hint)
#   kind: "int_range", "bool", "choice"
#   mutator: callable(config, new_value)
#   accessor: callable(config) -> current value
#   For int_range, options dict includes min/max/step.
def _set_font_size_locked(c, v):
    """Setter for font_size_base. Also marks the value as user-locked so
    the next launch's resolution-based auto-scale doesn't trample it.
    Without this, a user who picks 40 on a 1920x1152 screen would see
    96 (or capped 80) on the next launch."""
    c["ui"]["font_size_base"] = v
    c["ui"]["font_size_base_locked"] = True


def _make_options():
    return [
        {
            "label": "Font size",
            "kind": "int_range",
            "min": 14, "max": 80, "step": 2,
            "get": lambda c: c["ui"]["font_size_base"],
            "set": _set_font_size_locked,
            "hint": "Larger = fewer games visible at once.",
        },
        {
            "label": "Auto-scroll description",
            "kind": "bool",
            "get": lambda c: bool(c["ui"]["description_autoscroll"]),
            "set": lambda c, v: c["ui"].__setitem__("description_autoscroll", v),
            "hint": "Off: use L2 / R2 to scroll manually.",
        },
        {
            "label": "Safe Mode (doesn't delete)",
            "kind": "bool",
            "get": lambda c: bool(c["behavior"]["deletion_dry_run"]),
            "set": lambda c, v: c["behavior"].__setitem__("deletion_dry_run", v),
            "hint": "On: deletions are simulated only. Test before committing.",
        },
        {
            "label": "Delete scraped media",
            "kind": "bool",
            "get": lambda c: bool(c["behavior"]["include_scraped_media"]),
            "set": lambda c, v: c["behavior"].__setitem__("include_scraped_media", v),
            "hint": "When a ROM is deleted, also remove its images, videos, marquees, manuals, screenshots, and box art.",
        },
        {
            "label": "Rating display",
            "kind": "choice",
            "choices": ["stars", "text"],
            "get": lambda c: c.get("ratings_display", "stars"),
            "set": lambda c, v: c.__setitem__("ratings_display", v),
            "hint": "Graphical stars or a textual 'X.X / 5' label.",
        },
    ]


class SettingsScreen:
    def __init__(self, app):
        self.app = app
        self.options = _make_options()
        self.selected = 0
        self._dirty = False

    def handle_event(self, event):
        if event.type != pygame.KEYDOWN:
            return

        if event.key == pygame.K_ESCAPE:
            if self._dirty:
                self.app.save_settings()
                self._dirty = False
            self.app.pop_screen()
            return
        if event.key == pygame.K_UP:
            self.selected = (self.selected - 1) % len(self.options)
        elif event.key == pygame.K_DOWN:
            self.selected = (self.selected + 1) % len(self.options)
        elif event.key in (pygame.K_LEFT, pygame.K_RIGHT):
            self._adjust(+1 if event.key == pygame.K_RIGHT else -1)
        elif event.key == pygame.K_RETURN:
            # A on a bool toggles, on a choice cycles forward.
            opt = self.options[self.selected]
            if opt["kind"] == "bool":
                self._adjust(+1)
            elif opt["kind"] == "choice":
                self._adjust(+1)

    def _adjust(self, delta: int) -> None:
        opt = self.options[self.selected]
        cur = opt["get"](self.app.config)
        if opt["kind"] == "int_range":
            new = max(opt["min"], min(opt["max"], cur + delta * opt["step"]))
        elif opt["kind"] == "bool":
            new = not cur
        elif opt["kind"] == "choice":
            choices = opt["choices"]
            idx = (choices.index(cur) + delta) % len(choices) if cur in choices else 0
            new = choices[idx]
        else:
            return
        if new != cur:
            opt["set"](self.app.config, new)
            self._dirty = True

    def draw(self, surface):
        cfg = self.app.config
        theme = cfg["theme"]
        ui = cfg["ui"]
        surface.fill(tuple(theme["background_color"]))

        title_font = self.app.fonts.get(int(ui["font_size_base"] * 1.4))
        row_font = self.app.fonts.get(ui["font_size_base"])
        hint_font = self.app.fonts.get(max(11, int(ui["font_size_base"] * 0.75)))

        # Title
        title = title_font.render("Settings", True, tuple(theme["text_color"]))
        surface.blit(title, (40, 24))

        # Version, right-justified opposite the title - smaller than the
        # header, not bold, baseline-aligned to the title.
        from .. import __version__, __build__
        ver_font = self.app.fonts.get(max(12, int(ui["font_size_base"] * 0.8)))
        ver_surf = ver_font.render(f"v{__version__}  build {__build__}",
                                   True, tuple(theme["muted_color"]))
        surface.blit(
            ver_surf,
            (surface.get_width() - 40 - ver_surf.get_width(),
             24 + max(0, title.get_height() - ver_surf.get_height())))

        # Options. Value text is right-aligned against the screen edge so
        # there's always a visible gap between the label and its value,
        # even when the label is long.
        right_pad = 40
        y = 24 + title.get_height() + 24
        row_h = row_font.get_linesize() + 18

        for i, opt in enumerate(self.options):
            is_sel = (i == self.selected)
            if is_sel:
                pygame.draw.rect(
                    surface, tuple(theme["highlight_color"]),
                    pygame.Rect(20, y - 4, surface.get_width() - 40, row_h))

            label_color = (tuple(theme["highlight_text_color"]) if is_sel
                           else tuple(theme["text_color"]))
            label = row_font.render(opt["label"], True, label_color)
            surface.blit(label, (40, y + 4))

            value = opt["get"](cfg)
            if opt["kind"] == "bool":
                value_str = "On" if value else "Off"
            else:
                value_str = str(value)
            value_color = (tuple(theme["highlight_text_color"]) if is_sel
                           else tuple(theme["accent_color"]))
            value_surf = row_font.render(value_str, True, value_color)
            surface.blit(
                value_surf,
                (surface.get_width() - right_pad - value_surf.get_width(),
                 y + 4))

            y += row_h

        # Environment info block (OS / ROMs Location / Theme), relocated
        # here from the old system-browser subtitle. Sits just above the
        # hint line.
        info_lines = [
            f"OS:  {self.app.firmware_name}",
            f"ROMs Location:  {self.app.roms_dir if self.app.roms_dir else 'n/a'}",
            f"Theme:  {self.app.theme_dir.name if self.app.theme_dir else 'n/a'}",
        ]
        info_line_h = hint_font.get_linesize()
        info_y = surface.get_height() - 70 - info_line_h * len(info_lines) - 12
        for i, line in enumerate(info_lines):
            surf = hint_font.render(line, True, tuple(theme["muted_color"]))
            surface.blit(surf, (40, info_y + i * info_line_h))

        # Hint for selected option
        opt = self.options[self.selected]
        hint = hint_font.render(opt["hint"], True, tuple(theme["muted_color"]))
        surface.blit(hint, (40, surface.get_height() - 70))

        # Legend
        legend = hint_font.render(
            "Up/Down: choose   -   Left/Right: change   -   B: back",
            True, tuple(theme["legend_text_color"]))
        surface.blit(legend, (40, surface.get_height() - 36))
