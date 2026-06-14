"""
Pocket Curator entry point.

The launcher script already prepends the port directory and the
arch-specific libs folder to PYTHONPATH, so all we have to do here is
import the package and run it.
"""

from __future__ import annotations

import sys
from pathlib import Path


def _ensure_path():
    """
    Defensive sys.path setup. Even though the launcher sets PYTHONPATH,
    running main.py directly from a development machine (or from a
    different working directory) should still work.
    """
    here = Path(__file__).resolve().parent
    # The "curator" package lives next to this file
    if str(here) not in sys.path:
        sys.path.insert(0, str(here))
    # The PortMaster install puts main.py at /roms/ports/pocketcurator/main.py
    port_dir = here.parent
    if str(port_dir) not in sys.path:
        sys.path.insert(0, str(port_dir))


def main() -> int:
    _ensure_path()

    here = Path(__file__).resolve().parent

    from curator.app import App
    app = App(port_dir=here)
    rc = app.run()

    # --- Pocket Curator's own metadata (description, artwork, ...) ---
    #
    # PROVEN mechanism (do not "improve" this into a deferred post-exit
    # write again): write our metadata to disk HERE, while we are still
    # running, then immediately tell the running EmulationStation to
    # reload gamelists from disk. ES treats our port as a "game"; when our
    # window closes it flushes the ports gamelist from its in-RAM model
    # (bumping playcount/lastplayed), which would clobber a write that
    # only exists on disk. By reloading NOW, ES pulls our metadata into
    # its RAM first, so that exit-time flush writes our metadata BACK
    # instead of overwriting it. A post-exit write/reload (the launcher or
    # a deferred script) runs AFTER that flush and is too late - that was
    # the regression that made the description stop updating.
    wrote_metadata = False        # did we write our metadata to disk?
    metadata_reloaded = False      # did the running ES adopt it (API)?
    try:
        from curator.ports_gamelist import entry_needs_metadata, ensure_entry
        if entry_needs_metadata(here.parent):
            ensure_entry(ports_dir=here.parent)
            wrote_metadata = True
            # The in-app reload is what makes the write stick (see above).
            # API firmwares (Batocera/ROCKNIX/Knulli) -> True, done.
            # ArkOS-family (dArkOS) has no API -> False, so the launcher's
            # on-exit ArkOS ES-restart path must register it instead.
            metadata_reloaded = _reload_running_es()
    except Exception:
        pass

    # Tell the launcher what to do on exit:
    #   metadata / both -> we wrote our metadata but couldn't reload it
    #       in-app (no API, i.e. dArkOS). The launcher's metadata path
    #       does a stop -> write-while-ES-is-DOWN -> start. Writing while
    #       ES is stopped is the ONLY thing that sticks on dArkOS: at idle
    #       the write survives, but ES's game-exit flush (RAM -> disk)
    #       clobbers a write made while ES is up. Proven on-device with
    #       the down-window probe. 'both' when there are also ROM changes.
    #   deletions -> only ROM changes to surface (our metadata is already
    #       safe in ES's RAM via the in-app reload, or nothing to write).
    try:
        changed = (bool(getattr(app, "deletions_occurred", False))
                   or bool(getattr(app, "fetches_occurred", False)))
        reason = ""
        if wrote_metadata and not metadata_reloaded:
            # Down-window rewrite needed (dArkOS). 'both' also refreshes
            # for this session's deletions/fetches in the same restart.
            reason = "both" if changed else "metadata"
        elif changed:
            reason = "deletions"
        if reason:
            (here / ".es_refresh_needed").write_text(reason, encoding="utf-8")
    except Exception:
        pass

    return rc


def _reload_running_es(timeout: float = 8.0) -> bool:
    """Ask the running EmulationStation to reload gamelists from disk
    (no restart). Best-effort; returns True on success. This is the local
    ES HTTP API that Batocera/ROCKNIX/Knulli expose (the same one
    PortMaster uses). Firmwares without it (e.g. dArkOS) simply get False
    and fall back to the launcher's on-exit refresh."""
    import urllib.request
    try:
        with urllib.request.urlopen(
                "http://localhost:1234/reloadgames", timeout=timeout):
            return True
    except Exception:
        return False


if __name__ == "__main__":
    raise SystemExit(main())
