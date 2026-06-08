"""
Exit prompt - the last thing the user sees before the app quits.

Pocket Curator refreshes EmulationStation automatically on exit when the
user deleted games, so this screen is just a simple quit confirmation.
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

        # If they deleted anything this session, reassure them the menu
        # will update on its own (the launcher reloads ES on exit).
        if getattr(self.app, "deletions_occurred", False):
            note_text = "Your Emulation Station gameslist will automatically refresh."
            note_font = self._fit_font(note_text,
                                       max(11, int(ui["font_size_base"] * 0.85)),
                                       max_w)
            note = note_font.render(note_text, True, tuple(theme["muted_color"]))
            surface.blit(note,
                         ((screen_w - note.get_width()) // 2,
                          surface.get_height() // 2 - title.get_height() * 2 - 8))
