"""
Exit prompt - the last thing the user sees before the app quits.

Pocket Curator refreshes EmulationStation automatically on exit - when
games changed, and when our own Ports entry still needs its description
and artwork written. That write can only happen once ES is back at its
menu, so ES visibly reloads its game lists a few seconds AFTER the app
closes. Unannounced, that reads as "it crashed and took ES with it", so
this screen says up front that it is coming.
"""

from __future__ import annotations

import pygame


class ExitPromptScreen:
    def __init__(self, app):
        self.app = app

    def handle_event(self, event):
        if event.type != pygame.KEYDOWN:
            return
        # B button (Escape) is the only key that quits. Any other key
        # returns to the app. Quitting is the "scary" action so we make
        # it the deliberate one rather than the default.
        if event.key == pygame.K_ESCAPE:
            self.app.request_quit()
        else:
            self.app.pop_screen()

    def _fit_font(self, text, base_size, max_width):
        """Largest font (<= base_size) whose rendering of `text` fits
        within max_width. Keeps confirmation text on one line on narrow /
        1:1 screens instead of overflowing the edges."""
        size = base_size
        while size > 10:
            f = self.app.fonts.get(size)
            if f.size(text)[0] <= max_width:
                return f
            size -= 1
        return self.app.fonts.get(10)

    def draw(self, surface):
        cfg = self.app.config
        theme = cfg["theme"]
        ui = cfg["ui"]
        surface.fill(tuple(theme["background_color"]))

        screen_w = surface.get_width()
        max_w = screen_w - 48   # side margins; safe on 1:1 screens

        title_text = "Quit Pocket Curator?"
        hint_text = "Press B to quit  -  any other button to cancel"

        title_font = self._fit_font(title_text, int(ui["font_size_base"] * 1.4), max_w)
        hint_font = self._fit_font(hint_text, ui["font_size_base"], max_w)

        title = title_font.render(title_text, True, tuple(theme["text_color"]))
        surface.blit(title,
                     ((screen_w - title.get_width()) // 2,
                      surface.get_height() // 2 - title.get_height()))

        hint = hint_font.render(hint_text, True, tuple(theme["legend_text_color"]))
        surface.blit(hint,
                     ((screen_w - hint.get_width()) // 2,
                      surface.get_height() // 2 + hint.get_height()))

        # Tell them what will happen AFTER they quit. EmulationStation
        # visibly reloads its game lists when we write our entry or when
        # games have changed - and an unannounced reload, right after the
        # app disappears, reads as "it crashed and took ES with it".
        # Saying it up front turns a scare into an expectation.
        meta = bool(getattr(self.app, "metadata_pending", False))
        changed = (bool(getattr(self.app, "deletions_occurred", False))
                   or bool(getattr(self.app, "fetches_occurred", False)))
        notes = []
        if meta and changed:
            notes = ["After you exit, Emulation Station will refresh to add",
                     "Pocket Curator's details and update your games list.",
                     "This is normal."]
        elif meta:
            notes = ["After you exit, Emulation Station will refresh to",
                     "add Pocket Curator's details. This is normal."]
        elif changed:
            notes = ["Your Emulation Station gameslist will",
                     "automatically refresh after you exit."]

        if notes:
            note_font = self._fit_font(max(notes, key=len),
                                       max(11, int(ui["font_size_base"] * 0.85)),
                                       max_w)
            top = (surface.get_height() // 2 - title.get_height() * 2 - 8
                   - (len(notes) - 1) * (note_font.get_linesize() + 2))
            for i, line in enumerate(notes):
                note = note_font.render(line, True, tuple(theme["muted_color"]))
                surface.blit(note,
                             ((screen_w - note.get_width()) // 2,
                              top + i * (note_font.get_linesize() + 2)))
