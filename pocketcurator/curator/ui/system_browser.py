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
            # Fetch from WebDAV. Normally the highlighted system is both
            # the smart-jump target and the title context, but the actual
            # per-game destination is decided by the REMOTE folder name
            # (see RemoteBrowserScreen._context_for), never by what's
            # highlighted here. So when the device has no populated
            # systems yet - a fresh handheld whose ROM folders are still
            # empty - there's nothing to highlight, but the user still
            # needs to reach their server to copy ROMs ON in the first
            # place. Open the flow anyway with a neutral placeholder:
            # smart-jump simply won't jump, the user lands at the server
            # root, and copying routes into the matching (empty) ROM
            # folder via the fetch-target list. Guarded so a missing
            # runtime piece degrades to a log line, never a crash
            # (v0.63.0's ssl ImportError took down the whole app).
            try:
                from .remote_flow import start_fetch
                targets = getattr(self.app, "fetch_targets",
                                  None) or self.systems
                if self.systems:
                    launch = self.systems[self.selected]
                else:
                    launch = {"shortname": "", "display": "your device",
                              "path": "", "extensions": [], "theme": "",
                              "rom_count": 0}
                start_fetch(self.app, launch, targets)
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
        stats: dict = {}
        try:
            games = load_gamelist(system["path"],
                                  rom_extensions=system.get("extensions"),
                                  stats_out=stats)
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
        self._warn_if_gamelist_stale(system, stats)

    def _warn_if_gamelist_stale(self, system: dict, stats: dict) -> None:
        from .stale_notice import warn_if_stale
        warn_if_stale(self.app, system, stats)

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

    def refresh_counts(self) -> None:
        """Recount systems whose gamelist we changed, and pick up any
        system that has just gained its first games.

        Called ONCE when the user comes back to the carousel from the
        delete or fetch screens - not per frame. If a copy or delete is
        still running, we do nothing: the numbers would be wrong anyway,
        and re-parsing a 1300-entry gamelist every frame would stutter
        the carousel. The screens call this again when their work
        finishes.

        Two cases:
          - a system we already know changed  -> recount it (a pure
            gamelist.xml parse; no filesystem scan).
          - a system we DON'T know changed    -> it had no games at
            startup, so discovery skipped it, and the user has just
            copied the first ROMs into it. Re-run discovery so it
            appears without needing a restart.
        """
        dirty = getattr(self.app, "dirty_gamelists", None)
        if not dirty:
            return
        q = getattr(self.app, "fetch_queue", None)
        if q is not None and q.busy():
            return          # work still in flight - recount when it lands

        known = {str(Path(s.get("path", ""))) for s in self.systems}
        unknown = [p for p in dirty if p not in known]

        if unknown:
            self._rediscover(unknown)
            dirty.clear()
            return

        from ..firmware import _count_candidates
        for system in self.systems:
            path = str(Path(system.get("path", "")))
            if path not in dirty:
                continue
            try:
                before = system.get("rom_count", 0)
                system["rom_count"] = _count_candidates(
                    Path(path), system.get("extensions") or [])
                print(f"[discover] recount {system.get('shortname')}: "
                      f"{before} -> {system['rom_count']}")
            except Exception as exc:  # noqa: BLE001 - a bad count must not crash
                print(f"[discover] recount failed for {path}: {exc}")
        dirty.clear()

    def _rediscover(self, new_paths) -> None:
        """A system that was empty at startup now has games. Rebuild the
        system list so it shows up right away.

        Only happens on the rare 'first ROMs copied into a system that
        had none' event - notably the fresh-device path, where the user
        has no systems at all, connects to WebDAV, and copies their first
        games. Without this they'd have to relaunch to see them.

        Systems the user emptied THIS session are kept, showing 0 games,
        so they can see what they did and press Y to fetch straight back
        into them. They disappear on the next launch, like any empty
        system.
        """
        from ..firmware import discover_systems
        print(f"[discover] new system(s) gained games: {new_paths} - "
              f"re-running discovery")
        keep_shortname = (self.systems[self.selected].get("shortname")
                          if self.systems else None)
        try:
            fresh = discover_systems(self.app.roms_dir, self.app.systems_db)
        except Exception as exc:  # noqa: BLE001
            print(f"[discover] re-discovery failed: {exc}")
            return

        # Carry over any system we're already showing that discovery now
        # drops for having 0 games - the user emptied it this session and
        # should still see it (at 0) until restart.
        fresh_paths = {str(Path(s["path"])) for s in fresh}
        for old in self.systems:
            if str(Path(old.get("path", ""))) not in fresh_paths:
                old["rom_count"] = 0
                fresh.append(old)
                print(f"[discover] keeping emptied system "
                      f"{old.get('shortname')} visible at 0 games")

        fresh.sort(key=lambda s: (s.get("display") or "").lower())
        self.systems = fresh
        self.app.systems = fresh

        # Keep the cursor on the system the user was looking at.
        self.selected = 0
        if keep_shortname:
            for i, s in enumerate(fresh):
                if s.get("shortname") == keep_shortname:
                    self.selected = i
                    break
        self._logo_paths = {}
        print(f"[discover] carousel rebuilt: {len(fresh)} systems")

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
        from .. import __version__
        ver_font = self.app.fonts.get(max(11, int(ui["font_size_base"] * 0.7)))
        ver_surf = ver_font.render(f"v{__version__}",
                                   True, tuple(theme["muted_color"]))
        surface.blit(ver_surf,
                     ((screen_w - ver_surf.get_width()) // 2,
                      22 + title.get_height() + 6))

        if not self.systems:
            msg = list_font.render("No systems with ROMs were found.",
                                   True, tuple(theme["muted_color"]))
            surface.blit(msg,
                         ((screen_w - msg.get_width()) // 2,
                          screen_h // 2 - msg.get_height()))
            from ..render import render_prompt
            hint = render_prompt(
                small_font, theme,
                "Press Y to connect to a WebDAV server and copy ROMs onto "
                "your device.")
            surface.blit(hint,
                         ((screen_w - hint.get_width()) // 2,
                          screen_h // 2 + 6))
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

        # Navigate (d-pad) first, then the face buttons and Select as
        # chips. draw_hint_bar auto-shrinks to fit any screen width.
        from ..render import draw_hint_bar
        hints = [
            [("dpad",), ("txt", "Navigate")],
            [("chip", "A"), ("txt", "Enter")],
            [("chip", "B"), ("txt", "Exit")],
            [("chip", "X"), ("txt", "Delete System")],
            [("chip", "Y"), ("txt", "WebDAV")],
            [("chip", "SEL"), ("txt", "Settings")],
        ]
        draw_hint_bar(surface, rect, self.app.fonts,
                      ui["font_size_base"], theme, hints)

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

