#!/usr/bin/env python3
"""
Pocket Curator - ports gamelist metadata writer (standalone helper).

This writes Pocket Curator's own <game> entry (name, description, artwork,
video, rating, release date) into the Ports gamelist.xml. It is invoked by
PocketCuratorMetadataInstall.sh (and, as a fallback, by the launcher).

Timing is the caller's responsibility, not this script's. EmulationStation
owns every <game> node it has parsed: when you return from a "game" (a port
counts) it rewrites that node from its in-RAM model, dropping any fields we
add while it holds the entry. The only moment a write to an existing entry
sticks is when ES is idle at its menu - so the caller runs this helper then,
and immediately asks ES to reload from disk (curl localhost:1234/reloadgames)
so ES adopts our fields into RAM and keeps them.

This script writes nothing but our managed fields and preserves whatever ES
maintains (playcount, lastplayed, gametime, md5, scrap, ...). It overwrites
our managed fields when they differ from the canonical values (so updated
artwork propagates) and is otherwise idempotent.

Exit codes:
  0 - success (whether or not anything needed changing)
  1 - failure (import/parse/write error); logged to stdout for the caller
"""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    # Layout: .../ports/pocketcurator/tools/write_ports_metadata.py
    here = Path(__file__).resolve().parent      # .../pocketcurator/tools
    port_dir = here.parent                       # .../pocketcurator
    ports_dir = port_dir.parent                  # .../ports

    # Make the "curator" package importable without relying on the
    # launcher's PYTHONPATH (this may run in a bare environment).
    if str(port_dir) not in sys.path:
        sys.path.insert(0, str(port_dir))

    try:
        from curator.ports_gamelist import ensure_entry
    except Exception as exc:  # pragma: no cover - defensive
        print(f"[write_ports_metadata] import failed: "
              f"{type(exc).__name__}: {exc}")
        return 1

    try:
        changed = ensure_entry(ports_dir=ports_dir)
        print(f"[write_ports_metadata] ports_dir={ports_dir} changed={changed}")
        return 0
    except Exception as exc:
        print(f"[write_ports_metadata] failed: "
              f"{type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
