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

from pathlib import Path
import pygame

import threading

from .. import __version__
from ..updater import check_internet, clock_is_sane


class StatusScreen:
    def __init__(self, app):
        self.app = app
        self._internet: str = "Checking..."
        self._clock: str = "Checking..."
        self._closed = False
        threading.Thread(target=self._probe, daemon=True).start()

    # ------------------------------------------------------------------

    def _probe(self) -> None:
        """Internet reachability + clock-sanity rows, off the UI thread.
        Deliberately does NOT check for updates - that's the Check For
        Updates row's job - it only reports connectivity and whether the
        clock is sane enough for TLS."""
        online = check_internet()
        if self._closed:
            return
        self._internet = "Connected" if online else "No Internet Connection"
        self._clock = ("Synced (secure connections OK)" if clock_is_sane()
                       else "Not synced - secure connections may fail")

    def _sd_free_text(self) -> str:
        """Free space on the volume that holds the ROMs."""
        import shutil as _sh
        roms = getattr(self.app, "roms_dir", None)
        if not roms:
            return "n/a"
        probe = Path(str(roms))
        while not probe.exists() and probe != probe.parent:
            probe = probe.parent
        try:
            free = _sh.disk_usage(probe).free
        except OSError:
            return "n/a"
        # compact human size
        units = ["B", "KB", "MB", "GB", "TB"]
        f = float(free)
        i = 0
        while f >= 1024 and i < len(units) - 1:
            f /= 1024.0
            i += 1
        return f"{f:.1f} {units[i]}"

    def _refresh_status(self) -> str:
        """Whether the games list will be refreshed when Pocket Curator
        exits. Pending if anything was deleted or fetched this session.
        """
        pending = (getattr(self.app, "deletions_occurred", False)
                   or getattr(self.app, "fetches_occurred", False))
        return "Pending (On Exit)" if pending else "Not Necessary"

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
            ("Version", f"v{__version__}"),
            ("Refresh Games List", self._refresh_status()),
            ("OS", str(app.firmware_name)),
            ("ROMs Location", str(app.roms_dir) if app.roms_dir else "n/a"),
            ("SD Card Free Space", self._sd_free_text()),
            ("Theme", app.theme_dir.name if app.theme_dir else "n/a"),
            ("Internet", self._internet),
            ("Clock", self._clock),
        ]

        muted = tuple(theme["muted_color"])
        text = tuple(theme["text_color"])

        # Auto-fit: shrink the body font until every row (label + wrapped
        # value) fits between the title and the close-hint, so nothing
        # overflows on small screens. Tighter line spacing than before to
        # pack more in.
        hint_text = "Press A or B to close."
        avail_top = y
        avail_bottom = box.bottom - small_font.get_linesize() - pad
        avail_h = avail_bottom - avail_top

        fit_size = base
        while fit_size >= 10:
            bf = self.app.fonts.get(fit_size)
            label_w = max(bf.size(lbl + ":")[0] for lbl, _ in rows) + 14
            line_h = bf.get_linesize() + 3   # tightened from +8
            max_val_w = box.w - pad * 2 - label_w
            total = 0
            for _lbl, val in rows:
                parts = self._wrap(bf, str(val), max_val_w) or [""]
                total += line_h * len(parts)
            if total <= avail_h:
                break
            fit_size -= 1

        body_font = self.app.fonts.get(fit_size)
        label_w = max(body_font.size(lbl + ":")[0] for lbl, _ in rows) + 14
        line_h = body_font.get_linesize() + 3
        max_val_w = box.w - pad * 2 - label_w

        for lbl, val in rows:
            lab = body_font.render(lbl + ":", True, muted)
            surface.blit(lab, (box.x + pad, y))
            parts = self._wrap(body_font, str(val), max_val_w) or [""]
            for part in parts:
                vs = body_font.render(part, True, text)
                surface.blit(vs, (box.x + pad + label_w, y))
                y += line_h

        hint = small_font.render(hint_text, True, muted)
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
