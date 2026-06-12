"""
Application shell. Owns the pygame surface, the screen stack, the config,
and the shared resources (fonts, image cache).

Screen lifecycle:
    - app.push_screen(s)  -> s becomes the active screen
    - app.pop_screen()    -> previous screen resumes
    - The bottom screen never pops; when it would, the app quits.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import List, Optional

import pygame

from .firmware import (
    detect_firmware_name,
    detect_roms_dir,
    discover_systems,
    load_systems_db,
)
from .render import FontCache, ImageCache
from .theme import detect_active_theme, find_logo_fallback_dirs, detect_artwork_region


class App:
    def __init__(self, port_dir: Path):
        from . import __version__, __build__
        print(f"[app] Pocket Curator v{__version__} build {__build__}")
        print(f"[app] port_dir={port_dir}")

        # Startup phase timing. Cheap, always on: when someone reports a
        # slow splash, the log should answer "slow doing WHAT" without a
        # special build.
        import time as _time
        self._t0 = _time.monotonic()
        self._t_last = self._t0
        def _mark(label: str) -> None:
            now = _time.monotonic()
            print(f"[timing] {label}: +{now - self._t_last:.2f}s "
                  f"(total {now - self._t0:.2f}s)")
            self._t_last = now
        self._mark = _mark

        self.port_dir = port_dir
        self.package_dir = port_dir / "curator"
        self.assets_dir = port_dir / "assets"
        self.settings_path = port_dir / "settings.json"

        self.config = self._load_settings()
        self.systems_db = load_systems_db(self.package_dir)
        self._mark("settings + systems db loaded")

        self.firmware_name = detect_firmware_name()
        roms_dir = detect_roms_dir(self.config.get("roms_dir_override"))
        self.roms_dir = roms_dir

        # ---- pygame init -----------------------------------------------
        os.environ.setdefault("SDL_VIDEO_CENTERED", "1")
        # Note: deliberately NOT calling pygame.init() (the umbrella).
        # The umbrella inits every subsystem including mixer, which loads
        # ~6 MB of audio codec libraries (libSDL2_mixer, libFLAC,
        # libfluidsynth, libmpg123, libogg, libopus*, libvorbis*,
        # libsndfile, libasound, libpulse*) that we never use. Init only
        # the subsystems our app actually exercises.
        pygame.display.init()
        pygame.font.init()

        # Input on kmsdrm: with no compositor to feed us events, SDL must
        # read the kernel input devices (including gptokeyb's uinput
        # keyboard) through its own evdev backend - which only starts
        # scanning once the joystick subsystem is initialized. On
        # wayland/x11 the compositor delivers keys without this, but
        # initializing the joystick subsystem there is harmless. We do
        # NOT call pygame.init() (the umbrella), which would also pull in
        # the heavy audio mixer we never use.
        driver = (pygame.display.get_driver() or "").lower()
        if driver not in ("wayland", "x11"):
            try:
                pygame.joystick.init()
                for _ji in range(pygame.joystick.get_count()):
                    pygame.joystick.Joystick(_ji).init()
                print(f"[app] {driver}: joystick subsystem up "
                      f"({pygame.joystick.get_count()} device(s)) for evdev "
                      f"key input")
            except Exception as _exc:  # noqa: BLE001
                print(f"[app] joystick init skipped: {_exc}")

        info = pygame.display.Info()
        disp_w = info.current_w
        disp_h = info.current_h

        # Note on flags: SDL2 2.28's Wayland backend has known crashes when
        # you pass FULLSCREEN. Borderless at full display size looks the
        # same and goes through a more stable code path. The compositor
        # will still draw us full-screen because pm_platform_helper sends
        # the swaymsg to fullscreen our window after it appears.
        if os.environ.get("POCKETCURATOR_FULLSCREEN", "1") == "1":
            flags = pygame.NOFRAME
        else:
            flags = 0
        self._display = pygame.display.set_mode((disp_w, disp_h), flags)

        # Display rotation. Some panels (notably the Anbernic RG552) are
        # physically mounted in landscape but exposed by KMSDRM as a
        # portrait framebuffer (1152x1920); drawing straight into that
        # paints the UI sideways. We detect the need and draw into a
        # LOGICAL landscape surface, then rotate-blit it onto the real
        # display each frame, so no drawing code anywhere has to know.
        #
        # Resolution order: explicit PC_ROTATE env (0/90/180/270 from the
        # launcher) wins; otherwise auto-rotate a portrait panel 90deg so
        # the wider dimension becomes the UI width.
        rot_env = os.environ.get("PC_ROTATE", "").strip()
        if rot_env in ("0", "90", "180", "270"):
            self._rotation = int(rot_env)
        elif disp_h > disp_w:
            # Portrait framebuffer on a device meant to be held in
            # landscape -> rotate 90 clockwise for display.
            self._rotation = 90
        else:
            self._rotation = 0

        if self._rotation in (90, 270):
            self.screen_w, self.screen_h = disp_h, disp_w
            self.surface = pygame.Surface((self.screen_w, self.screen_h))
        elif self._rotation == 180:
            self.screen_w, self.screen_h = disp_w, disp_h
            self.surface = pygame.Surface((self.screen_w, self.screen_h))
        else:
            self.screen_w, self.screen_h = disp_w, disp_h
            self.surface = self._display     # no rotation: draw direct
        if self._rotation:
            print(f"[app] display {disp_w}x{disp_h} rotated {self._rotation}deg "
                  f"-> logical {self.screen_w}x{self.screen_h}")
        self._mark("display ready")
        pygame.display.set_caption("Pocket Curator")
        pygame.mouse.set_visible(False)
        self.clock = pygame.time.Clock()

        # Scale UI sizes for the actual screen we got. The bundled
        # font_size_base in settings.json is tuned for ~480px tall
        # screens. On a 1152px tall RG552 a fixed value looks tiny -
        # it's both unreadable and makes the image panel feel small
        # because everything around it is taking proportionally more
        # room. We auto-scale up from a 480px baseline; the user can
        # still override in settings.json with a hard value.
        base_from_settings = self.config["ui"].get("font_size_base", 18)
        if not self.config["ui"].get("font_size_base_locked", False):
            # Linear scale from 480px reference. 480 -> base, 720 -> ~1.5x,
            # 1152 -> ~2.4x. Capped at 2.8x to avoid silly results on
            # very large desktop test screens.
            scale = min(2.8, max(1.0, self.screen_h / 480.0))
            self.config["ui"]["font_size_base"] = max(14,
                int(round(base_from_settings * scale)))
            print(f"[app] screen {self.screen_w}x{self.screen_h}, "
                  f"font_size_base {base_from_settings} -> "
                  f"{self.config['ui']['font_size_base']} (scale x{scale:.2f})")

        # ---- shared resources ------------------------------------------
        fonts_dir = self.assets_dir / "fonts"
        regular = fonts_dir / "Oxanium-Medium.ttf"
        bold = fonts_dir / "Oxanium-Bold.ttf"
        self.fonts = FontCache(regular_path=regular, bold_path=bold)
        self.images = ImageCache()

        # ---- early splash: show "Loading..." immediately ----------------
        # Discovery, theme detection, and screen-stack setup can take a few
        # seconds on slow SD cards. Without this, the user stares at black
        # for that whole time and can't tell if the app is working. Render
        # the bundled splash + a one-line caption as soon as we have a
        # display and a font, then let normal init proceed.
        self._draw_startup_splash()

        # ---- ES theme detection (for system carousel logos) ------------
        try:
            self.theme_dir = detect_active_theme()
            if self.theme_dir:
                print(f"[app] using ES theme at {self.theme_dir}")
            else:
                print("[app] no ES theme found - will use text labels")
        except Exception as exc:  # noqa - never crash on theme detection
            print(f"[app] theme detection failed: {exc}")
            self.theme_dir = None

        # Themes to borrow logos from when the active theme has none for a
        # system (firmware/system-theme preferred). Better a logo than text.
        try:
            self.fallback_theme_dirs = find_logo_fallback_dirs(self.theme_dir)
            if self.fallback_theme_dirs:
                print(f"[app] logo fallback (system-theme): "
                      f"{self.fallback_theme_dirs[0]}")
            else:
                print("[app] no system-theme found for logo fallback")
        except Exception as exc:  # noqa - never crash on theme detection
            print(f"[app] logo fallback discovery failed: {exc}")
            self.fallback_theme_dirs = []

        # Theme region / subset selections, for themes that ship region
        # logo variants (e.g. US TurboGrafx-16 vs PC Engine). Detected once.
        self._mark("theme resolved")
        try:
            self.artwork_region, self.theme_subsets = detect_artwork_region()
            print(f"[app] artwork region: {self.artwork_region or 'unset'}")
        except Exception as exc:  # noqa - never crash on detection
            print(f"[app] artwork region detection failed: {exc}")
            self.artwork_region, self.theme_subsets = None, {}

        # ---- screen stack ----------------------------------------------
        self._screens: List = []
        self._quit = False
        # Set True once a real (non-dry-run) deletion happens. main.py
        # reads this after run() to decide whether to ask the launcher
        # to refresh EmulationStation so its in-RAM gamelist refreshes.
        self.deletions_occurred = False

        # ---- input tracking --------------------------------------------
        # Set of currently-held pygame key codes. Populated by run() as
        # KEYDOWN/KEYUP events flow through; queried by screens via
        # ``app.is_repeat()`` to distinguish a deliberate tap from an
        # auto-repeat triggered by holding the button.
        self._held_keys: set = set()
        self._is_repeat_event: bool = False
        # Set of keys whose KEYDOWN events should be swallowed (ignored)
        # until the user releases them. Populated on screen push/pop to
        # prevent the button that triggered the transition from auto-
        # repeating into the newly-active screen.
        self._swallowed_keys: set = set()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def push_screen(self, screen) -> None:
        self._screens.append(screen)
        # Snapshot currently-held keys so the new screen ignores their
        # auto-repeats until they're physically released. Otherwise
        # holding A to enter a system causes pygame's set_repeat to
        # fire KEYDOWN events at the brand-new screen, which sees them
        # as "the user is mass-marking from the carousel-entry press"
        # and toggles 10+ games before they ever see the screen.
        self._swallowed_keys.update(self._held_keys)

    def pop_screen(self) -> None:
        if not self._screens:
            return
        self._screens.pop()
        # Same defense in the other direction: holding B to back out
        # shouldn't immediately re-back-out from the underlying screen.
        self._swallowed_keys.update(self._held_keys)
        if not self._screens:
            self._quit = True

    def screen_below(self, screen):
        """Return the screen immediately below ``screen`` in the stack,
        or ``None`` if it's the bottom. Used by modals to render the
        underlying view behind themselves."""
        try:
            idx = self._screens.index(screen)
        except ValueError:
            return None
        if idx == 0:
            return None
        return self._screens[idx - 1]

    def request_quit(self) -> None:
        self._quit = True

    # ------------------------------------------------------------------
    # Bootstrap
    # ------------------------------------------------------------------

    def start(self) -> None:
        if self.roms_dir is None:
            from .ui.exit_prompt import ExitPromptScreen
            print("[app] No ROM directory found. Exiting after a confirmation.")
            # Use the exit screen but adjust message - or build a simple one inline
            self._screens.append(_NoRomsScreen(self))
            return

        # Paint a splash before the (potentially multi-second) ROM walk so
        # the user sees something other than a black screen and doesn't
        # think the app has hung.
        self._show_splash("Scanning ROM folders, please wait...")
        self._mark("init complete, ROM scan starting")

        systems = discover_systems(self.roms_dir, self.systems_db)
        self.all_systems = systems
        from .firmware import all_fetch_targets
        # Destinations for Fetch include empty-but-present roms folders
        # (e.g. atarijaguar with no ROMs yet), which discovery omits.
        self.fetch_targets = all_fetch_targets() or systems
        self._mark(f"ROM scan done ({len(systems)} systems, "
                   f"{sum(s.get('rom_count', 0) for s in systems)} ROMs)")
        from .ui.system_browser import SystemBrowserScreen
        self._screens.append(SystemBrowserScreen(self, systems))
        self._mark("system browser built - startup finished")

    def _draw_startup_splash(self) -> None:
        """Called once from __init__, the moment we have a display and a
        font. Just renders the splash so the user sees something while
        the rest of init (theme detection, settings loading) runs."""
        self._render_splash("Initializing...")

    def _show_splash(self, message: str) -> None:
        """Paint a heavyweight loading screen with the bundled splash
        image and the given message. Used only by the early init path
        (start(), __init__) where no screen has been pushed yet.

        For in-app status messages during gameplay, use _show_status
        instead - that won't clobber the underlying screen with the
        splash image."""
        self._render_splash(message)

    def _show_status(self, message: str) -> None:
        """Lightweight status overlay drawn over whatever's currently on
        screen. A short pill at the bottom of the screen with the message
        text; no full-screen fill, no splash image. Use this when you
        want feedback but the user already has something useful on
        screen (carousel, game list, etc.)."""
        cfg = self.config
        theme = cfg["theme"]
        ui = cfg["ui"]
        try:
            font = self.fonts.get(ui["font_size_base"])
            text = font.render(message, True,
                               tuple(theme["highlight_text_color"]))
            pad_x = max(16, font.get_height() // 2)
            pad_y = max(8, font.get_height() // 4)
            pill_w = text.get_width() + 2 * pad_x
            pill_h = text.get_height() + 2 * pad_y
            pill_x = (self.screen_w - pill_w) // 2
            pill_y = self.screen_h - pill_h - max(24, font.get_height())

            # Semi-transparent dark backdrop so the pill reads on top of
            # any underlying content.
            backdrop = pygame.Surface((pill_w, pill_h), pygame.SRCALPHA)
            backdrop.fill((0, 0, 0, 220))
            self.surface.blit(backdrop, (pill_x, pill_y))
            pygame.draw.rect(self.surface,
                             tuple(theme["highlight_color"]),
                             (pill_x, pill_y, pill_w, pill_h), width=2)
            self.surface.blit(text, (pill_x + pad_x, pill_y + pad_y))

            self._present()
            pygame.event.pump()
        except Exception as exc:
            print(f"[app] status overlay failed: {exc}")

    def _render_splash(self, message: str) -> None:
        cfg = self.config
        theme = cfg["theme"]
        ui = cfg["ui"]
        try:
            self.surface.fill(tuple(theme["background_color"]))

            # ---- splash image (centered, aspect-preserved) -------------
            # Cached after first load so repeated splash calls are cheap.
            splash_path = self.assets_dir / "splash.jpg"
            if splash_path.is_file() and not hasattr(self, "_splash_surface_cache"):
                try:
                    raw = pygame.image.load(str(splash_path)).convert()
                    iw, ih = raw.get_size()
                    # Leave the bottom ~15% for the status message and the
                    # build-number footer.
                    avail_w = int(self.screen_w * 0.9)
                    avail_h = int(self.screen_h * 0.75)
                    scale = min(avail_w / iw, avail_h / ih)
                    new_size = (max(1, int(iw * scale)),
                                max(1, int(ih * scale)))
                    self._splash_surface_cache = pygame.transform.smoothscale(
                        raw, new_size)
                except Exception as exc:
                    print(f"[app] splash image load failed: {exc}")
                    self._splash_surface_cache = None
            elif not splash_path.is_file():
                self._splash_surface_cache = None

            img = getattr(self, "_splash_surface_cache", None)

            msg_font = self.fonts.get(ui["font_size_base"])
            ver_font = self.fonts.get(max(10, int(ui["font_size_base"] * 0.6)))

            from . import __version__, __build__

            if img is not None:
                ix = (self.screen_w - img.get_width()) // 2
                # Position image so its centre sits a bit above geometric
                # centre - leaves room for the message text below without
                # crowding the bottom footer.
                iy = max(0, (self.screen_h - img.get_height()) // 2 - 30)
                self.surface.blit(img, (ix, iy))
                msg_baseline = iy + img.get_height() + 16
            else:
                # Text-only fallback when no image is available
                title_font = self.fonts.get(
                    int(ui["font_size_base"] * 1.6), bold=True)
                title = title_font.render("Pocket Curator", True,
                                          tuple(theme["text_color"]))
                self.surface.blit(
                    title,
                    ((self.screen_w - title.get_width()) // 2,
                     self.screen_h // 2 - title.get_height() - 8))
                msg_baseline = self.screen_h // 2 + 12

            msg = msg_font.render(message, True,
                                  tuple(theme["accent_color"]))
            self.surface.blit(
                msg,
                ((self.screen_w - msg.get_width()) // 2, msg_baseline))

            ver = ver_font.render(f"v{__version__}  build {__build__}",
                                  True, tuple(theme["muted_color"]))
            self.surface.blit(
                ver,
                ((self.screen_w - ver.get_width()) // 2,
                 self.screen_h - ver.get_height() - 12))

            self._present()
            # Service Wayland/X events so the compositor actually presents the
            # frame before we block on the long ROM walk. Without this the
            # frame can sit unrendered until the loop starts.
            pygame.event.pump()
        except Exception as exc:
            # Splash is a nicety, not a hard requirement.
            print(f"[app] splash render failed: {exc}")

    def _present(self) -> None:
        """Put the logical surface on the real display, rotating if the
        panel needs it, then flip. When no rotation is in effect the
        logical surface IS the display, so this is just a flip."""
        if self._rotation and self.surface is not self._display:
            if self._rotation == 90:
                rotated = pygame.transform.rotate(self.surface, -90)
            elif self._rotation == 270:
                rotated = pygame.transform.rotate(self.surface, 90)
            else:  # 180
                rotated = pygame.transform.rotate(self.surface, 180)
            self._display.blit(rotated, (0, 0))
        pygame.display.flip()  # PRESENT_FLIP

    def run(self) -> int:
        self.start()

        fps_cap = max(15, int(self.config["ui"].get("fps_cap", 30)))

        # Enable key repeat so holding a direction keeps moving the
        # selection without re-pressing. 400ms initial delay, 80ms per
        # repeat is the standard "menu nav" feel. Affects ALL keys; we
        # use the _held_keys set below to distinguish initial taps from
        # repeated events when handlers care about the difference (e.g.
        # to suppress wrap-around when scrolling fast).
        pygame.key.set_repeat(400, 80)

        while not self._quit and self._screens:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self._quit = True
                    continue
                if event.type == pygame.KEYDOWN:
                    # If this key is "swallowed" (was held when a screen
                    # transition happened), drop the event entirely until
                    # the user releases the key. This stops auto-repeats
                    # of e.g. the A button held to enter a system from
                    # firing inside the new screen.
                    if event.key in self._swallowed_keys:
                        continue
                    # If we already think this key is held, this KEYDOWN
                    # is an auto-repeat from set_repeat. Mark it so the
                    # screen handler can branch on is_repeat() if it
                    # wants different behaviour for repeats.
                    self._is_repeat_event = event.key in self._held_keys
                    self._held_keys.add(event.key)
                elif event.type == pygame.KEYUP:
                    self._is_repeat_event = False
                    self._held_keys.discard(event.key)
                    # Releasing a swallowed key un-swallows it. Next
                    # deliberate press by the user works normally.
                    self._swallowed_keys.discard(event.key)
                else:
                    self._is_repeat_event = False

                # Always forward to the top of the stack
                top = self._screens[-1]
                top.handle_event(event)
                if self._quit:
                    break

            if self._quit:
                break

            top = self._screens[-1]
            top.draw(self.surface)
            self._present()
            self.clock.tick(fps_cap)

        pygame.quit()
        return 0

    def is_repeat(self, key=None) -> bool:
        """True if the current event being handled is an auto-repeat of a
        held key. Pass ``key`` to require a specific key, or omit to ask
        about the current event regardless.

        Handlers use this to skip wrap-around when a direction is being
        held (so a fast d-pad scroll stops at the end of the list rather
        than looping back to the start)."""
        if not self._is_repeat_event:
            return False
        if key is None:
            return True
        return key in self._held_keys

    # ------------------------------------------------------------------
    # Settings IO
    # ------------------------------------------------------------------

    def _load_settings(self) -> dict:
        defaults = self._defaults()
        try:
            raw = json.loads(self.settings_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"[app] settings.json unreadable ({exc}); using defaults")
            return defaults

        # Shallow merge so missing keys fall back to defaults.
        merged = defaults
        for top_key, top_val in raw.items():
            if isinstance(top_val, dict) and isinstance(merged.get(top_key), dict):
                merged[top_key].update(top_val)
            else:
                merged[top_key] = top_val

        # One-time migration: the screenshot/media split was consolidated
        # into a single ``include_scraped_media`` toggle. Honor whatever
        # state the old keys had (either ON enables the new key), then
        # drop them so they don't sit stale in settings.json.
        beh = merged.setdefault("behavior", {})
        if "include_scraped_media" not in beh:
            beh["include_scraped_media"] = bool(
                beh.pop("include_screenshots_folder", True)
                or beh.pop("include_media_folder", True))
        else:
            beh.pop("include_screenshots_folder", None)
            beh.pop("include_media_folder", None)
        return merged

    def save_settings(self) -> None:
        try:
            self.settings_path.write_text(
                json.dumps(self.config, indent=4), encoding="utf-8")
            print("[app] settings saved")
        except OSError as exc:
            print(f"[app] could not save settings: {exc}")

    @staticmethod
    def _defaults() -> dict:
        return {
            "theme": {
                "background_color": [18, 18, 18],          # #121212
                "list_bg_color": [16, 18, 22],             # #101216
                "panel_bg_color": [18, 18, 18],            # #121212
                "frame_color": [22, 22, 22],               # #161616
                "text_color": [230, 230, 230],
                "muted_color": [136, 136, 136],            # #888888
                "highlight_color": [255, 85, 85],          # #FF5555 (Rocknix red)
                "highlight_text_color": [255, 255, 255],
                "flagged_color": [110, 110, 110],
                "legend_bg_color": [10, 10, 10],           # #0A0A0A
                "legend_text_color": [200, 200, 200],
                "accent_color": [255, 85, 85],             # #FF5555
                "blue_accent_color": [78, 151, 209],       # #4E97D1
            },
            "ui": {
                "list_width_pct": 0.40,
                "font_size_base": 22,
                "marquee_delay_ms": 600,
                "marquee_speed_px_per_sec": 60,
                "description_autoscroll": False,
                "description_autoscroll_speed_px_per_sec": 18,
                "image_load_debounce_ms": 120,
                "fps_cap": 30,
            },
            "behavior": {
                "deletion_dry_run": False,
                "confirm_before_delete": True,
                "include_scraped_media": True,
            },
            "ratings_display": "stars",
            "region_display": "text",
            "roms_dir_override": None,
            "theme_dir_override": None,
        }


# --- internal helper screen for the no-ROMs case ---------------------------

class _NoRomsScreen:
    def __init__(self, app):
        self.app = app

    def handle_event(self, event):
        if event.type == pygame.KEYDOWN:
            self.app.request_quit()

    def draw(self, surface):
        theme = self.app.config["theme"]
        ui = self.app.config["ui"]
        surface.fill(tuple(theme["background_color"]))
        title_font = self.app.fonts.get(int(ui["font_size_base"] * 1.4))
        body_font = self.app.fonts.get(ui["font_size_base"])
        small_font = self.app.fonts.get(max(11, int(ui["font_size_base"] * 0.8)))

        title = title_font.render("No ROM directory found",
                                  True, tuple(theme["text_color"]))
        surface.blit(title,
                     ((surface.get_width() - title.get_width()) // 2,
                      surface.get_height() // 3))

        lines = [
            "Pocket Curator checked the standard paths:",
            "  /userdata/roms   /storage/roms   /roms   /roms2",
            "  /mnt/mmc/MUOS/info/roms   /mnt/mmc/ROMS",
            "",
            "None of them exist on this device. If your ROMs are",
            "elsewhere, set 'roms_dir_override' in settings.json.",
        ]
        y = surface.get_height() // 2
        for line in lines:
            surf = small_font.render(line, True, tuple(theme["muted_color"]))
            surface.blit(surf,
                         ((surface.get_width() - surf.get_width()) // 2, y))
            y += surf.get_height() + 4

        hint = body_font.render("Press any button to exit", True,
                                tuple(theme["legend_text_color"]))
        surface.blit(hint,
                     ((surface.get_width() - hint.get_width()) // 2,
                      surface.get_height() - 60))
