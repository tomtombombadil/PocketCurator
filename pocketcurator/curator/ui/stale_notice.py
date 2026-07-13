"""
Missing-ROMs notice.

gamelist.xml is the source of truth - for EmulationStation and for us.
When it lists a game whose ROM isn't on the card, the two disagree: ES
hides the entry, but our count (which counts entries, as it must) still
includes it. That's why a system can read higher in Pocket Curator than
in ES.

EmulationStation never removes those entries on its own. "Update
Gamelists" only scans for NEW ROMs; it does not garbage-collect entries
whose ROM has gone. The function that does clean them is ES's own
"Clean Gamelist & Remove Unused Media".

So Pocket Curator's job here is to REPORT, not repair. We prune entries
for ROMs we delete ourselves (cleaning up after ourselves), but
pre-existing drift belongs to ES, and ES stays the only owner of its own
file. This module names the affected games and points at the fix.
"""

from __future__ import annotations

import pygame


class MissingRomsScreen:
    """Modal listing the games whose ROMs are missing from the card.

    The list scrolls with L1/R1 (PageUp/PageDown, per the gptk mapping)
    and the D-pad, so a system with dozens of stale entries can still be
    read in full. The instruction line sits BELOW the scroll area, so it
    stays visible no matter where the list is scrolled to.
    """

    def __init__(self, app, system_display: str, names: list):
        self.app = app
        self.system_display = system_display
        self.names = list(names)
        self.scroll = 0
        self._rows_visible = 1   # recomputed in draw() from real geometry

    # -- input ---------------------------------------------------------
    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type != pygame.KEYDOWN:
            return
        key = event.key
        if key in (pygame.K_RETURN, pygame.K_ESCAPE):
            self.app.pop_screen()
        elif key == pygame.K_PAGEDOWN:       # R1
            self._scroll_by(self._rows_visible)
        elif key == pygame.K_PAGEUP:         # L1
            self._scroll_by(-self._rows_visible)
        elif key == pygame.K_DOWN:
            self._scroll_by(1)
        elif key == pygame.K_UP:
            self._scroll_by(-1)

    def _scroll_by(self, delta: int) -> None:
        max_scroll = max(0, len(self.names) - self._rows_visible)
        self.scroll = max(0, min(self.scroll + delta, max_scroll))

    # -- draw ----------------------------------------------------------
    def draw(self, surface: pygame.Surface) -> None:
        below = self.app.screen_below(self)
        if below is not None:
            below.draw(surface)
        overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 200))
        surface.blit(overlay, (0, 0))

        from ..render import wrap_text
        theme = self.app.config["theme"]
        base = self.app.config["ui"]["font_size_base"]
        text_c = tuple(theme["text_color"])
        muted = tuple(theme["muted_color"])
        hi = tuple(theme["highlight_color"])
        panel = tuple(theme["panel_bg_color"])

        title_font = self.app.fonts.get(int(base * 1.1))
        row_font = self.app.fonts.get(max(11, int(base * 0.85)))
        foot_font = self.app.fonts.get(max(10, int(base * 0.72)))

        pad = max(14, int(base * 0.7))
        box_w = min(surface.get_width() - 40, max(560, base * 26))
        box_h = surface.get_height() - 40
        box = pygame.Rect((surface.get_width() - box_w) // 2,
                          (surface.get_height() - box_h) // 2, box_w, box_h)
        pygame.draw.rect(surface, panel, box)
        pygame.draw.rect(surface, hi, box, width=2)

        inner_w = box.w - 2 * pad

        # Title
        y = box.y + pad
        title = f"Missing ROMs Detected: {len(self.names)}"
        surface.blit(title_font.render(title, True, text_c), (box.x + pad, y))
        y += title_font.get_linesize() + 2
        surface.blit(row_font.render(self.system_display, True, muted),
                     (box.x + pad, y))
        y += row_font.get_linesize() + 6

        # Measure the footer FIRST, so the scroll area knows where to end.
        foot_text = ("Run Emulation Station's 'Clean Gamelist & Remove Unused "
                     "Media' from the System > Frontend Developer Options menu "
                     "to clear this message.")
        foot_lines = wrap_text(foot_text, foot_font, inner_w)
        ok_h = row_font.get_linesize() + 12
        foot_h = len(foot_lines) * (foot_font.get_linesize() + 2)
        footer_top = box.bottom - pad - ok_h - 8 - foot_h

        # Scrollable list area, between the title and the footer.
        list_top = y
        list_bottom = footer_top - 8
        row_h = row_font.get_linesize() + 2
        self._rows_visible = max(1, (list_bottom - list_top) // row_h)
        max_scroll = max(0, len(self.names) - self._rows_visible)
        self.scroll = max(0, min(self.scroll, max_scroll))

        # Leave room for the scroll indicator when the list overflows.
        rows_drawn = self._rows_visible - (1 if max_scroll else 0)
        rows_drawn = max(1, rows_drawn)
        visible = self.names[self.scroll:self.scroll + rows_drawn]

        ry = list_top
        for name in visible:
            label = name
            while row_font.size(label)[0] > inner_w - 14 and len(label) > 4:
                label = label[:-2]
            if label != name:
                label += "..."
            surface.blit(row_font.render(label, True, text_c),
                         (box.x + pad + 4, ry))
            ry += row_h

        # Scroll affordance: only when there's more than fits.
        if max_scroll:
            shown_to = self.scroll + len(visible)
            pos = f"{self.scroll + 1}-{shown_to} of {len(self.names)}"
            hint = foot_font.render(f"L1/R1 to scroll   {pos}", True, muted)
            surface.blit(hint, (box.right - pad - hint.get_width(),
                                list_bottom - foot_font.get_linesize()))

        # Divider, then the always-visible instruction below the list.
        pygame.draw.line(surface, muted,
                         (box.x + pad, footer_top - 6),
                         (box.right - pad, footer_top - 6))
        fy = footer_top
        for ln in foot_lines:
            surface.blit(foot_font.render(ln, True, text_c), (box.x + pad, fy))
            fy += foot_font.get_linesize() + 2

        # OK bar, pinned to the bottom.
        bar = pygame.Rect(box.x + pad, box.bottom - pad - ok_h, inner_w, ok_h)
        pygame.draw.rect(surface, hi, bar)
        lbl = row_font.render("OK", True, panel)
        surface.blit(lbl, (bar.centerx - lbl.get_width() // 2,
                           bar.centery - lbl.get_height() // 2))


def warn_if_stale(app, system: dict, stats: dict) -> None:
    """Show a one-time notice naming the games whose ROMs are missing.

    Shown once per system per session; a dialog on every entry would be
    more annoying than the problem it reports.
    """
    missing = int(stats.get("missing", 0) or 0)
    if missing <= 0:
        return

    seen = getattr(app, "_stale_warned", None)
    if seen is None:
        seen = set()
        app._stale_warned = seen
    key = system.get("shortname") or str(system.get("path", ""))
    if key in seen:
        return
    seen.add(key)

    display = system.get("display") or system.get("shortname") or "this system"
    names = stats.get("missing_names") or []
    print(f"[gamelist] {display}: {missing} gamelist entr"
          f"{'y' if missing == 1 else 'ies'} with no ROM on disk - "
          f"advising ES 'Clean Gamelist & Remove Unused Media'")

    try:
        app.push_screen(MissingRomsScreen(app, display, names))
    except Exception as exc:  # noqa: BLE001 - a notice must never crash the app
        print(f"[gamelist] missing-ROMs notice unavailable: {exc}")
