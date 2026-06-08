"""
Display preflight - runs in its own Python process before main.py so a
segfault here doesn't take down the launcher.

Walks pygame display init in small steps and prints what made it through.
The crash (if any) points us to the offending call.

Designed to be invoked with `python3 -u` so output is line-buffered and a
segfault doesn't eat the last few prints.
"""

from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path


def _say(msg: str) -> None:
    """Print and flush. Belt-and-braces in case -u was forgotten."""
    print(msg, flush=True)


def _env(name: str) -> str:
    return os.environ.get(name) or "(unset)"


def _probe_xdg_dir() -> None:
    rd = os.environ.get("XDG_RUNTIME_DIR")
    if not rd:
        _say("  XDG dir status  : XDG_RUNTIME_DIR is unset")
        return
    if not os.path.isdir(rd):
        _say(f"  XDG dir status  : {rd} does not exist")
        return
    try:
        st = os.stat(rd)
        owner_ok = st.st_uid == os.getuid()
        mode_ok = (st.st_mode & 0o077) == 0
        _say(f"  XDG dir status  : exists, owner_ok={owner_ok}, "
             f"mode_ok={mode_ok} (mode={oct(st.st_mode & 0o777)})")
    except OSError as exc:
        _say(f"  XDG dir stat    : FAILED {exc}")


def _probe_wayland_sockets() -> None:
    """Find every Wayland socket we can. Useful when WAYLAND_DISPLAY is unset
    or set to a value pointing nowhere."""
    candidates = []
    rd = os.environ.get("XDG_RUNTIME_DIR")
    if rd:
        candidates.append(Path(rd))
    uid = os.getuid()
    candidates.extend(Path(p) for p in (
        f"/var/run/user/{uid}",
        f"/run/user/{uid}",
        f"/tmp/runtime-{uid}",
        "/var/run",
        "/run",
    ))

    found = []
    seen = set()
    for d in candidates:
        if str(d) in seen or not d.is_dir():
            continue
        seen.add(str(d))
        try:
            for entry in d.iterdir():
                if entry.name.startswith("wayland-") and not entry.name.endswith(".lock"):
                    found.append(entry)
        except OSError:
            pass

    if found:
        _say(f"  Wayland sockets : {len(found)} found")
        for s in found:
            _say(f"      {s}")
    else:
        _say("  Wayland sockets : none found in standard locations")


def _step(label: str, fn) -> bool:
    """Run fn, print OK or the exception. Returns True on success."""
    try:
        result = fn()
        if result is None:
            _say(f"  {label}: OK")
        else:
            _say(f"  {label}: OK ({result})")
        return True
    except Exception as exc:
        _say(f"  {label}: FAILED {type(exc).__name__}: {exc}")
        # Short traceback only - full one is noise for our purposes
        tb = traceback.format_exc().splitlines()
        if len(tb) > 4:
            tb = tb[:2] + ["    ..."] + tb[-2:]
        for line in tb:
            _say(f"    {line}")
        return False


def main() -> int:
    _say("---- Pocket Curator display preflight ----")
    _say(f"  PYTHON          : {sys.version.split()[0]}")
    _say(f"  SDL_VIDEODRIVER : {_env('SDL_VIDEODRIVER')}")
    _say(f"  WAYLAND_DISPLAY : {_env('WAYLAND_DISPLAY')}")
    _say(f"  XDG_RUNTIME_DIR : {_env('XDG_RUNTIME_DIR')}")
    _say(f"  DISPLAY         : {_env('DISPLAY')}")
    _say(f"  HOME            : {_env('HOME')}")
    _say(f"  USER            : {_env('USER')}")
    _say(f"  uid/gid         : {os.getuid()}/{os.getgid()}")
    _probe_xdg_dir()
    _probe_wayland_sockets()

    # pygame import is essentially free; segfaults are basically impossible here
    if not _step("pygame import", lambda: __import__("pygame").version.ver):
        return 1
    import pygame  # noqa - already imported, but pylint wants the symbol

    # Note: we don't call pygame.init() (the umbrella) anymore. It loads
    # the mixer subsystem which pulls in ~6 MB of audio codec libs we
    # never use. Test the subsystems we actually need individually.

    # display.init is the most fragile step. Wrap it carefully.
    if not _step("display.init()",
                 lambda: pygame.display.init() or pygame.display.get_driver()):
        return 3

    if not _step("display.Info()",
                 lambda: (lambda i: f"{i.current_w}x{i.current_h}, bpp={i.bitsize}")
                         (pygame.display.Info())):
        return 4

    # set_mode is where Wayland's path tends to crash. Try something small
    # and non-fullscreen first so we isolate a fundamentally broken driver.
    if not _step("set_mode(320x240, no flags)",
                 lambda: pygame.display.set_mode((320, 240)).get_size()):
        return 5

    # Now test the SAME path the real app uses: full display resolution
    # with the NOFRAME flag. On some GPUs (e.g. RK3566 Mali-G52) the crash
    # only appears here, when a real full-size surface is created and the
    # GPU blob initializes. If this step is skipped, the probe can wrongly
    # bless a driver that the app then dies on.
    info = pygame.display.Info()
    w, h = info.current_w, info.current_h
    if w <= 0 or h <= 0:
        w, h = 640, 480
    if not _step(f"set_mode({w}x{h}, NOFRAME)",
                 lambda: pygame.display.set_mode((w, h), pygame.NOFRAME).get_size()):
        return 6

    _say("---- preflight passed ----")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
