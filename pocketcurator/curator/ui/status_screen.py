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

import pygame

from .. import __version__
from ..updater import Updater


class StatusScreen:
    def __init__(self, app):
        self.app = app
        self._closed = False

    # ------------------------------------------------------------------

    def _update_status(self) -> str:
        """Report the LATEST KNOWN update state without checking again -
        Check For Updates already does that. If no check has run this
        session, say so rather than reaching out to the network."""
        u = getattr(self.app, "updater", None)
        if u is None:
            return "not checked this session"
        if u.state == "staged":
            return f"v{u.latest_version} ready - restart to apply"
        if u.state == "available":
            return f"v{u.latest_version} available"
        if u.state == "up_to_date":
            return "up to date"
        if u.busy():
            return "checking..."
        return "not checked this session"

    def _refresh_status(self) -> str:
        """Whether the games list will be refreshed when Pocket Curator
        exits. Pending if anything was deleted or fetched this session.
        """
        pending = (getattr(self.app, "deletions_occurred", False)
                   or getattr(self.app, "fetches_occurred", False))
        return "Pending" if pending else "Not Necessary"

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
        rows = [
            ("Version", f"v{__version__}  ({self._update_status()})"),
            ("Refresh Games List On Exit", self._refresh_status()),
            ("OS", str(app.firmware_name)),
            ("ROMs Location", str(app.roms_dir) if app.roms_dir else "n/a"),
            ("Theme", app.theme_dir.name if app.theme_dir else "n/a"),
        ]

        label_w = max(body_font.size(lbl + ":")[0] for lbl, _ in rows) + 18
        line_h = body_font.get_linesize() + 8
        muted = tuple(theme["muted_color"])
        text = tuple(theme["text_color"])
        max_val_w = box.w - pad * 2 - label_w

        for lbl, val in rows:
            lab = body_font.render(lbl + ":", True, muted)
            surface.blit(lab, (box.x + pad, y))
            for part in self._wrap(body_font, str(val), max_val_w):
                vs = body_font.render(part, True, text)
                surface.blit(vs, (box.x + pad + label_w, y))
                y += line_h

        hint = small_font.render("Press A or B to close.", True, muted)
        surface.blit(hint, (box.x + pad, box.bottom - hint.get_height() - pad))

    @staticmethod
    def _wrap(font, s: str, max_w: int):
        """Word-wrap a row value to the panel width; over-long single
        tokens (paths) are middle-ellipsized so nothing overflows."""
        out, line = [], ""
        for word in s.split(" "):
            while font.size(word)[0] > max_w and len(word) > 8:
                word = "..." + word[5:]
            cand = (line + " " + word).strip()
            if font.size(cand)[0] <= max_w:
                line = cand
            else:
                if line:
                    out.append(line)
                line = word
        if line:
            out.append(line)
        return out or [""]
