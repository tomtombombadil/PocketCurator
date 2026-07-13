"""
The remote browser - Pocket Curator's game list, pointed at a network
source.

v0.63.1 redesign, from RG35xxSP/Smart Pro S field testing:

  - THE FOLDER DECIDES THE DESTINATION. Whatever remote folder you're
    in is matched against the handheld's systems (amiga -> the
    device's amiga folder), and that mapping controls both the
    extension filter and where copies land. Browsing from gba into
    atari2600 and copying no longer drops an Atari ROM into the GBA
    folder; entering a folder for a system the device doesn't have
    shows the files but blocks copying with a clear message. The
    system highlighted on the carousel only chooses the STARTING
    folder (smart-jump).
  - Navigation is an explicit path stack: B always goes back exactly
    one level; backing out of the top listing leaves the browser. No
    more surprise disconnects.
  - All listings load in a background thread with a visible
    "Opening connection..." / "Loading folder..." state - a slow
    server can no longer freeze the UI, and the connection message is
    actually readable.
  - Layout, fonts, and image sizing mirror the deletion game list
    exactly: same list width, same base-font rows, same 0.70-height
    image area, same 0.85x description font, same legend metrics.
    Y jumps to a letter and Select opens Settings, same as there.
  - While the queue runs, the legend shows only "Copying 4/10: Title"
    over a thick whole-queue progress bar - no per-file noise - and
    once it finishes the normal help text simply returns.
"""

from __future__ import annotations

import posixpath
import tempfile
import threading
import urllib.parse
import xml.etree.ElementTree as ET
import re
from pathlib import Path
from typing import Dict, List, Optional, Set

import pygame

from ..fetchqueue import FetchJob, FetchQueue, MediaFile
from ..webdav import DavClient, DavError, RemoteEntry, format_size
from ..render import (draw_stars, draw_wrapped_text, render_clipped_text,
                      wrap_text)

FETCH_GREEN = (64, 224, 96)
EXISTS_YELLOW = (235, 200, 50)  # marked but already on the device

# Folder-name translation layer: firmwares disagree about what some
# system folders are called (ROCKNIX/Knulli use Batocera-style names,
# ArkOS-family and AmberELEC use 351elec/RetroPie-style). Every name in
# a group resolves to whichever of them exists on THIS device, both for
# mapping a remote folder to a local destination and for the smart-jump
# search. Groups are bidirectional.
ALIAS_GROUPS = [
    # Sega
    {"megadrive", "genesis", "md"},
    {"segacd", "megacd"},
    {"sega32x", "32x"},
    {"saturn", "segasaturn"},
    {"dreamcast", "dc"},
    {"mastersystem", "ms", "sms"},
    {"gamegear", "gg"},
    {"sg1000", "sg-1000"},
    # Nintendo
    {"nes", "famicom", "fc"},
    {"fds", "famicomdisksystem"},
    {"snes", "sfc", "superfamicom", "supernintendo"},
    {"n64", "nintendo64"},
    {"gb", "gameboy"},
    {"gbc", "gameboycolor"},
    {"gba", "gameboyadvance"},
    {"virtualboy", "vb"},
    {"pokemini", "pokemonmini"},
    {"gamecube", "gc", "ngc"},
    {"gw", "gameandwatch"},
    # NEC
    {"pcengine", "tg16", "turbografx16", "pce"},
    {"pcenginecd", "tg16cd", "turbografxcd", "tgcd"},
    {"supergrafx", "sgfx"},
    {"pcfx", "pc-fx"},
    # Atari (ROCKNIX/AmberELEC use atari-prefixed names; Batocera and
    # Knulli use the bare ones)
    {"lynx", "atarilynx"},
    {"jaguar", "atarijaguar"},
    {"jaguarcd", "atarijaguarcd"},
    {"atari2600", "a2600"},
    {"atari5200", "a5200"},
    {"atari7800", "a7800"},
    {"atari800", "a800"},
    {"atarist", "st"},
    # Sony
    {"psx", "ps1", "playstation"},
    {"ps2", "playstation2"},
    {"psvita", "vita"},
    # SNK
    {"ngp", "neogeopocket"},
    {"ngpc", "neogeopocketcolor"},
    {"neogeocd", "neocd"},
    # Bandai
    {"wonderswan", "wswan"},
    {"wonderswancolor", "wswanc"},
    # Arcade
    {"arcade", "mame"},
    {"fbneo", "fba", "fbn"},
    # Computers
    {"amstradcpc", "cpc"},
    {"c64", "commodore64"},
    {"vic20", "c20"},
    {"zxspectrum", "spectrum", "zx"},
    {"msx", "msx1"},
    {"pc88", "pc8800"},
    {"pc98", "pc9800"},
    {"dos", "msdos", "pc"},
    {"amigacd32", "cd32"},
    # Amiga family. Batocera/Knulli split Amiga into amiga500, amiga1200,
    # amigacd32, amigacdtv and have NO plain "amiga" folder, while a
    # remote library (and ROCKNIX) commonly use "amiga". Group them so a
    # remote "amiga" folder resolves to whichever Amiga system the device
    # actually has. amigacd32 keeps its own group above (it's CD media,
    # not a floppy Amiga); we include it here too so the broad "amiga"
    # name can still reach it if it's the only Amiga system present.
    {"amiga", "amiga500", "amiga1200", "amigacdtv", "commodoreamiga"},
    # Other consoles
    {"colecovision", "coleco"},
    {"intellivision", "intv"},
    {"odyssey2", "videopac", "o2em"},
    {"channelf", "fairchild"},
    {"cdi", "cdimono1", "philipscdi"},
    {"3do", "panasonic3do"},
    {"pico8", "pico-8"},
]
_ALIASES = {}
for _grp in ALIAS_GROUPS:
    for _n in _grp:
        _ALIASES[_n] = _grp


_REGION_CAPS = {
    "us": "US", "usa": "USA", "eu": "EU", "europe": "Europe",
    "jp": "JP", "jpn": "JP", "japan": "Japan", "world": "World",
    "uk": "UK", "fr": "FR", "de": "DE", "es": "ES", "it": "IT",
    "kr": "KR", "korea": "Korea", "cn": "CN", "china": "China",
    "br": "BR", "au": "AU", "ca": "CA", "asia": "Asia",
}


def _format_region(region: str) -> str:
    """Display regions in their conventional caps: us -> US, eu -> EU,
    japan -> Japan. Multi-region strings (USA, Europe) keep their
    separators."""
    if not region:
        return ""
    parts = re.split(r"([,/|]| - )", region)
    out = []
    for p in parts:
        key = p.strip().lower()
        if key in _REGION_CAPS:
            out.append(p.replace(p.strip(), _REGION_CAPS[key]))
        else:
            out.append(p)
    return "".join(out)


def expand_names(name: str):
    """name + every alias of it, lowercased - from BOTH the hand-curated
    firmware matrix (system_matrix.csv, authoritative) and the built-in
    alias groups (fallback for anything not yet in the matrix)."""
    n = name.lower()
    names = set(_ALIASES.get(n, {n})) | {n}
    try:
        from ..system_matrix import get_matrix
        matrix_aliases = get_matrix().aliases_for(n)
        if matrix_aliases:
            names |= set(matrix_aliases)
    except Exception:  # noqa: BLE001 - matrix is best-effort
        pass
    return names

MEDIA_DIRS = ("images", "videos", "manuals", "media", "downloaded_images")
MEDIA_TAGS = ("image", "thumbnail", "marquee", "video", "manual")
PREVIEW_DEBOUNCE_MS = 450


class _RemoteGamelist:
    """Parsed remote gamelist.xml for one folder, indexed by basename."""

    def __init__(self, raw: bytes):
        self.by_name: Dict[str, ET.Element] = {}
        try:
            root = ET.fromstring(raw)
        except ET.ParseError:
            return
        for g in root.iter("game"):
            p = (g.findtext("path") or "").strip()
            if p:
                self.by_name[posixpath.basename(p)] = g

    def entry(self, rom_name: str) -> Optional[ET.Element]:
        return self.by_name.get(rom_name)


class RemoteBrowserScreen:
    def __init__(self, app, system: dict, client: DavClient,
                 systems: Optional[List[dict]] = None):
        self.app = app
        self.launch_system = system
        self.all_systems = systems or [system]
        self.client = client

        self.cwd = "/"
        self.context: Optional[dict] = None   # device system for cwd
        self.entries: List[RemoteEntry] = []
        self.selected = 0
        self.scroll = 0
        self.flagged: Set[int] = set()
        self.flagged_existing: Set[int] = set()   # marked AND on device
        # Description scroll state - exactly the deletion screen's
        # mechanism: idle autoscroll unless L2/R2 took manual control.
        self._desc_offset_px: float = 0.0
        self._desc_manual: bool = False
        self._desc_total_h: int = 0
        self._desc_visible_h: int = 0
        self._desc_line_h: int = 0
        self._desc_pause_until: int = 0
        self._desc_last_ms: int = 0
        self.error = ""
        self.toast = ""
        self._toast_until = 0
        self._nav: List[str] = []              # path stack (parents)

        self._loading = True
        self._loading_msg = "Opening connection..."
        self._copied_any = False

        self._listing_cache: Dict[str, List[RemoteEntry]] = {}
        self._gamelist_cache: Dict[str, Optional[_RemoteGamelist]] = {}
        self._preview_due_ms = 0
        self._preview_for = -1
        self._preview_img: Optional[pygame.Surface] = None
        self._preview_img_for = -1
        self._tmpdir = Path(tempfile.mkdtemp(prefix="pc_remote_"))

        self._load_async("/", smart_jump=True, push=False)

    # ------------------------------------------------------------------
    # System context: the folder decides the destination
    # ------------------------------------------------------------------

    def _system_lookup(self) -> Dict[str, dict]:
        """Every name a device system answers to - shortname, its roms
        folder's leaf, and all aliases of both - maps to that system."""
        out: Dict[str, dict] = {}
        # TWO-PASS: exact shortnames and folder leafs claim their names
        # first, then aliases fill the gaps. Critical on firmwares that
        # ship region variants as separate systems (ROCKNIX has both
        # megadrive AND genesis, nes AND famicom): a remote 'genesis'
        # folder must hit the device's genesis, not megadrive-by-alias.
        for s in self.all_systems:                       # pass 1: exact
            out.setdefault(s["shortname"].lower(), s)
            leaf = Path(str(s.get("path", ""))).name.lower()
            if leaf:
                out.setdefault(leaf, s)
        for s in self.all_systems:                       # pass 2: aliases
            names = set(expand_names(s["shortname"]))
            leaf = Path(str(s.get("path", ""))).name
            if leaf:
                names |= expand_names(leaf)
            for n in names:
                out.setdefault(n, s)
        return out

    def _context_for(self, href: str) -> Optional[dict]:
        """Deepest path segment that names one of the device's systems
        wins. '/stuff/roms/amiga' -> the device's amiga system."""
        lookup = self._system_lookup()
        decoded = urllib.parse.unquote(href)
        for seg in reversed([s for s in decoded.split("/") if s]):
            hit = lookup.get(seg.lower())
            if hit is not None:
                return hit
        return None

    # ------------------------------------------------------------------
    # Listing + navigation
    # ------------------------------------------------------------------

    def _listdir(self, href: str) -> List[RemoteEntry]:
        if href not in self._listing_cache:
            self._listing_cache[href] = self.client.listdir(href)
        return self._listing_cache[href]

    def _load_async(self, href: str, smart_jump: bool = False,
                    push: bool = True) -> None:
        """Fetch + present a folder in a worker thread. `push` records
        the current folder on the back stack (False for the initial
        load and for backward moves)."""
        self._loading = True
        self._loading_msg = ("Opening connection..." if smart_jump
                             else "Loading folder...")
        prev = self.cwd

        def work() -> None:
            target = href
            try:
                entries = self._listdir(target)
                if smart_jump:
                    jumped = self._smart_target(target, entries)
                    if jumped is not None:
                        target = jumped
                        entries = self._listdir(target)
            except DavError as exc:
                self.error = str(exc)
                self._loading = False
                return
            if push and prev:
                self._nav.append(prev)
            self.error = ""
            self.cwd = target
            self.context = self._context_for(target)
            self.entries = self._filtered(entries)
            self.selected = 0
            self.scroll = 0
            self.flagged.clear()
            self.flagged_existing.clear()
            self._preview_for = -1
            self._preview_img_for = -1
            self._preview_img = None
            self._loading = False

        threading.Thread(target=work, daemon=True).start()

    def _smart_target(self, href: str, entries: List[RemoteEntry]
                      ) -> Optional[str]:
        """Initial-open helper: walk toward the folder named after the
        LAUNCH system, following one level of 'roms/' indirection."""
        wanted = set(expand_names(self.launch_system["shortname"]))
        leaf = Path(str(self.launch_system.get("path", ""))).name
        if leaf:
            wanted |= expand_names(leaf)
        dirs = {e.name.lower(): e for e in entries if e.is_dir}
        for w in wanted:
            if w in dirs:
                self._nav.append(href)       # B from the jump = source root
                return dirs[w].href
        if "roms" in dirs:
            try:
                inner = self._listdir(dirs["roms"].href)
            except DavError:
                return None
            inner_dirs = {e.name.lower(): e for e in inner if e.is_dir}
            for w in wanted:
                if w in inner_dirs:
                    self._nav.append(href)
                    self._nav.append(dirs["roms"].href)
                    return inner_dirs[w].href
        return None

    def _filtered(self, entries: List[RemoteEntry]) -> List[RemoteEntry]:
        """Folders always; files filtered by the CURRENT FOLDER's system
        extensions. A folder that maps to no device system shows all
        files (you can look, just not copy)."""
        out = [e for e in entries if e.is_dir]
        ctx = self._context_for(self.cwd) if self.context is None \
            else self.context
        exts = None
        if ctx is not None:
            exts = {e.lower() if e.startswith(".") else "." + e.lower()
                    for e in ctx.get("extensions", [])}
        if exts:
            out += [e for e in entries if not e.is_dir and e.ext in exts]
        else:
            out += [e for e in entries
                    if not e.is_dir and e.name.lower() != "gamelist.xml"]
        return out

    # ------------------------------------------------------------------
    # Remote gamelist + media resolution
    # ------------------------------------------------------------------

    def _gamelist_for_cwd(self) -> Optional[_RemoteGamelist]:
        if self.cwd not in self._gamelist_cache:
            gl = None
            try:
                raw_entries = self._listdir(self.cwd)
                hit = next((e for e in raw_entries
                            if e.name.lower() == "gamelist.xml"), None)
                if hit is not None:
                    gl = _RemoteGamelist(self.client.fetch_bytes(hit.href))
            except DavError:
                gl = None
            self._gamelist_cache[self.cwd] = gl
        return self._gamelist_cache[self.cwd]

    def _resolve_href(self, rel: str) -> str:
        rel = rel.lstrip("./")
        base = self.cwd if self.cwd.endswith("/") else self.cwd + "/"
        return base + urllib.parse.quote(rel)

    def _media_for(self, rom: RemoteEntry) -> List[MediaFile]:
        out: List[MediaFile] = []
        seen: Set[str] = set()
        gl = self._gamelist_for_cwd()
        entry = gl.entry(rom.name) if gl else None
        if entry is not None:
            for tag in MEDIA_TAGS:
                rel = (entry.findtext(tag) or "").strip()
                if not rel or rel in seen:
                    continue
                seen.add(rel)
                href = self._resolve_href(rel)
                size = self._size_of(href)
                if size is None:
                    continue
                out.append(MediaFile(href=href,
                                     rel_dest=rel.lstrip("./"), size=size))
        if out:
            return out
        stem = Path(rom.name).stem
        try:
            raw = self._listdir(self.cwd)
        except DavError:
            return out
        for d in raw:
            if not d.is_dir or d.name.lower() not in MEDIA_DIRS:
                continue
            try:
                for f in self._listdir(d.href):
                    if not f.is_dir and Path(f.name).stem.startswith(stem):
                        out.append(MediaFile(
                            href=f.href,
                            rel_dest=f"{d.name}/{f.name}",
                            size=f.size))
            except DavError:
                continue
        return out

    def _size_of(self, href: str) -> Optional[int]:
        parent = posixpath.dirname(urllib.parse.unquote(href))
        name = posixpath.basename(urllib.parse.unquote(href))
        try:
            for e in self._listdir(urllib.parse.quote(parent)):
                if e.name == name:
                    return e.size
        except DavError:
            pass
        return None

    # ------------------------------------------------------------------
    # Queue
    # ------------------------------------------------------------------

    def _exists_locally(self, e: RemoteEntry) -> bool:
        ctx = self.context
        return (ctx is not None
                and (Path(ctx["path"]) / e.name).exists())

    def _toastline(self, msg: str, ms: int = 4000) -> None:
        self.toast = msg
        self._toast_until = pygame.time.get_ticks() + ms

    def _start_copy(self, with_media: bool,
                    skip_existing: bool = False) -> None:
        ctx = self.context
        if ctx is None:
            self._toastline("This handheld has no system matching "
                            "this folder - can't copy here.")
            return
        dest = Path(ctx["path"])
        # Safety: never write into Pocket Curator's own port directory.
        # A misparsed or relative es_systems <path> used to resolve
        # against the cwd and dump fetched games into
        # roms/ports/pocketcurator; refuse rather than scatter files into
        # the app (which on some firmwares could even break the next
        # launch). Require an absolute destination outside the port dir.
        try:
            port_dir = Path(self.app.port_dir).resolve()
            dest_res = dest.resolve()
            in_port = (dest_res == port_dir
                       or port_dir in dest_res.parents)
        except (OSError, ValueError):
            in_port = False
        if not dest.is_absolute() or in_port:
            print(f"[fetch] REFUSING copy: destination '{dest}' for system "
                  f"'{ctx.get('shortname')}' is not a valid roms folder "
                  f"(absolute={dest.is_absolute()}, in_port={in_port}).")
            self._toastline(
                "Can't copy: this system's folder didn't resolve to a "
                "real location on your device. Nothing was copied.",
                5000)
            return
        # ONE queue for the whole session; every job carries its own
        # destination, so marking more games mid-copy - same system or
        # a different one - just grows the queue and the progress bar.
        src_url = getattr(self.client, "base_url", None) or getattr(
            self.client, "url", "?")
        print(f"[fetch] start: server={src_url} system='{ctx['shortname']}' "
              f"display='{ctx['display']}' dest={dest} "
              f"with_media={with_media} skip_existing={skip_existing}")
        q = getattr(self.app, "fetch_queue", None)
        if q is None:
            q = FetchQueue(self.client, dest,
                           on_job_done=self._merge_job_metadata)
            self.app.fetch_queue = q
        # Copy w/ Scrapings + metadata injection: back the gamelist up
        # once per system per session, BEFORE the first merge can touch
        # it. (Restorable via Settings -> Restore Gamelist Backup.)
        if with_media:
            key = ctx["shortname"]
            done = getattr(self.app, "_gl_backed_up", None)
            if done is None:
                done = set()
                self.app._gl_backed_up = done
            if key not in done:
                from ..gamelist_merge import backup_gamelist
                backup_gamelist(self.app.port_dir, ctx)
                done.add(key)
        gl = self._gamelist_for_cwd() if with_media else None
        jobs: List[FetchJob] = []
        skipped = 0
        for i in sorted(self.flagged):
            e = self.entries[i]
            if skip_existing and (dest / e.name).exists():
                skipped += 1
                continue
            media = self._media_for(e) if with_media else []
            entry_xml = None
            if gl is not None:
                g = gl.entry(e.name)
                if g is not None:
                    entry_xml = ET.tostring(g, encoding="unicode")
            jobs.append(FetchJob(title=Path(e.name).stem, rom_href=e.href,
                                 rom_name=e.name, rom_size=e.size,
                                 media=media, gamelist_entry=entry_xml,
                                 dest_dir=dest,
                                 merge_overwrite=not skip_existing))
        if not jobs:
            self.flagged.clear()
            self.flagged_existing.clear()
            self._toastline("All of those are already on this handheld - "
                            "nothing to copy.")
            return
        err = q.enqueue(jobs)
        if err:
            self._toastline(err)
        else:
            self.app.fetches_occurred = True
            self._copied_any = True
            self.flagged.clear()
            self.flagged_existing.clear()
            note = (f"Queued {len(jobs)} "
                    f"game{'s' if len(jobs) != 1 else ''} "
                    f"for {ctx['display']}")
            if skipped:
                note += f" ({skipped} already here, skipped)"
            elif with_media:
                note += " with scrapings"
            self._toastline(note)

    def _merge_job_metadata(self, job: FetchJob, success: bool) -> None:
        """Queue callback (worker thread): after a game's files land,
        inject its source gamelist entry into the destination
        gamelist.xml. Failures log and never disturb the copy."""
        if not success or not job.gamelist_entry or not job.dest_dir:
            return
        try:
            from ..gamelist_merge import merge_entries
            merge_entries(job.dest_dir, [job.gamelist_entry],
                          overwrite=job.merge_overwrite)
            # Destination system just gained a game; its carousel count
            # (fixed at startup) is now stale. Flag it for recount on
            # the way back. set.add is atomic, so calling this from the
            # copy worker thread is safe.
            self.app.dirty_gamelists.add(str(Path(job.dest_dir)))
        except Exception as exc:  # noqa: BLE001 - never break the copy
            print(f"[gamelist-merge] skipped for '{job.title}': {exc}")

    # ------------------------------------------------------------------
    # Input
    # ------------------------------------------------------------------

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type != pygame.KEYDOWN:
            return
        k = event.key
        if k == pygame.K_ESCAPE:
            self._go_back()
        elif self._loading:
            return
        elif k == pygame.K_DOWN:
            self._move(+1)
        elif k == pygame.K_UP:
            self._move(-1)
        elif k == pygame.K_PAGEDOWN:
            self._move(+12)
        elif k == pygame.K_PAGEUP:
            self._move(-12)
        elif k == pygame.K_HOME:
            self._jump_to(0)
        elif k == pygame.K_END:
            self._jump_to(len(self.entries) - 1)
        elif k == pygame.K_RETURN:
            e = (self.entries[self.selected]
                 if self.entries else None)
            if (e is not None and not e.is_dir
                    and self.app.is_repeat(k)):
                # Hold-A mass-mark, exactly like the deletion list:
                # advance first, then mark, so the initial press's mark
                # isn't undone by the first repeat tick.
                old_sel = self.selected
                self._move(+1, wrap=False)
                cur = self.entries[self.selected]
                if self.selected != old_sel and not cur.is_dir:
                    self.flagged.add(self.selected)
                    if self._exists_locally(cur):
                        self.flagged_existing.add(self.selected)
            else:
                self._activate()
        elif k == pygame.K_x:
            self._confirm_copy()
        elif k == pygame.K_y:
            if self.entries:
                from .jump import JumpScreen
                self.app.push_screen(JumpScreen(self.app, self.entries,
                                                on_pick=self._jump_to))
        elif k == pygame.K_LEFTBRACKET:
            # L2: page up. Takes manual control - autoscroll won't
            # fight us. (Same semantics as the deletion screen.)
            self._desc_manual = True
            page = max(20, self._desc_visible_h - self._desc_line_h)
            self._desc_offset_px = max(0.0, self._desc_offset_px - page)
        elif k == pygame.K_RIGHTBRACKET:
            # R2: page down, clamped to the last line.
            self._desc_manual = True
            page = max(20, self._desc_visible_h - self._desc_line_h)
            max_offset = max(0, self._desc_total_h - self._desc_visible_h)
            self._desc_offset_px = min(float(max_offset),
                                       self._desc_offset_px + page)
        elif k == pygame.K_F1:
            from .settings_screen import SettingsScreen
            self.app.push_screen(SettingsScreen(self.app))

    def _move(self, d: int, wrap=None) -> None:
        """Same semantics as the deletion list: wrap on a tap, stop at
        the ends while a direction is held."""
        if not self.entries:
            return
        n = len(self.entries)
        if wrap is None:
            wrap = not self.app.is_repeat()
        if wrap and (self.selected + d < 0 or self.selected + d >= n):
            self.selected = (self.selected + d) % n
        else:
            self.selected = max(0, min(n - 1, self.selected + d))
        self._preview_due_ms = pygame.time.get_ticks() + PREVIEW_DEBOUNCE_MS
        self._desc_offset_px = 0.0
        self._desc_manual = False
        self._desc_pause_until = pygame.time.get_ticks() + 1200

    def _jump_to(self, index: int) -> None:
        if self.entries:
            self.selected = max(0, min(len(self.entries) - 1, index))
            self._preview_due_ms = (pygame.time.get_ticks()
                                    + PREVIEW_DEBOUNCE_MS)

    def _activate(self) -> None:
        if not self.entries:
            return
        e = self.entries[self.selected]
        if e.is_dir:
            self._load_async(e.href, push=True)
        else:
            if self.selected in self.flagged:
                self.flagged.discard(self.selected)
                self.flagged_existing.discard(self.selected)
            else:
                self.flagged.add(self.selected)
                if self._exists_locally(e):
                    self.flagged_existing.add(self.selected)

    def _go_back(self) -> None:
        """B: exactly one level back along the visited path; at the top
        of the stack, leave the browser. (No post-copy notice: fetched
        games already show in Pocket Curator's own lists immediately, and
        EmulationStation refreshes automatically on exit, so the old
        ATTENTION pop-up no longer served a purpose.)"""
        if self._nav:
            self._load_async(self._nav.pop(), push=False)
            return
        self.app.pop_screen()

    def _confirm_copy(self) -> None:
        if self.context is None:
            from .remote_flow import NoticeScreen

            def clear():
                self.flagged.clear()
                self.flagged_existing.clear()
            self.app.push_screen(NoticeScreen(
                self.app, "Can't copy here",
                "Your device does not have a matching roms folder for "
                "this game system. These files can't be copied.",
                ok_label="A Cancel", on_close=clear))
            return
        if not self.flagged:
            self._toastline("Mark games with A first.", 3000)
            return
        marked = [self.entries[i] for i in sorted(self.flagged)]
        rom_bytes = sum(e.size for e in marked)
        # Media sizing requires a PROPFIND per game and is slow for big
        # selections, so we DON'T block on it here. The dialog opens
        # immediately and computes media size in the background; pass a
        # callable it can run off-thread plus the rom total it can show
        # right away.
        def size_media():
            total = 0
            for e in marked:
                for m in self._media_for(e):
                    total += max(0, m.size)
            return total
        from .remote_confirm import RemoteConfirmScreen
        self.app.push_screen(RemoteConfirmScreen(
            self.app, self.context, marked, rom_bytes,
            media_sizer=size_media, on_choice=self._start_copy))

    # ------------------------------------------------------------------
    # Preview (remote gamelist + screenshot)
    # ------------------------------------------------------------------

    def _maybe_preview(self) -> None:
        now = pygame.time.get_ticks()
        if (self._loading or not self.entries
                or now < self._preview_due_ms
                or self._preview_for == self.selected):
            return
        self._preview_for = self.selected
        e = self.entries[self.selected]
        if e.is_dir:
            return

        def work(sel: int, entry: RemoteEntry, max_w: int, max_h: int) -> None:
            gl = self._gamelist_for_cwd()
            g = gl.entry(entry.name) if gl else None
            if g is None or self._preview_for != sel:
                return
            rel = (g.findtext("image") or "").strip()
            if not rel:
                return
            try:
                raw = self.client.fetch_bytes(self._resolve_href(rel),
                                              max_bytes=6 * 1024 * 1024)
                tmp = self._tmpdir / f"prev_{sel}.img"
                tmp.write_bytes(raw)
                img = pygame.image.load(str(tmp))
                # scale exactly like ImageCache.load_scaled: fit the
                # box with NO upscale cap - remote thumbs are small and
                # the deletion screen grows them to fill the panel
                scale = min(max_w / img.get_width(),
                            max_h / img.get_height())
                img = pygame.transform.smoothscale(
                    img, (max(1, int(img.get_width() * scale)),
                          max(1, int(img.get_height() * scale))))
                if self._preview_for == sel:
                    self._preview_img = img
                    self._preview_img_for = sel
            except (DavError, pygame.error, OSError, ValueError):
                pass

        # image box matches the deletion screen's right panel: width
        # minus padding, 70% of panel height
        ui = self.app.config["ui"]
        W = pygame.display.get_surface().get_width()
        H = pygame.display.get_surface().get_height()
        legend_h = max(28, ui["font_size_base"] + 8)
        hdr_font = self.app.fonts.get(
            max(11, int(ui["font_size_base"] * 0.7)))
        header_h = hdr_font.get_linesize() + 6
        list_w = int(W * ui["list_width_pct"])
        pad = 16
        max_w = (W - list_w) - 2 * pad   # panel width is the same either side
        max_h = int((H - legend_h - header_h) * 0.70)
        threading.Thread(target=work,
                         args=(self.selected, e, max_w, max_h),
                         daemon=True).start()

    # ------------------------------------------------------------------
    # Draw - geometry and fonts mirror game_list.py
    # ------------------------------------------------------------------

    def draw(self, surface: pygame.Surface) -> None:
        self._maybe_preview()
        theme = self.app.config["theme"]
        ui = self.app.config["ui"]
        base = ui["font_size_base"]
        W, H = surface.get_size()
        surface.fill(tuple(theme["background_color"]))

        legend_h = max(28, base + 8)
        from ..render import (draw_screen_header, HEADER_FETCH_BG,
                              split_layout)
        header_h = draw_screen_header(surface, self.app, theme, ui,
                                      "FETCH FROM WebDAV", HEADER_FETCH_BG)
        list_rect, right_rect = split_layout(
            W, header_h, H - legend_h - header_h, ui["list_width_pct"],
            ui.get("games_list_side", "left"))

        if self._loading:
            font = self.app.fonts.get(base)
            msg = font.render(self._loading_msg, True,
                              tuple(theme["text_color"]))
            surface.blit(msg, ((W - msg.get_width()) // 2,
                               (H - msg.get_height()) // 2))
            self._draw_legend(surface, theme, ui,
                              pygame.Rect(0, H - legend_h, W, legend_h))
            return

        self._draw_list(surface, theme, ui, list_rect)
        self._draw_right_panel(surface, theme, ui, right_rect)
        self._draw_legend(surface, theme, ui,
                          pygame.Rect(0, H - legend_h, W, legend_h))

    def _draw_list(self, surface, theme, ui, rect) -> None:
        font = self.app.fonts.get(ui["font_size_base"])
        text_c = tuple(theme["text_color"])
        muted = tuple(theme["muted_color"])
        hi = tuple(theme["highlight_color"])
        hi_text = tuple(theme.get("highlight_text_color",
                                  theme["background_color"]))

        if self.error:
            draw_wrapped_text(surface,
                              wrap_text(self.error, font, rect.w - 24),
                              font, muted, rect.inflate(-24, -24))
            return
        if not self.entries:
            msg = ("This folder is empty." if self.context is None else
                   f"No {self.context['display']} games here.")
            draw_wrapped_text(surface, wrap_text(msg, font, rect.w - 24),
                              font, muted, rect.inflate(-24, -24))
            return

        line_h = font.get_linesize() + 4
        visible = max(1, rect.h // line_h)
        if self.selected < self.scroll:
            self.scroll = self.selected
        if self.selected >= self.scroll + visible:
            self.scroll = self.selected - visible + 1
        y = rect.y + 2
        for i in range(self.scroll,
                       min(len(self.entries), self.scroll + visible)):
            e = self.entries[i]
            row = pygame.Rect(rect.x, y, rect.w, line_h)
            flagged = i in self.flagged
            exists = i in self.flagged_existing
            if i == self.selected:
                pygame.draw.rect(surface, hi, row)
            # Marked rows keep normal text color; an inverted chip
            # carries the signal so it stays legible under any font or
            # highlight color: black + on a green chip for new games,
            # black ? on a yellow chip for games already on the device.
            fg = hi_text if i == self.selected else text_c
            x = row.x + 8
            if e.is_dir:
                x += self._draw_folder_icon(surface, x, row, fg) + 8
            elif flagged and exists:
                x += self._draw_chip(surface, x, row, font, "?",
                                     EXISTS_YELLOW) + 8
            elif flagged:
                x += self._draw_chip(surface, x, row, font, "+",
                                     FETCH_GREEN) + 8
            render_clipped_text(surface, e.name, font, fg,
                                pygame.Rect(x, row.y + 1,
                                            row.right - x - 8, line_h))
            y += line_h

    @staticmethod
    def _draw_chip(surface, x, row, font, glyph, color) -> int:
        """A colored rounded chip with a black glyph - "+" for new, "?"
        for already-on-device. Black-on-bright stays readable whatever
        the user picks for font and highlight colors."""
        size = max(12, int(row.h * 0.66))
        chip = pygame.Rect(x, row.y + (row.h - size) // 2, size, size)
        pygame.draw.rect(surface, color, chip, border_radius=3)
        cx, cy = chip.centerx, chip.centery
        if glyph == "+":
            bar = max(2, size // 6)
            half = int(size * 0.30)
            pygame.draw.rect(surface, (0, 0, 0),
                             pygame.Rect(cx - bar // 2, cy - half, bar, half * 2))
            pygame.draw.rect(surface, (0, 0, 0),
                             pygame.Rect(cx - half, cy - bar // 2, half * 2, bar))
        else:  # "?" - render the glyph in black, centered
            gf = font.render("?", True, (0, 0, 0))
            surface.blit(gf, (cx - gf.get_width() // 2,
                              cy - gf.get_height() // 2))
        return size

    @staticmethod
    def _draw_folder_icon(surface, x, row, color) -> int:
        h = max(10, int(row.h * 0.52))
        w = int(h * 1.3)
        top = row.y + (row.h - h) // 2
        pygame.draw.rect(surface, color,
                         pygame.Rect(x, top + 2, w, h - 2), width=1)
        pygame.draw.rect(surface, color,
                         pygame.Rect(x, top, max(3, w // 3), 3), width=1)
        return w

    def _draw_right_panel(self, surface, theme, ui, rect) -> None:
        pygame.draw.rect(surface, tuple(theme["panel_bg_color"]), rect)
        base = ui["font_size_base"]
        text_c = tuple(theme["text_color"])
        muted = tuple(theme["muted_color"])
        pad = 16

        # header: which device system this folder feeds
        meta_font = self.app.fonts.get(max(12, int(base * 0.8)))
        where = (f"-> {self.context['display']}" if self.context
                 else "-> no matching system on this handheld")
        head = f"{urllib.parse.unquote(self.cwd)}  {where}"
        render_clipped_text(surface, head, meta_font,
                            muted, pygame.Rect(rect.x + pad, rect.y + 4,
                                               rect.w - 2 * pad,
                                               meta_font.get_linesize()))

        if not self.entries:
            return
        e = self.entries[self.selected]
        # Filesize lives on the header line, right-justified - it no
        # longer costs a line under the image.
        if not e.is_dir and e.size:
            sz = meta_font.render(format_size(e.size), True, muted)
            surface.blit(sz, (rect.right - pad - sz.get_width(),
                              rect.y + 4))
        img_y = rect.y + 4 + meta_font.get_linesize() + 6
        max_img_w = rect.width - 2 * pad
        # 0.64 (was 0.70): one image line traded for a third visible
        # description line.
        max_img_h = int(rect.height * 0.64)

        if e.is_dir:
            draw_wrapped_text(surface,
                              wrap_text("A opens this folder.", meta_font,
                                        max_img_w),
                              meta_font, muted,
                              pygame.Rect(rect.x + pad, img_y,
                                          max_img_w, rect.bottom - img_y))
            return

        img_area_bottom = img_y + max_img_h
        if (self._preview_img is not None
                and self._preview_img_for == self.selected):
            img = self._preview_img
            # The preview is scaled by a background worker against the
            # max_h captured when the request was made. If that differs
            # from the area we're drawing into now (different panel size,
            # e.g. on Batocera), a too-tall cached image would overflow
            # the reserved area and clip down into the stars/region line.
            # Clamp to the CURRENT reserved area before blitting so the
            # image can never bleed past img_area_bottom - matching the
            # deletion screen, which rescales every frame.
            iw, ih = img.get_width(), img.get_height()
            if iw > max_img_w or ih > max_img_h:
                fit = min(max_img_w / iw, max_img_h / ih)
                img = pygame.transform.smoothscale(
                    img, (max(1, int(iw * fit)), max(1, int(ih * fit))))
            ix = rect.x + (rect.width - img.get_width()) // 2
            iy = img_y + (max_img_h - img.get_height()) // 2
            surface.blit(img, (ix, iy))

        y = img_area_bottom + 6
        gl = self._gamelist_cache.get(self.cwd)
        g = gl.entry(e.name) if gl else None
        # One meta line: stars (ALWAYS five - empty outlines when no
        # rating, like the deletion screen) + region + genre.
        rating = 0.0
        genre = region = ""
        if g is not None:
            try:
                rating = float((g.findtext("rating") or "0").strip() or 0)
            except (ValueError, TypeError):
                rating = 0.0
            genre = (g.findtext("genre") or "").strip()
            region = (g.findtext("region") or "").strip()
        if not region:
            import re as _re
            m = _re.search(r"\(([^)]+)\)", e.name)
            if m and len(m.group(1)) <= 24:
                region = m.group(1)
        region = _format_region(region)
        x = rect.x + pad
        x += draw_stars(surface, x, y, rating,
                        tuple(theme["accent_color"]), muted) + 12
        bits = "  \u2022  ".join(b for b in (region, genre) if b)
        if bits:
            render_clipped_text(surface, bits, meta_font, muted,
                                pygame.Rect(x, y, rect.right - pad - x,
                                            meta_font.get_linesize()))
        y += meta_font.get_linesize() + 6
        # Description: 3+ visible lines, idle autoscroll, L2/R2 manual
        # paging - the deletion screen's mechanism, mirrored.
        desc = (g.findtext("desc") or "").strip() if g is not None else ""
        if desc:
            desc_font = self.app.fonts.get(max(12, int(base * 0.85)))
            drect = pygame.Rect(rect.x + pad, y, max_img_w,
                                rect.bottom - y - 6)
            lines = wrap_text(desc, desc_font, drect.w)
            self._desc_line_h = desc_font.get_linesize()
            self._desc_total_h = self._desc_line_h * len(lines)
            self._desc_visible_h = drect.height
            now = pygame.time.get_ticks()
            dt = min(0.1, max(0.0, (now - self._desc_last_ms) / 1000.0)) \
                if self._desc_last_ms else 0.0
            self._desc_last_ms = now
            overflow = max(0, self._desc_total_h - self._desc_visible_h)
            if (ui.get("description_autoscroll", True)
                    and not self._desc_manual and overflow
                    and now >= self._desc_pause_until):
                speed = ui.get("description_autoscroll_speed_px_per_sec", 18)
                if getattr(self, "_desc_at_bottom", False):
                    # paused at the end; snap back to the top and pause
                    self._desc_offset_px = 0.0
                    self._desc_at_bottom = False
                    self._desc_pause_until = now + 1200
                else:
                    self._desc_offset_px += speed * dt
                    if self._desc_offset_px >= overflow:
                        self._desc_offset_px = float(overflow)
                        self._desc_at_bottom = True
                        self._desc_pause_until = now + 2500
            if self._desc_offset_px > overflow:
                self._desc_offset_px = float(overflow)
            # Draw exactly like the deletion screen: pass the REAL drect
            # and let draw_wrapped_text handle clipping + the scroll via
            # its y_offset. (Previously we faked the scroll by moving an
            # oversized rect and set our own clip, which draw_wrapped_text
            # overwrote - so the text scrolled up over the image/stars.)
            draw_wrapped_text(surface, lines, desc_font, text_c, drect,
                              y_offset=int(self._desc_offset_px))

    def _draw_legend(self, surface, theme, ui, rect) -> None:
        pygame.draw.rect(surface, tuple(theme["legend_bg_color"]), rect)
        font = self.app.fonts.get(max(11, int(ui["font_size_base"] * 0.7)))
        fg = tuple(theme["legend_text_color"])
        q = getattr(self.app, "fetch_queue", None)
        snap = q.snapshot() if q is not None else None
        now = pygame.time.get_ticks()

        toast_live = self.toast and now < self._toast_until
        if snap is not None and snap.active:
            # "Copying 4/10: Title" over a thick whole-queue bar. A
            # live toast REPLACES the text line for its few seconds -
            # refusals and notices must be visible mid-copy, not hidden
            # under the progress text.
            txt = font.render(self.toast if toast_live
                              else snap.legend_text(), True, fg)
            surface.blit(txt, (10, rect.y + 2))
            # Right-justified live transfer rate on the same line as
            # "Copying ##/##" (hidden while a toast is occupying the line).
            if not toast_live:
                spd = snap.speed_text()
                if spd:
                    spd_surf = font.render(spd, True, fg)
                    surface.blit(spd_surf,
                                 (rect.right - 10 - spd_surf.get_width(),
                                  rect.y + 2))
            bar_h = 7
            bar = pygame.Rect(10, rect.bottom - bar_h - 2,
                              rect.w - 20, bar_h)
            pygame.draw.rect(surface, tuple(theme["muted_color"]), bar, 1)
            fill = int((bar.w - 2) * snap.queue_fraction())
            pygame.draw.rect(surface, fg,
                             pygame.Rect(bar.x + 1, bar.y + 1,
                                         fill, bar_h - 2))
            return
        if toast_live:
            surface.blit(font.render(self.toast, True, fg),
                         (10, rect.y + (rect.h - font.get_height()) // 2))
            return
        n = len(self.flagged)
        mark = f"A Mark ({n})" if n else "A Mark / Open"
        legend = f"{mark}  -  X Copy  -  Y Jump  -  Sel Settings  -  B Back"
        surface.blit(font.render(legend, True, fg),
                     (10, rect.y + (rect.h - font.get_height()) // 2))
