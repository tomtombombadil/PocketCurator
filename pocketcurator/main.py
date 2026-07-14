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
    # We do NOT write it here, and we do NOT reload here. Proven on-device
    # (RG40xxV, 2026-07-13):
    #
    #   ES owns every <game> node it has parsed. Our port IS a game in
    #   Ports, so when the port exits ES rewrites that node from its
    #   in-RAM model (bumping playcount/lastplayed) - flattening anything
    #   we wrote to disk while it was suspended. Calling
    #   /reloadgames from in here LOOKS like it works (the socket opens,
    #   so the old code returned True) but ES is suspended behind us and
    #   never applies it before that flush. Result: the app wrote the
    #   correct description on all 80 launches and not one of them stuck -
    #   the file still held a sentinel string a probe script left behind
    #   years ago, because THAT one was written while ES was idle.
    #
    #   Writing while ES sits idle at its menu, then asking it to reload,
    #   IS adopted and IS durable (confirmed by hand on the device).
    #
    # So: just tell the launcher that our entry needs writing. It runs
    # tools/write_ports_metadata.py in a detached process AFTER ES has
    # come back and done its flush - the one moment the write survives.
    needs_metadata = False
    try:
        from curator.ports_gamelist import entry_needs_metadata
        needs_metadata = entry_needs_metadata(here.parent)
    except Exception:
        pass

    # Tell the launcher what to do on exit:
    #   metadata / both -> write our entry once ES is idle again, then
    #       reload. 'both' when there are also ROM changes to surface.
    #   deletions -> ROM changes only. A plain reload handles those: ES
    #       re-scans for added/removed games, which is disk->RAM and
    #       cannot be clobbered. (This is why fetch and delete have always
    #       worked while our own metadata never did - different code path
    #       inside ES entirely.)
    try:
        changed = (bool(getattr(app, "deletions_occurred", False))
                   or bool(getattr(app, "fetches_occurred", False)))
        reason = ""
        if needs_metadata:
            reason = "both" if changed else "metadata"
        elif changed:
            reason = "deletions"
        if reason:
            (here / ".es_refresh_needed").write_text(reason, encoding="utf-8")
    except Exception:
        pass

    return rc


if __name__ == "__main__":
    raise SystemExit(main())
