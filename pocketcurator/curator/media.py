"""
Media file discovery and deletion planning.

The scraped-media layout used by EmulationStation across firmwares is
roughly:

    <system_dir>/
        <rom>.zip
        gamelist.xml
        images/<rom>.png            <- boxart, hero, or generic image
        videos/<rom>.mp4
        marquees/<rom>.png
        thumbnails/<rom>.png
        manuals/<rom>.pdf
        screenshots/<rom>.png       <- some scrapers use this
        media/<kind>/<rom>.<ext>    <- Skraper's tree

We trust gamelist.xml's explicit references first, then fall back to scanning
the conventional subdirectories for files matching the ROM's basename.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Set

from .gamelist import Game


def gather_files_to_delete_batch(
    games: List["Game"],
    system_dir: Path,
    include_scraped_media: bool = True,
) -> List[List[Path]]:
    """
    Compute deletion plans for many games at once.

    Only files explicitly referenced by each game's gamelist.xml entry
    are returned. We do NOT scan media folders for stem-matching files
    - if a scraper wrote files that aren't named in the gamelist, the
    firmware's "orphan media cleanup" handles them, not us. This keeps
    the deletion plan instantaneous regardless of how many junk files
    exist in the media subdirs.

    Per-game plan contents:
      - the ROM file (game.rom_path)
      - game.image / .thumbnail / .marquee / .video / .manual, if present
        and ``include_scraped_media`` is True

    The unused ``system_dir`` parameter is kept in the signature for
    backwards compatibility with the call site.
    """
    if not games:
        return []

    plans: List[List[Path]] = []
    for game in games:
        targets: Set[Path] = set()
        if game.rom_path and game.rom_path.exists():
            targets.add(game.rom_path)
        if include_scraped_media:
            for explicit in (game.image, game.thumbnail, game.marquee,
                             game.video, game.manual):
                if explicit and explicit.exists():
                    targets.add(explicit)
        plans.append(sorted(targets))

    return plans


def gather_files_to_delete(game: Game, system_dir: Path,
                           include_scraped_media: bool = True) -> List[Path]:
    """
    Build the list of files that should be removed for ``game``.

    Only paths the gamelist.xml entry explicitly names are returned. No
    directory scanning. See ``gather_files_to_delete_batch`` for the
    same logic at scale.

    ``system_dir`` is kept in the signature but no longer used.
    """
    targets: Set[Path] = set()
    if game.rom_path and game.rom_path.exists():
        targets.add(game.rom_path)
    if include_scraped_media:
        for explicit in (game.image, game.thumbnail, game.marquee,
                         game.video, game.manual):
            if explicit and explicit.exists():
                targets.add(explicit)
    return sorted(targets)


def total_bytes(paths: Iterable[Path]) -> int:
    """Sum of file sizes, ignoring any that disappeared since we listed them."""
    total = 0
    for p in paths:
        try:
            total += p.stat().st_size
        except OSError:
            pass
    return total


def humanize_bytes(n: int) -> str:
    """Human-friendly byte size with a sensible unit."""
    units = ("B", "KB", "MB", "GB", "TB")
    if n < 0:
        return "0 B"
    f = float(n)
    for u in units:
        if f < 1024.0 or u == units[-1]:
            if u == "B":
                return f"{int(f)} {u}"
            return f"{f:.1f} {u}"
        f /= 1024.0
    return f"{f:.1f} TB"
