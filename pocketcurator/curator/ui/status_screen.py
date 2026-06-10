"""
Status dialog. A read-only modal (same overlay style as the delete
confirmation) showing the install's vital signs: version (and whether
it's the latest), detected OS, ROMs location, active theme, internet
reachability, and whether the clock is sane enough for TLS.

The instant rows render immediately; the two network-dependent rows
(internet, latest-version) are filled in by a background thread so
opening the dialog never blocks the UI. With no connection, the
network rows read 'No Internet Connection'.
"""

from __future__ import annotations

import threading

import pygame

from .. import __version__
from ..updater import (
    Updater, check_internet, clock_is_sane, _version_tuple,
)


class StatusScreen:
    def __init__(self, app):
        self.app = app
        self._internet: str = "Checking..."
        self._latest: str = "Checking..."
        self._closed = False
        threading.Thread(target=self._probe, daemon=True).start()

    # ------------------------------------------------------------------

    def _probe(self) -> None:
        """Network rows, off the UI thread. Reuses the app's updater so
        a result here and the Check For Updates row never disagree."""
        online = check_internet()
        if self._closed:
            return
        if not online:
            self._internet = "No Internet Connection"
            self._latest = "No Internet Connection"
            return
        self._internet = "Connected"

        if getattr(self.app, "updater", None) is None:
            self.app.updater = Updater(self.app.port_dir, __version__)
        u = self.app.updater
        if u.state == "staged":
            self._latest = f"v{u.latest_version} downloaded, installs next launch"
            return
        if not u.busy():
            u.start_check()
        # Wait for the worker (bounded; it has its own timeouts).
        for _ in range(120):
            if self._closed or not u.busy():
                break
            pygame.time.wait(250)
        if u.state == "available":
            self._latest = f"v{u.latest_version} available - see Check For Updates"
        elif u.state == "up_to_date":
            self._latest = "This is the latest version"
        elif u.state == "staged":
            self._latest = f"v{u.latest_version} downloaded, installs next launch"
        else:
            self._latest = "Couldn't check (see Check For Updates)"

    # ------------------------------------------------------------------

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type != pygame.KEYDOWN:
            return
        if event.key in (pygame.K_ESCAPE, pygame.K_RETURN):
            self._closed = True
            self.app.pop_screen()

    def update(self, dt: float) -> None:
        pass

    def draw(self, surface: pygame.Surface) -> None:
        below = self.app.screen_below(self)
        if below is not None:
            below.draw(surface)

        overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        surface.blit(overlay, (0, 0))

        cfg = self.app.config
        theme = cfg["theme"]
        ui = cfg["ui"]
        base = ui["font_size_base"]

        target_w = max(720, base * 38)
        target_h = max(360, base * 17)
        box_w = min(target_w, surface.get_width() - 80)
        box_h = min(target_h, surface.get_height() - 80)
        box = pygame.Rect(
            (surface.get_width() - box_w) // 2,
            (surface.get_height() - box_h) // 2,
            box_w, box_h,
        )
        pygame.draw.rect(surface, tuple(theme["panel_bg_color"]), box)
        pygame.draw.rect(surface, tuple(theme["highlight_color"]), box, width=2)

        title_font = self.app.fonts.get(int(base * 1.2))
        body_font = self.app.fonts.get(base)
        small_font = self.app.fonts.get(max(11, int(base * 0.75)))

        pad = max(24, base)
        y = box.y + pad

        title = title_font.render("Status", True, tuple(theme["text_color"]))
        surface.blit(title, (box.x + pad, y))
        y += title.get_height() + 14

        app = self.app
        clock_ok = clock_is_sane()
        rows = [
            ("Version", f"v{__version__}  ({self._latest})"),
            ("OS", str(app.firmware_name)),
            ("ROMs Location", str(app.roms_dir) if app.roms_dir else "n/a"),
            ("Theme", app.theme_dir.name if app.theme_dir else "n/a"),
            ("Internet", self._internet),
            ("Clock", "Synced (secure connections OK)" if clock_ok
             else "Not synced - secure connections may fail"),
        ]

        label_w = max(body_font.size(lbl + ":")[0] for lbl, _ in rows) + 18
        line_h = body_font.get_linesize() + 8
        muted = tuple(theme["muted_color"])
        text = tuple(theme["text_color"])
        max_val_w = box.w - pad * 2 - label_w

        for lbl, val in rows:
            lab = body_font.render(lbl + ":", True, muted)
            surface.blit(lab, (box.x + pad, y))
            val_s = self._fit(body_font, str(val), max_val_w)
            vs = body_font.render(val_s, True, text)
            surface.blit(vs, (box.x + pad + label_w, y))
            y += line_h

        hint = small_font.render("Press A or B to close.", True, muted)
        surface.blit(hint, (box.x + pad, box.bottom - hint.get_height() - pad))

    @staticmethod
    def _fit(font, s: str, max_w: int) -> str:
        """Middle-ellipsize long values (paths) to the panel width."""
        if font.size(s)[0] <= max_w:
            return s
        while len(s) > 8 and font.size("..." + s[-(len(s) - 4):])[0] > max_w:
            s = s[1:]
        return "..." + s[-(len(s) - 4):] if len(s) > 8 else s
