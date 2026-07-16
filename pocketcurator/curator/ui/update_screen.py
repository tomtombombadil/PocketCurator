"""
Software update dialog. Opens from Settings -> Check For Updates and
runs the whole pipeline unattended - check, and when an update exists,
download + verify + stage - showing each step as it happens:

    Checking for update...
    Update found: v0.62.2
    Downloading update... 47%
    Verifying update...
    Update ready! Restart Pocket Curator to complete the update.

No mid-pipeline confirmations: if the user asked to check, they want
the update. Closing the dialog mid-download is safe - the worker keeps
going, and reopening (or the Settings row) shows current progress.
"""

from __future__ import annotations

import pygame

from .. import __version__
from ..updater import Updater


class UpdateScreen:
    def __init__(self, app, prerelease: bool = False):
        self.app = app
        if getattr(app, "updater", None) is None:
            app.updater = Updater(app.port_dir, __version__)
        self.updater = app.updater
        self.prerelease = prerelease
        # Kick the pipeline immediately; harmless no-op if it's already
        # running or an update is already staged.
        self.updater.start_full(prerelease=prerelease)

    # ------------------------------------------------------------------

    def _lines(self):
        """Progressive checklist derived from the updater's state.

        Rule: never call the running build "the latest" while offering an
        update to it. The status line only earns "(latest)" when the
        channel the user is ON has nothing newer. Saying "you're running
        the latest Pre-Release" and then offering a newer Pre-Release in
        the next breath is nonsense.
        """
        u = self.updater
        s = u.state
        lines = [("Checking for updates...", True)]

        if s == "checking":
            return lines, ""

        kind = "Pre-Release" if u.running_prerelease() else "Stable Release"

        if s == "up_to_date":
            lines.append(
                (f"You are running the latest {kind} (v{u.current_version}).",
                 True))
            return lines, "Press B to close."

        if s == "error":
            lines.append(("Update failed:", True))
            return lines, "Press A to retry, B to close."

        if s == "available":
            # Is the channel the user is ON up to date? Only then may the
            # status line say so. A newer release on the OTHER channel
            # doesn't make the running build stale.
            own_channel_current = (
                u.prerelease is None if u.running_prerelease()
                else u.stable is None)
            suffix = " (latest)" if own_channel_current else ""
            lines.append(
                (f"Running {kind} v{u.current_version}{suffix}.", True))

            keys = []
            if u.stable:
                lines.append((f"Stable Release available: "
                              f"v{u.stable['version']}", True))
                keys.append("A Install Stable")
            if u.prerelease:
                lines.append((f"Pre-Release available: "
                              f"v{u.prerelease['version']} (not fully tested)",
                              True))
                keys.append("Y Install Pre-Release")
            keys.append("B Cancel")
            return lines, "   -   ".join(keys)

        # downloading / verifying / staging / staged
        label = u.channel_label()
        if u.latest_version:
            lines.append((f"Installing {label} v{u.latest_version}", True))
        if s == "downloading":
            lines.append(
                (f"Downloading... {int(u.progress * 100)}%", True))
            return lines, "You can press B to close - it keeps downloading."
        if s in ("verifying", "staging", "staged"):
            lines.append(("Downloading... 100%", True))
            lines.append(("Verifying...", True))
        if s == "staged":
            lines.append((f"{label} v{u.latest_version} ready! Restart "
                          f"Pocket Curator to complete the update.", True))
            return lines, "Press A or B to close."
        return lines, ""

    # ------------------------------------------------------------------

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type != pygame.KEYDOWN:
            return
        u = self.updater

        if event.key == pygame.K_ESCAPE:          # B - always closes
            self.app.pop_screen()

        elif event.key == pygame.K_RETURN:        # A
            if u.state == "error":
                u.start_full()                    # retry the check
            elif u.state == "available" and u.stable:
                u.install("stable")               # take the stable release
            elif not u.busy():
                self.app.pop_screen()

        elif event.key == pygame.K_y:             # Y - pre-release
            if u.state == "available" and u.prerelease:
                u.install("prerelease")


    def draw(self, surface: pygame.Surface) -> None:
        below = self.app.screen_below(self)
        if below is not None:
            below.draw(surface)

        overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        surface.blit(overlay, (0, 0))

        cfg = self.app.config
        theme = cfg["theme"]
        base = cfg["ui"]["font_size_base"]

        box_w = min(max(720, base * 36), surface.get_width() - 80)
        box_h = min(max(360, base * 15), surface.get_height() - 80)
        box = pygame.Rect((surface.get_width() - box_w) // 2,
                          (surface.get_height() - box_h) // 2,
                          box_w, box_h)
        pygame.draw.rect(surface, tuple(theme["panel_bg_color"]), box)
        pygame.draw.rect(surface, tuple(theme["highlight_color"]), box, width=2)

        title_font = self.app.fonts.get(int(base * 1.2))
        body_font = self.app.fonts.get(base)
        small_font = self.app.fonts.get(max(11, int(base * 0.75)))
        text = tuple(theme["text_color"])
        muted = tuple(theme["muted_color"])

        pad = max(24, base)
        y = box.y + pad
        title = title_font.render("Software Update", True, text)
        surface.blit(title, (box.x + pad, y))
        y += title.get_height() + 14

        lines, footer = self._lines()
        line_h = body_font.get_linesize() + 6
        max_w = box.w - pad * 2
        for txt, _ in lines:
            for part in _wrap(body_font, txt, max_w):
                surface.blit(body_font.render(part, True, text),
                             (box.x + pad, y))
                y += line_h
        if self.updater.state == "error" and self.updater.error:
            for part in _wrap(body_font, self.updater.error, max_w):
                surface.blit(body_font.render(part, True, muted),
                             (box.x + pad, y))
                y += line_h

        if not footer and self.updater.busy():
            footer = "Working..."
        if footer:
            from ..render import render_prompt
            hint = render_prompt(small_font, theme, footer)
            surface.blit(hint,
                         (box.x + pad, box.bottom - hint.get_height() - pad))


def _wrap(font, s: str, max_w: int):
    """Greedy word wrap; a single over-long token (URL/path) gets
    middle-ellipsized rather than overflowing the panel."""
    out, line = [], ""
    for word in str(s).split(" "):
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
