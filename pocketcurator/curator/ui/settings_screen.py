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
            "label": "Check For Updates",
            "kind": "action",
            # status/hint/run receive the App, not the config: this row
            # reflects live updater state rather than a settings value.
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
            "label": "Restore Gamelist Backup",
            "kind": "action",
            "status": lambda app: "",
            "run": lambda app: _open_restore(app),
            "hint": ("Puts back a system's gamelist.xml from the backup "
                     "made before Fetch injected game details."),
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
            "label": "Auto-Scroll Description",
            "kind": "bool",
            "get": lambda c: bool(c["ui"]["description_autoscroll"]),
            "set": lambda c, v: c["ui"].__setitem__("description_autoscroll", v),
            "hint": "Off: use L2 / R2 to scroll manually.",
        },
        {
            "label": "Safe Mode (Doesn't Delete)",
            "kind": "bool",
            "get": lambda c: bool(c["behavior"]["deletion_dry_run"]),
            "set": lambda c, v: c["behavior"].__setitem__("deletion_dry_run", v),
            "hint": "On: deletions are simulated only. Test before committing.",
        },
        {
            "label": "Delete Scraped Media",
            "kind": "bool",
            "get": lambda c: bool(c["behavior"]["include_scraped_media"]),
            "set": lambda c, v: c["behavior"].__setitem__("include_scraped_media", v),
            "hint": "When a ROM is deleted, also remove its images, videos, marquees, manuals, screenshots, and box art.",
        },
        {
            "label": "Rating Display",
            "kind": "choice",
            "choices": ["stars", "text"],
            "get": lambda c: c.get("ratings_display", "stars"),
            "set": lambda c, v: c.__setitem__("ratings_display", v),
            "hint": "Graphical stars or a textual 'X.X / 5' label.",
        },
    ]


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
        elif event.key in (pygame.K_LEFT, pygame.K_RIGHT):
            self._adjust(+1 if event.key == pygame.K_RIGHT else -1)
        elif event.key == pygame.K_RETURN:
            # A on a bool toggles, on a choice cycles forward, on an
            # action runs it.
            opt = self.options[self.selected]
            if opt["kind"] == "bool":
                self._adjust(+1)
            elif opt["kind"] == "choice":
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

            if opt["kind"] == "action":
                value_str = opt["status"](self.app)
            else:
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

        # Hint for selected option (action rows carry a live hint)
        opt = self.options[self.selected]
        hint_text = (opt["dynamic_hint"](self.app)
                     if "dynamic_hint" in opt else opt["hint"])
        hint = hint_font.render(hint_text, True, tuple(theme["muted_color"]))
        surface.blit(hint, (40, surface.get_height() - 70))

        # Legend
        legend = hint_font.render(
            "Up/Down: choose   -   Left/Right: change   -   B: back",
            True, tuple(theme["legend_text_color"]))
        surface.blit(legend, (40, surface.get_height() - 36))

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
