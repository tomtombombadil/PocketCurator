"""
System browser - ES-style carousel of available systems.

Left/right navigates. A enters the game list for that system. B exits to
the exit prompt. Y opens settings.

The carousel shows the actual logo image from the user's currently
installed ES theme if we can find one; otherwise it falls back to
the system's display name in text. See curator/theme.py for the
detection logic.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

import pygame

from ..gamelist import load_gamelist
from ..theme import find_system_logo


class SystemBrowserScreen:
    def __init__(self, app, systems):
        self.app = app
        self.systems = systems
        self.selected = 0

        # Cache the resolved logo path per system. None means "no logo
        # found"; absent means "not looked up yet". Path means hit.
        self._logo_paths: Dict[str, Optional[Path]] = {}

    def handle_event(self, event):
        if event.type != pygame.KEYDOWN:
            return

        if event.key == pygame.K_LEFT:
            if self.systems:
                if self.app.is_repeat():
                    # Holding L: stop at the start instead of wrapping
                    self.selected = max(0, self.selected - 1)
                else:
                    self.selected = (self.selected - 1) % len(self.systems)
        elif event.key == pygame.K_RIGHT:
            if self.systems:
                if self.app.is_repeat():
                    self.selected = min(len(self.systems) - 1,
                                        self.selected + 1)
                else:
                    self.selected = (self.selected + 1) % len(self.systems)
        elif event.key == pygame.K_UP:
            self.selected = max(0, self.selected - 1)
        elif event.key == pygame.K_DOWN:
            self.selected = min(max(0, len(self.systems) - 1), self.selected + 1)
        elif event.key == pygame.K_RETURN:
            self._enter_selected()
        elif event.key == pygame.K_x:
            self._begin_delete_system()
        elif event.key == pygame.K_y:
            # Fetch from WebDAV into the highlighted system - the
            # destination is decided by what's under the cursor, so the
            # flow never has to ask where files are going. Guarded so a
            # missing runtime piece degrades to a log line, never a
            # crash (v0.63.0's ssl ImportError took down the whole app).
            if self.systems:
                try:
                    from .remote_flow import start_fetch
                    targets = getattr(self.app, "fetch_targets",
                                      None) or self.systems
                    start_fetch(self.app, self.systems[self.selected],
                                targets)
                except Exception as exc:  # noqa: BLE001
                    print(f"[fetch] feature unavailable: {exc}")
        elif event.key == pygame.K_ESCAPE:
            from .exit_prompt import ExitPromptScreen
            self.app.push_screen(ExitPromptScreen(self.app))
        elif event.key == pygame.K_F1:
            from .settings_screen import SettingsScreen
            self.app.push_screen(SettingsScreen(self.app))

    def _enter_selected(self):
        if not self.systems:
            return
        system = self.systems[self.selected]
        # Big collections (SNES no-intro = 1500+ games) take a couple of
        # seconds to parse + ghost-filter. Tell the user we're working
        # rather than freezing in silence. Lightweight overlay keeps
        # the carousel visible underneath.
        self.app._show_status(f"Loading {system['display']}...")
        try:
            games = load_gamelist(system["path"],
                                  rom_extensions=system.get("extensions"))
        except Exception as exc:  # noqa - never crash on a malformed XML
            print(f"[system_browser] failed to load {system['path']}: {exc}")
            games = []

        from .game_list import GameListScreen

        def _sync_selection(idx: int) -> None:
            """Called by GameListScreen when the user used L/R to jump to
            a different system. Keeps the carousel's selection in sync
            so backing out (B button) returns to the system the user was
            actually viewing."""
            if 0 <= idx < len(self.systems):
                self.selected = idx

        self.app.push_screen(GameListScreen(
            self.app, system, games,
            systems=self.systems,
            system_index=self.selected,
            on_system_changed=_sync_selection,
        ))

    def _begin_delete_system(self) -> None:
        """X on the carousel: delete every game in the highlighted system,
        plus all of its scraped media. Confirmation is mandatory."""
        if not self.systems:
            return
        system = self.systems[self.selected]
        self.app._show_status(f"Loading {system['display']}...")
        try:
            games = load_gamelist(system["path"],
                                  rom_extensions=system.get("extensions"))
        except Exception as exc:  # noqa
            print(f"[system_browser] system-delete load failed: {exc}")
            games = []
        if not games:
            print("[system_browser] no games found - nothing to delete")
            return
        from .confirm import ConfirmDeleteScreen
        self.app.push_screen(ConfirmDeleteScreen(
            app=self.app,
            system=system,
            games_to_delete=games,
            on_committed=None,
            on_cancelled=None,
            scope="system",
        ))

    # ------------------------------------------------------------------
    # Logo resolution (lazy, cached)
    # ------------------------------------------------------------------

    def _resolve_logo(self, system: dict) -> Optional[Path]:
        shortname = system["shortname"]
        if shortname in self._logo_paths:
            return self._logo_paths[shortname]
        # Prefer ES's theme key (from es_systems.cfg) when available -
        # it's the name the active theme is actually expecting. Fall
        # back to the shortname if missing.
        lookup_name = system.get("theme") or shortname
        region = getattr(self.app, "artwork_region", None)
        subsets = getattr(self.app, "theme_subsets", None)
        path = find_system_logo(self.app.theme_dir, lookup_name, region, subsets)
        source = "active theme"
        if path is None:
            # Active theme has no logo for this system: borrow one from the
            # firmware system-theme / another installed theme before we
            # drop to a text label.
            for fb in getattr(self.app, "fallback_theme_dirs", []):
                path = find_system_logo(fb, lookup_name, region, subsets)
                if path is not None:
                    source = f"fallback:{fb.name}"
                    break
        if path is None:
            print(f"[theme] no logo found for system '{shortname}' "
                  f"(theme key '{lookup_name}')")
        else:
            print(f"[theme] logo for '{shortname}': {path.name} ({source})")
        self._logo_paths[shortname] = path
        return path

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def draw(self, surface):
        cfg = self.app.config
        theme = cfg["theme"]
        ui = cfg["ui"]
        screen_w = surface.get_width()
        screen_h = surface.get_height()
        surface.fill(tuple(theme["background_color"]))

        title_font = self.app.fonts.get(int(ui["font_size_base"] * 1.5),
                                        bold=True)
        small_font = self.app.fonts.get(max(11, int(ui["font_size_base"] * 0.7)))
        list_font = self.app.fonts.get(ui["font_size_base"])

        # Title bar
        title = title_font.render("Pocket Curator", True,
                                  tuple(theme["text_color"]))
        surface.blit(title, ((screen_w - title.get_width()) // 2, 22))

        # Version + build, centered directly under the title. (Previously
        # this sat in the bottom-right of the legend bar where the help
        # text could overrun it; the firmware/roms/theme line that used
        # to be here has moved to the Settings screen.)
        from .. import __version__, __build__
        ver_font = self.app.fonts.get(max(11, int(ui["font_size_base"] * 0.7)))
        ver_surf = ver_font.render(f"v{__version__}  build {__build__}",
                                   True, tuple(theme["muted_color"]))
        surface.blit(ver_surf,
                     ((screen_w - ver_surf.get_width()) // 2,
                      22 + title.get_height() + 6))

        if not self.systems:
            msg = list_font.render("No systems with ROMs were found.",
                                   True, tuple(theme["muted_color"]))
            surface.blit(msg,
                         ((screen_w - msg.get_width()) // 2, screen_h // 2))
            self._draw_legend(surface, theme, ui)
            return

        centre_x = screen_w // 2
        centre_y = screen_h // 2

        # Region we will paint logos/names into. Cap is screen-height-
        # relative so high-res screens (RG552 etc.) actually get a
        # proportionally large logo instead of a 480px cap that looks
        # tiny on 1920x1152.
        focus_w = min(screen_w // 2 - 40, int(screen_h * 0.75))
        focus_h = screen_h // 3
        side_w = focus_w * 6 // 10
        side_h = focus_h * 6 // 10

        # Geometry: focused item dead-centre; one neighbour each side
        # slightly smaller, two more on the wings further out.
        slots = [
            (-2, centre_x - focus_w - side_w - 60, side_w * 7 // 10, side_h * 7 // 10,
             small_font, tuple(theme["muted_color"])),
            (-1, centre_x - focus_w // 2 - side_w // 2 - 30, side_w, side_h,
             list_font, tuple(theme["muted_color"])),
            (0, centre_x, focus_w, focus_h, title_font,
             tuple(theme["highlight_text_color"])),
            (+1, centre_x + focus_w // 2 + side_w // 2 + 30, side_w, side_h,
             list_font, tuple(theme["muted_color"])),
            (+2, centre_x + focus_w + side_w + 60, side_w * 7 // 10, side_h * 7 // 10,
             small_font, tuple(theme["muted_color"])),
        ]

        n = len(self.systems)
        drawn = set()
        for offset, cx, max_w, max_h, font, name_color in slots:
            if n == 0:
                break
            # Wrap around the ends so the carousel display matches its
            # wrap-around behaviour (last system sits left of the first).
            idx = (self.selected + offset) % n
            # The focused system always owns the centre slot. Neighbour
            # slots are skipped if they'd duplicate the focused system or
            # one already drawn (happens only with very short lists).
            if offset != 0 and (idx == self.selected or idx in drawn):
                continue
            drawn.add(idx)
            sys = self.systems[idx]

            logo_path = self._resolve_logo(sys)
            logo = None
            if logo_path is not None:
                logo = self.app.images.load_scaled(logo_path, max_w, max_h)

            if logo is not None:
                lw, lh = logo.get_size()
                surface.blit(logo, (cx - lw // 2, centre_y - lh // 2))
            elif abs(offset) <= 1:
                # Text fallback: show previous / current / next system
                # names. Each name is wrapped to ITS OWN slot width, so
                # neighbouring names stay inside their slots and never
                # overlap (the original bug was full-width names centred on
                # the side slots bleeding into the middle). The far wings
                # (offset +/-2) are left blank in text mode to keep it clean.
                from ..render import wrap_text
                lines = wrap_text(sys["display"], font, max(40, max_w))
                line_h = font.get_height() + 2
                block_h = line_h * len(lines)
                ly = centre_y - block_h // 2
                for line in lines:
                    ls = font.render(line, True, name_color)
                    surface.blit(ls, (cx - ls.get_width() // 2, ly))
                    ly += line_h

            if offset == 0:
                count_txt = (f"{sys['rom_count']} game"
                             f"{'s' if sys['rom_count'] != 1 else ''}")
                count_surf = small_font.render(
                    count_txt, True, tuple(theme["accent_color"]))
                surface.blit(count_surf,
                             (cx - count_surf.get_width() // 2,
                              centre_y + max_h // 2 + 8))

        self._draw_legend(surface, theme, ui)

    def _draw_legend(self, surface, theme, ui):
        legend_h = max(28, ui["font_size_base"] + 8)
        rect = pygame.Rect(0, surface.get_height() - legend_h,
                           surface.get_width(), legend_h)
        pygame.draw.rect(surface, tuple(theme["legend_bg_color"]), rect)
        color = tuple(theme["legend_text_color"])

        # Directions first, then A, B, X, Y, Select - Title Case. The
        # font shrinks until the whole line fits the screen width, so
        # no resolution or font-size setting can push entries off the
        # right edge (seen on the 1280-wide Smart Pro S).
        sep = "  -  "
        text = ("Navigate" + sep + "A Enter" + sep + "B Exit"
                + sep + "X Delete System" + sep + "Y WebDAV"
                + sep + "Sel Settings")

        size = max(11, int(ui["font_size_base"] * 0.7))
        while size > 10:
            font = self.app.fonts.get(size)
            icon_w = font.get_height() + 6
            if icon_w + 8 + font.size(text)[0] + 16 <= rect.w:
                break
            size -= 1
        font = self.app.fonts.get(size)
        icon_w = font.get_height() + 6

        x = rect.x + 8
        y_center = rect.y + rect.height // 2
        self._blit_dpad(surface, color, x, y_center, font.get_height())
        x += icon_w + 6
        label = font.render(text, True, color)
        surface.blit(label, (x, y_center - label.get_height() // 2))

    @staticmethod
    def _blit_dpad(surface, color, x, y_center, h):
        """A d-pad glyph (ES-style cross) drawn as two crossing bars
        with a hollow center."""
        size = h - 2
        size -= size % 2
        bar = max(4, size // 3)
        top = y_center - size // 2
        cx = x + (size - bar) // 2
        cy = y_center - bar // 2
        pygame.draw.rect(surface, color,
                         pygame.Rect(cx, top, bar, size), border_radius=2)
        pygame.draw.rect(surface, color,
                         pygame.Rect(x, cy, size, bar), border_radius=2)

