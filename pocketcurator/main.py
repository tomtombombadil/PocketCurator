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

    # If the user deleted ROMs, EmulationStation's in-RAM gamelists are now
    # stale, so leave a flag asking the launcher to refresh ES on exit
    # (an in-place reload). If nothing was deleted, no flag is written and
    # the launcher exits cleanly with no refresh.
    #
    # Note: writing Pocket Curator's OWN metadata is handled separately by
    # PocketCuratorMetadataInstall.sh, which defers the write until ES is
    # idle - the only moment a write to our existing entry survives ES's
    # game-exit gamelist flush.
    try:
        if bool(getattr(app, "deletions_occurred", False)):
            (here / ".es_refresh_needed").write_text("deletions", encoding="utf-8")
    except Exception:
        pass

    return rc


if __name__ == "__main__":
    raise SystemExit(main())
