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


def _check_stale_bytecode(here: Path) -> None:
    """Catch python running OLD code against NEW source files.

    The launcher reads __version__ straight out of curator/__init__.py on
    disk and passes it in. We compare it against the version we actually
    IMPORTED. They can only differ if python loaded stale .pyc files from
    __pycache__ - new sources, old behaviour.

    This is not hypothetical: a Batocera device ran launcher v1.0.34 on
    top of app v1.0.18 for exactly this reason. The app kept reporting the
    old version, so it kept offering the same update, applying it, and
    "succeeding" - forever. Nothing in the code noticed, because nothing
    was comparing the two.

    So: notice, say so loudly, and fix it - delete the stale bytecode so
    the next launch compiles the real sources. Self-healing beats a
    diagnostic nobody reads.
    """
    import os
    import shutil
    from curator import __version__ as imported

    on_disk = os.environ.get("PC_DISK_VERSION", "").strip()
    if not on_disk or on_disk == imported:
        return

    print(f"[app] *** STALE BYTECODE: disk has v{on_disk} but python "
          f"imported v{imported} ***")
    print("[app] clearing __pycache__ so the next launch runs the real code")
    removed = 0
    for root, dirs, _ in os.walk(here):
        for d in list(dirs):
            if d == "__pycache__":
                shutil.rmtree(Path(root) / d, ignore_errors=True)
                dirs.remove(d)
                removed += 1
    print(f"[app] removed {removed} __pycache__ director"
          f"{'y' if removed == 1 else 'ies'}; relaunch to complete the update")


def main() -> int:
    _ensure_path()

    here = Path(__file__).resolve().parent

    try:
        _check_stale_bytecode(here)
    except Exception as exc:  # noqa: BLE001 - a diagnostic must never crash us
        print(f"[app] bytecode check failed: {exc}")

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
