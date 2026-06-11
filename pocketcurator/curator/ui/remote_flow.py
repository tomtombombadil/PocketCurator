"""
The fetch flow: everything between pressing Y on a system and landing
in the remote browser.

    Y on a system
      -> SourcePickerScreen   (saved sources + "Find New WebDAV Server";
                               skipped entirely when nothing is saved)
      -> FindNewScreen        (Scan local network / Enter address)
      -> ScanScreen           (live scan progress -> results list)
      -> OSK                  (address entry, keypad layout; and
                               username/password when a server wants them)
      -> RemoteBrowserScreen  (curator/ui/remote_browser.py)

Design notes:
  - B is "back one step" everywhere in Pocket Curator, so these dialogs
    are option lists driven by d-pad + A, with B backing out - rather
    than binding actions onto B itself.
  - Saved sources persist in settings.json as url + username + dialect.
    Passwords are deliberately NOT persisted (plaintext on an SD card);
    they're remembered for the session in app memory, so a reconnect
    during the same run never re-prompts.
"""

from __future__ import annotations

import threading
from typing import List, Optional

import pygame

from ..webdav import DavAuthRequired, DavClient, DavError, Source
from .. import netscan


def start_fetch(app, system: dict, systems=None) -> None:
    """Entry point. Called by the system carousel's Y handler. `system`
    is the highlighted system (smart-jump target); `systems` is the
    whole device list, which the browser uses to map remote folders to
    local destinations."""
    saved = _load_sources(app)
    if saved:
        app.push_screen(SourcePickerScreen(app, system, saved, systems))
    else:
        app.push_screen(FindNewScreen(app, system, systems))


# ----------------------------------------------------------------------
# Persistence
# ----------------------------------------------------------------------

def _load_sources(app) -> List[Source]:
    out = []
    for d in app.config.get("webdav_sources", []):
        try:
            out.append(Source(url=d["url"], name=d.get("name", ""),
                              username=d.get("username", ""),
                              dialect=d.get("dialect", "")))
        except (KeyError, TypeError):
            continue
    return out


def remember_source(app, src: Source) -> None:
    entry = {"url": src.url, "name": src.name,
             "username": src.username, "dialect": src.dialect}
    lst = app.config.setdefault("webdav_sources", [])
    for i, d in enumerate(lst):
        if d.get("url") == src.url:
            lst[i] = entry
            break
    else:
        lst.insert(0, entry)
        del lst[8:]                      # keep the list sane
    app.save_settings()
    # session password cache
    if src.password:
        getattr(app, "_dav_passwords", None) or setattr(
            app, "_dav_passwords", {})
        app._dav_passwords[src.url] = src.password


# ----------------------------------------------------------------------
# Shared modal scaffolding
# ----------------------------------------------------------------------

class _MenuScreen:
    """A titled option list: d-pad + A, B backs out."""

    def __init__(self, app, title: str, footer: str = "A select   B back"):
        self.app = app
        self.title = title
        self.footer = footer
        self.items: List[str] = []
        self.selected = 0
        self.status = ""                 # transient line under the list

    def _activate(self, index: int) -> None:  # override
        pass

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type != pygame.KEYDOWN:
            return
        if event.key == pygame.K_UP:
            self.selected = max(0, self.selected - 1)
        elif event.key == pygame.K_DOWN:
            self.selected = min(max(0, len(self.items) - 1), self.selected + 1)
        elif event.key == pygame.K_RETURN:
            if self.items:
                self._activate(self.selected)
        elif event.key == pygame.K_ESCAPE:
            self.app.pop_screen()

    def draw(self, surface: pygame.Surface) -> None:
        below = self.app.screen_below(self)
        if below is not None:
            below.draw(surface)
        overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 190))
        surface.blit(overlay, (0, 0))

        theme = self.app.config["theme"]
        base = self.app.config["ui"]["font_size_base"]
        text_c = tuple(theme["text_color"])
        muted = tuple(theme["muted_color"])
        hi = tuple(theme["highlight_color"])

        box_w = min(surface.get_width() - 60, max(640, base * 30))
        box_h = min(surface.get_height() - 60, max(360, base * 15))
        box = pygame.Rect((surface.get_width() - box_w) // 2,
                          (surface.get_height() - box_h) // 2, box_w, box_h)
        pygame.draw.rect(surface, tuple(theme["panel_bg_color"]), box)
        pygame.draw.rect(surface, hi, box, width=2)

        font = self.app.fonts.get(base)
        title_font = self.app.fonts.get(int(base * 1.15))
        small = self.app.fonts.get(max(11, int(base * 0.72)))
        pad = max(18, int(base * 0.8))
        y = box.y + pad
        surface.blit(title_font.render(self.title, True, text_c),
                     (box.x + pad, y))
        y += title_font.get_linesize() + 10

        line_h = font.get_linesize() + 8
        visible = max(1, (box.h - (y - box.y) - pad * 2
                          - small.get_linesize()) // line_h)
        top = max(0, min(self.selected - visible // 2,
                         len(self.items) - visible))
        for i in range(top, min(len(self.items), top + visible)):
            row = pygame.Rect(box.x + pad, y, box.w - pad * 2, line_h - 2)
            if i == self.selected:
                pygame.draw.rect(surface, hi, row)
            label = font.render(self.items[i], True,
                                tuple(theme["panel_bg_color"])
                                if i == self.selected else text_c)
            surface.blit(label, (row.x + 8, row.y + 3))
            y += line_h

        if self.status:
            surface.blit(small.render(self.status, True, muted),
                         (box.x + pad, box.bottom - pad
                          - small.get_linesize() * 2))
        surface.blit(small.render(self.footer, True, muted),
                     (box.x + pad, box.bottom - pad - small.get_linesize()))


# ----------------------------------------------------------------------
# Screens
# ----------------------------------------------------------------------

class SourcePickerScreen(_MenuScreen):
    def __init__(self, app, system: dict, saved: List[Source],
                 systems=None):
        super().__init__(app, f"Fetch into {system['display']} - from where?")
        self.system = system
        self.systems = systems
        self.saved = saved
        self.items = [s.display() for s in saved] + ["Find New WebDAV Server"]

    def _activate(self, index: int) -> None:
        if index >= len(self.saved):
            self.app.push_screen(
                FindNewScreen(self.app, self.system, self.systems))
            return
        src = self.saved[index]
        pw_cache = getattr(self.app, "_dav_passwords", {})
        src.password = pw_cache.get(src.url, "")
        _connect_and_open(self.app, self.system, src, self, self.systems)


class FindNewScreen(_MenuScreen):
    def __init__(self, app, system: dict, systems=None):
        super().__init__(app, "Find New WebDAV Server")
        self.system = system
        self.systems = systems
        self.items = ["Scan the local network", "Enter an address"]

    def _activate(self, index: int) -> None:
        if index == 0:
            self.app.push_screen(
                ScanScreen(self.app, self.system, self.systems))
        else:
            _prompt_address(self.app, self.system, self, self.systems)


class ScanScreen(_MenuScreen):
    """Runs the subnet scan in a thread; morphs into the results list."""

    def __init__(self, app, system: dict, systems=None):
        super().__init__(app, "Scanning the local network...",
                         footer="B cancel")
        self.system = system
        self.systems = systems
        self.results: List[netscan.Found] = []
        self.done = False
        self._cancelled = False
        self._progress = (0, 1)
        threading.Thread(target=self._scan, daemon=True).start()

    def _scan(self) -> None:
        self.results = netscan.scan(
            progress=lambda n, t: setattr(self, "_progress", (n, t)),
            cancelled=lambda: self._cancelled)
        self.done = True
        if self.results:
            self.title = "Servers found - pick one"
            self.items = [f"{f.host}:{f.port}  ({f.dialect})"
                          for f in self.results] + ["Enter an address instead"]
            self.footer = "A select   B back"
        else:
            self.title = "No servers found on this network"
            self.items = ["Enter an address manually", "Back"]
            self.footer = "A select   B back"

    def _activate(self, index: int) -> None:
        if not self.done:
            return
        if self.results and index < len(self.results):
            f = self.results[index]
            _connect_and_open(self.app, self.system,
                              Source(url=f.url, dialect=f.dialect), self,
                              self.systems)
        elif self.items[index].startswith("Enter"):
            _prompt_address(self.app, self.system, self, self.systems)
        else:
            self.app.pop_screen()

    def handle_event(self, event: pygame.event.Event) -> None:
        if (event.type == pygame.KEYDOWN
                and event.key == pygame.K_ESCAPE and not self.done):
            self._cancelled = True
            self.app.pop_screen()
            return
        super().handle_event(event)

    def draw(self, surface: pygame.Surface) -> None:
        if not self.done:
            n, t = self._progress
            self.status = f"Probing addresses... {int(n * 100 / max(1, t))}%"
        elif not self.results:
            self.status = ("Scans can't see across guest WiFi or other "
                           "subnets - manual entry always works.")
        else:
            self.status = ""
        super().draw(surface)


# ----------------------------------------------------------------------
# Connect / auth plumbing
# ----------------------------------------------------------------------

def _prompt_address(app, system: dict, parent, systems=None) -> None:
    from .osk import OSKScreen

    def got(text: Optional[str]) -> None:
        if not text:
            return
        _connect_and_open(app, system, Source(url=text.strip()), parent,
                          systems)

    app.push_screen(OSKScreen(
        app, "Server address (e.g. 192.168.1.20:5005)", got,
        layout="keypad"))


def _connect_and_open(app, system: dict, src: Source, parent,
                      systems=None) -> None:
    """Probe in a thread, prompting for credentials on 401, then open
    the remote browser. `parent` shows status while connecting; the
    browser itself then shows "Opening connection..." until the first
    listing is on screen, so the state is readable end to end."""

    def attempt() -> None:
        parent.status = f"Opening connection to {src.url}..."
        try:
            client = DavClient(src)
            client.probe()
        except DavAuthRequired:
            parent.status = ""
            _prompt_credentials(app, system, src, parent, systems)
            return
        except DavError as exc:
            parent.status = str(exc)
            return
        parent.status = ""
        remember_source(app, src)
        from .remote_browser import RemoteBrowserScreen
        app.push_screen(RemoteBrowserScreen(app, system, client, systems))

    threading.Thread(target=attempt, daemon=True).start()


def _prompt_credentials(app, system: dict, src: Source, parent,
                        systems=None) -> None:
    from .osk import OSKScreen

    def got_user(user: Optional[str]) -> None:
        if user is None:
            return
        src.username = user.strip()

        def got_pass(pw: Optional[str]) -> None:
            if pw is None:
                return
            src.password = pw
            _connect_and_open(app, system, src, parent, systems)

        app.push_screen(OSKScreen(
            app, f"Password for {src.username or 'this server'}",
            got_pass, mask=True, layout="full"))

    app.push_screen(OSKScreen(
        app, f"Username for {src.url} (blank if none)", got_user,
        initial=src.username, layout="full"))
