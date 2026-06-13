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
    """Setter for the Font Size control. The user is choosing an explicit
    on-screen size, so we lock it (no resolution auto-scale on the next
    launch) and store it as BOTH the effective size used this session
    (font_size_base) and the persisted user value (font_size_user) the
    next launch reads. Writing font_size_user is what stops the old
    runaway-rescale bug (22 -> 53 -> 127...)."""
    c["ui"]["font_size_base"] = v
    c["ui"]["font_size_user"] = v
    c["ui"]["font_size_base_locked"] = True


def _make_options():
    return [
        {
            "label": "Check For Updates",
            "kind": "action",
            "status": lambda app: _updater(app).status_text(),
            "dynamic_hint": lambda app: _updater(app).hint_text(),
            "run": lambda app: _open_update(app),
            "hint": "Checks for and downloads new releases. Needs WiFi.",
        },
        {
            "label": "Status",
            "kind": "action",
            "status": lambda app: "",
            "run": lambda app: _open_status(app),
            "hint": "Version, firmware, paths, theme, and connection health.",
        },
        {
            "label": "Font Size",
            "kind": "int_range",
            "min": 14, "max": 80, "step": 2,
            "get": lambda c: c["ui"]["font_size_base"],
            "set": _set_font_size_locked,
            "hint": "Larger = fewer games visible at once.",
        },
        {
            "label": "Font Color",
            "kind": "color_choice",
            "palette": "font",
            "get": lambda c: c["ui"].get("font_color", "Theme Default"),
            "set": _set_font_color,
            "hint": "Text color. Left / Right to scroll the swatches.",
        },
        {
            "label": "Highlight Color",
            "kind": "color_choice",
            "palette": "highlight",
            "get": lambda c: c["ui"].get("highlight_color", "Theme Default"),
            "set": _set_highlight_color,
            "hint": "Selection-bar color. Left / Right to scroll.",
        },
        {
            "label": "Swap Games List Side",
            "kind": "choice",
            "choices": ["left", "right"],
            "get": lambda c: c["ui"].get("games_list_side", "left"),
            "set": lambda c, v: c["ui"].__setitem__("games_list_side", v),
            "hint": ("Which side the games list sits on; the preview and "
                     "details take the other side."),
        },
        {
            "label": "Delete Scraped Files with ROMs",
            "kind": "bool",
            "get": lambda c: bool(c["behavior"]["include_scraped_media"]),
            "set": lambda c, v: c["behavior"].__setitem__("include_scraped_media", v),
            "hint": "When a ROM is deleted, also remove its images, videos, marquees, manuals, screenshots, and box art.",
        },
        {
            "label": "Auto-Scroll Description",
            "kind": "bool",
            "get": lambda c: bool(c["ui"]["description_autoscroll"]),
            "set": lambda c, v: c["ui"].__setitem__("description_autoscroll", v),
            "hint": "Off: use L2 / R2 to scroll manually.",
        },
        {
            "label": "Rating Display",
            "kind": "choice",
            "choices": ["stars", "text"],
            "get": lambda c: c.get("ratings_display", "stars"),
            "set": lambda c, v: c.__setitem__("ratings_display", v),
            "hint": "Graphical stars or a textual 'X.X / 5' label.",
        },
        {
            "label": "Restore Gamelist Backup",
            "kind": "action",
            "status": lambda app: "",
            "run": lambda app: _open_restore(app),
            "hint": ("Puts back a system's gamelist.xml from the backup "
                     "made before Fetch injected game details."),
        },
    ]


def _set_font_color(c, v):
    c["ui"]["font_color"] = v
    from ..colors import apply_user_colors
    apply_user_colors(c)


def _set_highlight_color(c, v):
    c["ui"]["highlight_color"] = v
    from ..colors import apply_user_colors
    apply_user_colors(c)


def _updater(app):
    """Create the updater lazily on first visit to the row, so app
    startup pays nothing for it."""
    if getattr(app, "updater", None) is None:
        from .. import __version__
        from ..updater import Updater
        app.updater = Updater(app.port_dir, __version__)
    return app.updater


def _open_update(app):
    """The row opens the update dialog, which runs the whole pipeline
    (check -> download -> verify -> stage) without further input."""
    _updater(app)  # ensure the shared instance exists
    from .update_screen import UpdateScreen
    app.push_screen(UpdateScreen(app))


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
        elif event.key == pygame.K_PAGEUP:        # L1 -> top
            self.selected = 0
        elif event.key == pygame.K_PAGEDOWN:      # R1 -> bottom
            self.selected = len(self.options) - 1
        elif event.key in (pygame.K_LEFT, pygame.K_RIGHT):
            self._adjust(+1 if event.key == pygame.K_RIGHT else -1)
        elif event.key == pygame.K_RETURN:
            # A on a bool toggles, on a choice/color cycles forward, on
            # an action runs it.
            opt = self.options[self.selected]
            if opt["kind"] in ("bool", "choice", "color_choice"):
                self._adjust(+1)
            elif opt["kind"] == "action":
                opt["run"](self.app)

    def _adjust(self, delta: int) -> None:
        opt = self.options[self.selected]
        if opt["kind"] == "action":
            return
        cur = opt["get"](self.app.config)
        if opt["kind"] == "int_range":
            new = max(opt["min"], min(opt["max"], cur + delta * opt["step"]))
        elif opt["kind"] == "bool":
            new = not cur
        elif opt["kind"] == "choice":
            choices = opt["choices"]
            idx = (choices.index(cur) + delta) % len(choices) if cur in choices else 0
            new = choices[idx]
        elif opt["kind"] == "color_choice":
            from ..colors import font_color_names, highlight_color_names
            names = (font_color_names() if opt["palette"] == "font"
                     else highlight_color_names())
            idx = (names.index(cur) + delta) % len(names) if cur in names else 0
            new = names[idx]
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
        W, H = surface.get_size()

        base = ui["font_size_base"]
        title_font = self.app.fonts.get(int(base * 1.4))
        row_font = self.app.fonts.get(base)
        hint_font = self.app.fonts.get(max(11, int(base * 0.75)))

        text_c = tuple(theme["text_color"])
        muted = tuple(theme["muted_color"])
        accent = tuple(theme["accent_color"])
        hi = tuple(theme["highlight_color"])
        hi_text = tuple(theme["highlight_text_color"])

        # Title
        title = title_font.render("Settings", True, text_c)
        surface.blit(title, (40, 24))

        # Version, right-justified opposite the title.
        from .. import __version__, __build__
        ver_font = self.app.fonts.get(max(12, int(base * 0.8)))
        ver_surf = ver_font.render(f"v{__version__}  build {__build__}",
                                   True, muted)
        surface.blit(
            ver_surf,
            (W - 40 - ver_surf.get_width(),
             24 + max(0, title.get_height() - ver_surf.get_height())))

        # --- pinned bottom block: hint line + legend line. These are
        # reserved FIRST so the list can never grow into them, no matter
        # how large the font is. ---
        line_gap = 8
        legend_h = hint_font.get_linesize()
        hint_h = hint_font.get_linesize()
        bottom_block_h = legend_h + hint_h + line_gap + 10
        list_top = 24 + title.get_height() + 18
        list_bottom = H - bottom_block_h

        # Compact rows: same height as the games lists (font line + small
        # padding), not the old roomy row.
        row_h = row_font.get_linesize() + 6
        right_pad = 40
        swatch_w = max(18, int(base * 0.9))

        visible = max(1, (list_bottom - list_top) // row_h)
        n = len(self.options)

        # Keep the selected row in view (scroll the window).
        if not hasattr(self, "_scroll"):
            self._scroll = 0
        if self.selected < self._scroll:
            self._scroll = self.selected
        elif self.selected >= self._scroll + visible:
            self._scroll = self.selected - visible + 1
        self._scroll = max(0, min(self._scroll, max(0, n - visible)))

        y = list_top
        for i in range(self._scroll, min(n, self._scroll + visible)):
            opt = self.options[i]
            is_sel = (i == self.selected)
            if is_sel:
                pygame.draw.rect(surface, hi,
                                 pygame.Rect(20, y, W - 40, row_h))
            label_color = hi_text if is_sel else text_c
            label = row_font.render(opt["label"], True, label_color)
            surface.blit(label, (40, y + 3))

            # Value / swatch on the right.
            if opt["kind"] == "color_choice":
                from ..colors import (swatch_rgb_font, swatch_rgb_highlight,
                                      font_color_names, highlight_color_names)
                cur = opt["get"](cfg)
                rgb = (swatch_rgb_font(cur, theme) if opt["palette"] == "font"
                       else swatch_rgb_highlight(cur, theme))
                name_color = hi_text if is_sel else accent
                name_surf = row_font.render(cur, True, name_color)
                box = pygame.Rect(W - right_pad - swatch_w,
                                  y + (row_h - swatch_w) // 2,
                                  swatch_w, swatch_w)
                # arrows hint the left/right scroll
                arrow_c = hi_text if is_sel else muted
                lx = box.x - 10
                surface.blit(name_surf,
                             (lx - name_surf.get_width(),
                              y + 3))
                pygame.draw.rect(surface, rgb, box)
                pygame.draw.rect(surface, (0, 0, 0), box, width=1)
            else:
                if opt["kind"] == "action":
                    value_str = opt["status"](self.app)
                else:
                    value = opt["get"](cfg)
                    if opt["kind"] == "bool":
                        value_str = "On" if value else "Off"
                    else:
                        value_str = str(value)
                value_color = hi_text if is_sel else accent
                value_surf = row_font.render(value_str, True, value_color)
                surface.blit(value_surf,
                             (W - right_pad - value_surf.get_width(), y + 3))
            y += row_h

        # Scroll indicators: a small up/down arrow when the list extends
        # beyond the visible window in that direction.
        cx = W // 2
        if self._scroll > 0:
            self._draw_tri(surface, cx, list_top - 9, muted, up=True)
        if self._scroll + visible < n:
            self._draw_tri(surface, cx, list_bottom + 1, muted, up=False)

        # --- pinned hint + legend (Title Case) ---
        opt = self.options[self.selected]
        hint_text = (opt["dynamic_hint"](self.app)
                     if "dynamic_hint" in opt else opt["hint"])
        hint = hint_font.render(hint_text, True, muted)
        hint_y = H - bottom_block_h + 4
        surface.blit(hint, (40, hint_y))

        legend = hint_font.render(
            "Up / Down: Choose   -   Left / Right: Change   -   "
            "L1 / R1: Jump   -   B: Back",
            True, tuple(theme["legend_text_color"]))
        surface.blit(legend, (40, hint_y + hint_h + line_gap))

    @staticmethod
    def _draw_tri(surface, cx, y, color, up: bool):
        """A small triangle indicating more list above/below."""
        s = 7
        if up:
            pts = [(cx, y - s), (cx - s, y + s), (cx + s, y + s)]
        else:
            pts = [(cx, y + s), (cx - s, y - s), (cx + s, y - s)]
        pygame.draw.polygon(surface, color, pts)


def _open_status(app):
    from .status_screen import StatusScreen
    app.push_screen(StatusScreen(app))


def _open_restore(app):
    """List systems with gamelist backups; A restores the newest."""
    from ..gamelist_merge import list_backups, restore_backup
    from .remote_flow import _MenuScreen, NoticeScreen

    backups = list_backups(app.port_dir)
    if not backups:
        app.push_screen(NoticeScreen(
            app, "No backups yet",
            "Backups are made automatically the first time Fetch "
            "injects game details into a system's gamelist.xml."))
        return

    class _RestoreScreen(_MenuScreen):
        def __init__(self, app):
            super().__init__(app, "Restore which gamelist?")
            self.backups = backups
            self.items = [f"{b['shortname']}  (backup from {b['stamp']})"
                          for b in backups]
            self.status = ("Restoring replaces the system's current "
                           "gamelist.xml with the backup.")

        def _activate(self, index):
            b = self.backups[index]
            system = None
            for s in getattr(app, "all_systems", []) or []:
                if s["shortname"] == b["shortname"]:
                    system = s
                    break
            if system is None:
                # fall back: derive the dir from any loaded system list
                from pathlib import Path
                roms_root = Path(app.roms_dir)
                system = {"path": str(roms_root / b["shortname"])}
            ok = restore_backup(system["path"], b["path"])
            self.app.pop_screen()
            self.app.push_screen(NoticeScreen(
                app,
                "Restored" if ok else "Restore failed",
                (f"{b['shortname']}'s gamelist.xml was restored from "
                 f"the {b['stamp']} backup."
                 if ok else
                 "Couldn't write the gamelist. Check pocketcurator.log.")))

    app.push_screen(_RestoreScreen(app))
