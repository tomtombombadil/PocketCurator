"""
The game list screen - the main view per the project spec.

Left 40%: scrollable list of games. Highlighted entry marquee-scrolls if
its name overflows the column width.

Right 60%:
    - Image at top, dimensions follow the source aspect ratio.
    - One-line rating + region beneath the image.
    - Scrolling description filling the rest of the right panel.

Bottom: legend of button hints.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, List, Optional, Set

import pygame

from ..gamelist import Game
from ..render import (
    draw_stars,
    draw_wrapped_text,
    render_clipped_text,
    wrap_text,
)


def x_pad_left_anticipated(is_flag: bool, font: pygame.font.Font) -> int:
    """How much horizontal space the flagged-X marker will eat. Used by
    the marquee math to bound scroll properly when the row is flagged."""
    if not is_flag:
        return 0
    x_size = max(10, int(font.get_height() * 0.60))
    return x_size + 10


class GameListScreen:
    """One instance per system. Owns its own scroll state."""

    def __init__(self, app, system: dict, games: List[Game],
                 systems: Optional[List[dict]] = None,
                 system_index: int = 0,
                 on_system_changed: Optional[Callable[[int], None]] = None):
        self.app = app
        self.system = system
        self.games: List[Game] = games
        # Carousel context. Used by the L/R-switches-system feature; when
        # absent the L/R keys do nothing (legacy callers that only pass
        # a single system still work).
        self.systems = systems or [system]
        self.system_index = system_index
        self._on_system_changed = on_system_changed

        self.selected = 0
        self.scroll = 0                     # index of top visible game
        self.flagged: Set[int] = set()      # indices into self.games

        # Marquee state for the highlighted name
        self._marquee_anchor_ms = pygame.time.get_ticks()
        self._last_selection = -1

        # Description state
        self._desc_offset_px = 0.0
        self._desc_lines_cache: Optional[List[str]] = None
        self._desc_lines_cache_key: tuple = ()  # (selected_index, font_size, rect_width)
        # Cached during draw so the L2/R2 handlers know how much they
        # can scroll without doing the wrap_text work themselves.
        self._desc_total_h: int = 0
        self._desc_visible_h: int = 0
        self._desc_line_h: int = 0
        # Set true the first time the user presses L2/R2 - disables
        # autoscroll for this selection. Resets when selection changes.
        self._desc_manual: bool = False

        # Image debounce
        self._image_due_ms = 0
        self._current_image: Optional[pygame.Surface] = None
        self._current_image_path: Optional[Path] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type != pygame.KEYDOWN:
            return

        key = event.key
        if key == pygame.K_ESCAPE:
            self.app.pop_screen()
        elif key == pygame.K_DOWN:
            self._move(+1)
        elif key == pygame.K_UP:
            self._move(-1)
        elif key == pygame.K_LEFT:
            # ES-style: change to the previous system's game list. No-op
            # if there's only one system in the carousel context.
            self._switch_system(-1)
        elif key == pygame.K_RIGHT:
            self._switch_system(+1)
        elif key == pygame.K_PAGEDOWN:
            self._page(+1)
        elif key == pygame.K_PAGEUP:
            self._page(-1)
        elif key == pygame.K_HOME:
            self._jump_to(0)
        elif key == pygame.K_END:
            self._jump_to(len(self.games) - 1)
        elif key == pygame.K_RETURN:
            # A button.
            #
            # Tap: just toggle the current game's mark. The user is
            # making a single deliberate choice.
            #
            # Hold (auto-repeat): each repeat advances to the next
            # game and marks it. This makes holding A a fast mass-mark
            # pass. We advance BEFORE toggling - if we toggled the
            # current game first, the initial-press mark would get
            # un-marked on the first repeat (which is what happens if
            # you do toggle-then-move).
            #
            # If advance is a no-op (already at the last game), skip
            # the toggle entirely to avoid flicker-marking the bottom
            # game on every repeat tick.
            if self.app.is_repeat(key):
                old = self.selected
                self._move(+1, wrap=False)
                if self.selected != old:
                    self._toggle_flag()
            else:
                self._toggle_flag()
        elif key == pygame.K_x:
            # X button: delete flagged
            self._begin_delete()
        elif key == pygame.K_y:
            # Y button: search (jump to first game starting with a letter)
            from .jump import JumpScreen
            self.app.push_screen(JumpScreen(self.app, self.games,
                                              on_pick=self._jump_to))
        elif key == pygame.K_F1:
            # Select button: settings
            from .settings_screen import SettingsScreen
            self.app.push_screen(SettingsScreen(self.app))
        elif key == pygame.K_LEFTBRACKET:
            # L2: page up. Takes manual control - autoscroll won't fight us.
            self._desc_manual = True
            page = max(20, self._desc_visible_h - self._desc_line_h)
            self._desc_offset_px = max(0.0, self._desc_offset_px - page)
        elif key == pygame.K_RIGHTBRACKET:
            # R2: page down, clamped to last line so we never scroll into
            # blank space past the end of the description.
            self._desc_manual = True
            page = max(20, self._desc_visible_h - self._desc_line_h)
            max_offset = max(0, self._desc_total_h - self._desc_visible_h)
            self._desc_offset_px = min(float(max_offset),
                                       self._desc_offset_px + page)

    def draw(self, surface: pygame.Surface) -> None:
        cfg = self.app.config
        theme = cfg["theme"]
        ui = cfg["ui"]
        screen_w, screen_h = surface.get_size()

        surface.fill(tuple(theme["background_color"]))

        legend_h = max(28, ui["font_size_base"] + 8)
        list_w = int(screen_w * ui["list_width_pct"])
        right_x = list_w
        right_w = screen_w - list_w

        # Reset description scroll if the selection changed. Note we MUST
        # invalidate the cache_key here too - without that, the re-wrap
        # below skips because cache_key looks unchanged, but cache itself
        # is None, and len(None) crashes _draw_right_panel.
        if self._last_selection != self.selected:
            self._marquee_anchor_ms = pygame.time.get_ticks()
            self._desc_offset_px = 0.0
            self._desc_lines_cache = None
            self._desc_lines_cache_key = ()
            self._desc_manual = False
            self._image_due_ms = pygame.time.get_ticks() + ui["image_load_debounce_ms"]
            self._last_selection = self.selected

        self._draw_left_panel(surface, theme, ui,
                              pygame.Rect(0, 0, list_w, screen_h - legend_h))
        self._draw_right_panel(surface, theme, ui,
                               pygame.Rect(right_x, 0, right_w,
                                           screen_h - legend_h))
        self._draw_legend(surface, theme, ui,
                          pygame.Rect(0, screen_h - legend_h, screen_w, legend_h))

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _move(self, delta: int, wrap: Optional[bool] = None) -> None:
        """Move the selection by ``delta`` (signed). If ``wrap`` is None,
        wrap on a tap but not on an auto-repeat - holding the d-pad
        stops cleanly at the top/bottom instead of jumping back across
        the whole list. Pass wrap=True/False to force a behaviour."""
        if not self.games:
            return
        n = len(self.games)
        if wrap is None:
            wrap = not self.app.is_repeat()
        if wrap and (self.selected + delta < 0 or self.selected + delta >= n):
            self.selected = (self.selected + delta) % n
        else:
            self.selected = max(0, min(n - 1, self.selected + delta))
        # Keep the selection on-screen
        visible = self._visible_count()
        if self.selected < self.scroll:
            self.scroll = self.selected
        elif self.selected >= self.scroll + visible:
            self.scroll = self.selected - visible + 1

    def _switch_system(self, delta: int) -> None:
        """L/R on the games list: jump to the prev/next system's games,
        matching the EmulationStation UX. Wraps on a tap, stops on an
        auto-repeat (so holding L/R doesn't blow past every system in
        sequence)."""
        from ..gamelist import load_gamelist  # local import keeps top clean
        if not self.systems or len(self.systems) <= 1:
            return
        n = len(self.systems)
        wrap = not self.app.is_repeat()
        new_idx = self.system_index + delta
        if wrap:
            new_idx = new_idx % n
        else:
            if new_idx < 0 or new_idx >= n:
                return  # held past the edge - no-op
        new_system = self.systems[new_idx]

        self.app._show_status(f"Loading {new_system['display']}...")
        try:
            games = load_gamelist(new_system["path"],
                                  rom_extensions=new_system.get("extensions"))
        except Exception as exc:  # noqa
            print(f"[game_list] switch to {new_system['path']} failed: {exc}")
            games = []

        # Replace state in-place rather than push a new screen - keeps the
        # navigation stack one-deep and lets B-button always go back to
        # the carousel.
        self.system = new_system
        self.system_index = new_idx
        self.games = games
        self.selected = 0
        self.scroll = 0
        self.flagged.clear()
        self._marquee_anchor_ms = pygame.time.get_ticks()
        self._last_selection = -1
        self._desc_offset_px = 0.0
        self._desc_lines_cache = None
        self._desc_lines_cache_key = ()
        self._desc_manual = False
        self._image_due_ms = 0
        self._current_image = None
        self._current_image_path = None
        # Sync the carousel so backing out lands the user where they
        # actually were last.
        if self._on_system_changed is not None:
            try:
                self._on_system_changed(new_idx)
            except Exception as exc:
                print(f"[game_list] on_system_changed callback failed: {exc}")

    def _page(self, direction: int) -> None:
        """Page down (direction +1) or page up (direction -1).

        The point of paging in a curation app is to scan through a
        long list quickly while deleting as you go. So:
          - PgDn: jump forward by one full page, put the new selection
            at the TOP of the visible area. The user can then walk down
            through the page deleting things without ever having to
            arrow back up.
          - PgUp: jump backward by one full page, put the new selection
            at the BOTTOM of the visible area. Same logic in reverse -
            the user walks back up through the page deleting.
        """
        if not self.games:
            return
        visible = self._visible_count()
        last = len(self.games) - 1
        max_scroll = max(0, len(self.games) - visible)

        if direction > 0:
            new_sel = min(last, self.selected + visible)
            # Selection at top of the new page; scroll matches it,
            # clamped to max_scroll so we don't blank out the bottom.
            self.scroll = min(new_sel, max_scroll)
            self.selected = new_sel
        else:
            new_sel = max(0, self.selected - visible)
            # Selection at bottom of the new page.
            self.scroll = max(0, new_sel - visible + 1)
            self.selected = new_sel

    def _jump_to(self, idx: int) -> None:
        if not self.games:
            return
        self.selected = max(0, min(len(self.games) - 1, idx))
        # Try to centre the selection
        visible = self._visible_count()
        self.scroll = max(0, self.selected - visible // 2)

    def _toggle_flag(self) -> None:
        if not self.games:
            return
        if self.selected in self.flagged:
            self.flagged.remove(self.selected)
        else:
            self.flagged.add(self.selected)
        # Reset the marquee so the user sees an immediate visual cue that
        # the toggle registered, even before they read the flag glyph.
        self._marquee_anchor_ms = pygame.time.get_ticks()

    def _begin_delete(self) -> None:
        if not self.flagged:
            return
        flagged_games = [self.games[i] for i in sorted(self.flagged)]
        from .confirm import ConfirmDeleteScreen
        self.app.push_screen(ConfirmDeleteScreen(
            app=self.app,
            system=self.system,
            games_to_delete=flagged_games,
            on_committed=self._after_delete,
            on_cancelled=None,
        ))

    def _after_delete(self, deleted_games: List[Game]) -> None:
        """Called by ConfirmDeleteScreen after it finishes deletion."""
        removed_paths = {g.rom_path for g in deleted_games}
        new_games = [g for g in self.games if g.rom_path not in removed_paths]
        self.games = new_games
        self.flagged.clear()
        self.selected = min(self.selected, max(0, len(self.games) - 1))
        self.scroll = min(self.scroll, max(0, len(self.games) - 1))
        self._last_selection = -1  # force redraw of right panel

    def _visible_count(self) -> int:
        font_h = self.app.fonts.get(self.app.config["ui"]["font_size_base"]).get_linesize()
        avail = self.app.screen_h - max(28, self.app.config["ui"]["font_size_base"] + 8)
        return max(1, avail // font_h)

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def _draw_left_panel(self, surface, theme, ui, rect) -> None:
        # Background tint to separate the list visually
        pygame.draw.rect(surface, tuple(theme["list_bg_color"]), rect)

        font = self.app.fonts.get(ui["font_size_base"])
        line_h = font.get_linesize()
        visible = max(1, rect.height // line_h)

        # Adjust scroll if window has resized
        if self.selected < self.scroll:
            self.scroll = self.selected
        elif self.selected >= self.scroll + visible:
            self.scroll = self.selected - visible + 1

        now = pygame.time.get_ticks()
        pad_x = 8

        if not self.games:
            empty_font = self.app.fonts.get(ui["font_size_base"])
            empty = empty_font.render("No games in this system.", True,
                                      tuple(theme["muted_color"]))
            surface.blit(empty, (rect.x + pad_x, rect.y + pad_x))
            return

        for row in range(visible):
            idx = self.scroll + row
            if idx >= len(self.games):
                break
            y = rect.y + row * line_h
            game = self.games[idx]

            is_sel = (idx == self.selected)
            is_flag = idx in self.flagged

            text_color = tuple(theme["text_color"])
            if is_flag:
                text_color = tuple(theme["flagged_color"])

            if is_sel:
                pygame.draw.rect(
                    surface,
                    tuple(theme["highlight_color"]),
                    pygame.Rect(rect.x, y, rect.width, line_h),
                )
                text_color = tuple(theme["highlight_text_color"])

            # Marquee for the selected row only.
            #
            # Behavior: scroll left until the END of the text reaches the
            # right edge of the visible area, then pause briefly, snap
            # back to start, pause again, repeat. There's no point
            # scrolling past the end of the text - the whole point of the
            # marquee is to show what didn't fit, not to scroll the text
            # all the way off-screen.
            x_off = 0
            if is_sel:
                width = font.size(game.name)[0]
                limit_w = rect.width - 2 * pad_x - x_pad_left_anticipated(is_flag, font)
                if width > limit_w:
                    elapsed = now - self._marquee_anchor_ms
                    delay = ui["marquee_delay_ms"]
                    speed = ui["marquee_speed_px_per_sec"]
                    end_off = width - limit_w  # right edge of text aligned with viewport right
                    # Time to traverse from 0 to end_off at given speed
                    travel_ms = (end_off / max(1, speed)) * 1000.0
                    # Cycle: delay -> travel -> hold -> snap back -> delay -> ...
                    hold_ms = 1200
                    cycle_ms = delay + travel_ms + hold_ms
                    if elapsed < delay:
                        x_off = 0
                    elif elapsed < delay + travel_ms:
                        # Scrolling phase
                        x_off = int(speed * (elapsed - delay) / 1000.0)
                        x_off = min(x_off, end_off)
                    elif elapsed < cycle_ms:
                        # Hold at end-visible
                        x_off = end_off
                    else:
                        # Snap back and restart the cycle
                        x_off = 0
                        self._marquee_anchor_ms = now

            # Flag indicator: a red X drawn as two lines, left of the
            # game name. Oxanium doesn't have a ballot-X glyph (U+2717)
            # in its char map, and the user wanted X specifically, not
            # a bullet. Drawing as a shape is reliable.
            #
            # Colour switches to white when the row is selected because
            # red-on-red highlight is invisible. Stroke is generous so
            # the mark is legible on small handheld screens.
            display_name = game.name
            x_pad_left = 0
            if is_flag:
                x_size = max(10, int(font.get_height() * 0.60))
                x_pad_left = x_size + 10  # space taken by X + gap
                if is_sel:
                    x_color = (255, 255, 255)  # white on the red bar
                else:
                    x_color = tuple(theme["accent_color"])  # Rocknix red
                cx = rect.x + pad_x + x_size // 2
                cy = y + line_h // 2
                half = x_size // 2
                stroke = max(3, x_size // 4)
                pygame.draw.line(surface, x_color,
                                 (cx - half, cy - half),
                                 (cx + half, cy + half),
                                 stroke)
                pygame.draw.line(surface, x_color,
                                 (cx + half, cy - half),
                                 (cx - half, cy + half),
                                 stroke)

            render_clipped_text(
                surface,
                display_name,
                font,
                text_color,
                pygame.Rect(rect.x + pad_x + x_pad_left,
                            y + (line_h - font.get_height()) // 2,
                            rect.width - 2 * pad_x - x_pad_left, line_h),
                x_offset=x_off,
            )

    def _draw_right_panel(self, surface, theme, ui, rect) -> None:
        pygame.draw.rect(surface, tuple(theme["panel_bg_color"]), rect)

        if not self.games:
            return

        game = self.games[self.selected]
        pad = 16
        now = pygame.time.get_ticks()

        # ---- Image -----------------------------------------------------
        img_y = rect.y + pad
        max_img_w = rect.width - 2 * pad
        # Give the screenshot most of the panel height. The old 50% cap
        # meant 16:9 screenshots ended up height-limited and shrunken,
        # losing screen real estate to a description area that was
        # usually mostly empty. Description gets what's left below.
        max_img_h = int(rect.height * 0.70)

        if game.image and (now >= self._image_due_ms or
                           self._current_image_path == game.image):
            if self._current_image_path != game.image:
                self._current_image = self.app.images.load_scaled(
                    game.image, max_img_w, max_img_h)
                self._current_image_path = game.image
        else:
            self._current_image = None

        # Reserve the full max_img_h for the image area regardless of
        # the actual loaded image's height. This pins the metadata + 
        # description positions so they don't shift down when a previously-
        # not-loaded image finishes loading; before this fix you'd see the
        # text render first, then the image appear and shove the text down,
        # which felt jarring when scrolling. Worth a bit of empty space
        # below short images for stable layout.
        img_area_bottom = img_y + max_img_h
        if self._current_image is not None:
            img_w = self._current_image.get_width()
            img_h = self._current_image.get_height()
            img_x = rect.x + (rect.width - img_w) // 2
            # Centre vertically within the reserved area so a short image
            # doesn't hug the top.
            img_y_centered = img_y + (max_img_h - img_h) // 2
            surface.blit(self._current_image, (img_x, img_y_centered))
        else:
            # Placeholder rectangle - takes the full reserved area so its
            # bottom matches img_area_bottom (no layout shift on load).
            ph = pygame.Rect(rect.x + pad, img_y, max_img_w, max_img_h)
            pygame.draw.rect(surface, tuple(theme["list_bg_color"]), ph)
            placeholder_font = self.app.fonts.get(ui["font_size_base"])
            label = placeholder_font.render("(no image)", True,
                                            tuple(theme["muted_color"]))
            surface.blit(label, (ph.centerx - label.get_width() // 2,
                                 ph.centery - label.get_height() // 2))
        img_bottom = img_area_bottom

        # ---- Metadata line --------------------------------------------
        meta_font = self.app.fonts.get(max(12, int(ui["font_size_base"] * 0.8)))
        meta_y = img_bottom + 8
        x = rect.x + pad

        if game.rating is not None and self.app.config.get("ratings_display", "stars") == "stars":
            w = draw_stars(
                surface, x, meta_y + 2, game.rating,
                accent=tuple(theme["accent_color"]),
                muted=tuple(theme["muted_color"]),
                star_size=meta_font.get_height() - 2,
            )
            x += w + 12
        elif game.rating is not None:
            txt = f"{game.rating * 5.0:.1f} / 5"
            surf = meta_font.render(txt, True, tuple(theme["accent_color"]))
            surface.blit(surf, (x, meta_y))
            x += surf.get_width() + 12

        if game.region:
            region_surf = meta_font.render(game.region, True,
                                           tuple(theme["muted_color"]))
            surface.blit(region_surf, (x, meta_y))
            x += region_surf.get_width() + 12

        if game.genre:
            gs = meta_font.render(game.genre, True, tuple(theme["muted_color"]))
            surface.blit(gs, (x, meta_y))

        meta_bottom = meta_y + meta_font.get_height() + 6

        # ---- Description ----------------------------------------------
        desc_font = self.app.fonts.get(max(12, int(ui["font_size_base"] * 0.85)))
        desc_rect = pygame.Rect(
            rect.x + pad,
            meta_bottom,
            rect.width - 2 * pad,
            rect.bottom - meta_bottom - pad,
        )

        # Re-wrap only when something changed
        cache_key = (self.selected, ui["font_size_base"], desc_rect.width)
        if self._desc_lines_cache_key != cache_key:
            self._desc_lines_cache = wrap_text(
                game.desc or "", desc_font, desc_rect.width)
            self._desc_lines_cache_key = cache_key

        # Cache description metrics so the L2/R2 handlers can page by the
        # visible window without recomputing the wrap.
        self._desc_line_h = desc_font.get_linesize()
        self._desc_total_h = self._desc_line_h * len(self._desc_lines_cache or [])
        self._desc_visible_h = desc_rect.height

        # Auto-scroll: ping-pong with a brief pause at each end. Does NOT
        # run if the user has taken manual control via L2/R2.
        if (ui.get("description_autoscroll")
                and not self._desc_manual
                and self._desc_lines_cache):
            overflow = max(0, self._desc_total_h - self._desc_visible_h)
            if overflow > 0:
                # We store direction in a small private field so the
                # ping-pong survives across frames.
                if not hasattr(self, "_desc_dir"):
                    self._desc_dir = 1  # 1 = scrolling down, -1 = up
                    self._desc_pause_until_ms = 0
                now = pygame.time.get_ticks()
                if now >= self._desc_pause_until_ms:
                    speed = ui["description_autoscroll_speed_px_per_sec"]
                    self._desc_offset_px += (
                        self._desc_dir * speed / max(1, ui["fps_cap"]))
                    if self._desc_offset_px >= overflow:
                        self._desc_offset_px = float(overflow)
                        self._desc_dir = -1
                        self._desc_pause_until_ms = now + 1500
                    elif self._desc_offset_px <= 0:
                        self._desc_offset_px = 0.0
                        self._desc_dir = 1
                        self._desc_pause_until_ms = now + 1500

        draw_wrapped_text(
            surface, self._desc_lines_cache or [], desc_font,
            tuple(theme["text_color"]), desc_rect,
            y_offset=int(self._desc_offset_px),
        )

    def _draw_legend(self, surface, theme, ui, rect) -> None:
        pygame.draw.rect(surface, tuple(theme["legend_bg_color"]), rect)
        font = self.app.fonts.get(max(11, int(ui["font_size_base"] * 0.7)))
        text_color = tuple(theme["legend_text_color"])

        flagged_count = len(self.flagged)
        delete_hint = f"X Delete ({flagged_count})" if flagged_count else "X Delete"

        items = [
            "A Mark",
            "B Back",
            delete_hint,
            "Y Jump",
            "Sel Settings",
            "L1/R1 PgUp/PgDn",
        ]
        legend_str = "  \u2022  ".join(items)
        surf = font.render(legend_str, True, text_color)
        surface.blit(surf, (rect.x + 8,
                            rect.y + (rect.height - surf.get_height()) // 2))
