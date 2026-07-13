"""
Stale-gamelist notice.

gamelist.xml is the source of truth - for EmulationStation and for us.
When it lists a game whose ROM isn't on the card, the two disagree: ES
hides the entry, but our count (which counts entries, as it must) still
includes it. That's why a system can read higher in Pocket Curator than
in ES.

EmulationStation never removes those entries on its own. "Update
Gamelists" only scans for NEW ROMs; it does not garbage-collect entries
whose ROM has gone. The function that does clean them is ES's own
"Clean Gamelist & Remove Unused Media".

So Pocket Curator's job here is to REPORT, not repair. We prune entries
for ROMs we delete ourselves (that's cleaning up after ourselves), but
pre-existing drift belongs to ES, and ES should stay the only owner of
its own file. This module surfaces the drift and points at the fix.
"""

from __future__ import annotations


def warn_if_stale(app, system: dict, stats: dict) -> None:
    """Show a one-time notice if this system's gamelist lists ROMs the
    card doesn't have. Shown once per system per session; a dialog on
    every entry would be more annoying than the problem it reports."""
    missing = int(stats.get("missing", 0) or 0)
    if missing <= 0:
        return

    seen = getattr(app, "_stale_warned", None)
    if seen is None:
        seen = set()
        app._stale_warned = seen
    key = system.get("shortname") or str(system.get("path", ""))
    if key in seen:
        return
    seen.add(key)

    plural = "ROM" if missing == 1 else "ROMs"
    display = system.get("display") or system.get("shortname") or "this system"
    print(f"[gamelist] {display}: {missing} gamelist entr"
          f"{'y' if missing == 1 else 'ies'} with no ROM on disk - "
          f"advising ES 'Clean Gamelist & Remove Unused Media'")

    try:
        from .remote_flow import NoticeScreen
        app.push_screen(NoticeScreen(
            app,
            title="Gamelist out of date",
            body=(f"Pocket Curator has detected {missing} missing {plural} "
                  f"in your gamelist.xml for {display}.\n\n"
                  f"Please run Emulation Station's 'Clean Gamelist & Remove "
                  f"Unused Media' from the System > Frontend Developer "
                  f"Options menu."),
            ok_label="OK",
        ))
    except Exception as exc:  # noqa: BLE001 - a notice must never crash the app
        print(f"[gamelist] stale notice unavailable: {exc}")
