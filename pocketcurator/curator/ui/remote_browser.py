"""
The remote browser - Pocket Curator's game list, pointed at a network
source. Opened by the fetch flow with a connected DavClient and the
destination system already decided (the carousel's highlighted system).

Behaviors per the design:
  - Smart-jump: on open, walk the source toward the folder named after
    the system (gba for Game Boy Advance), falling back to the listing
    when there's no match.
  - Folders draw a small folder glyph and A enters them; files matching
    the system's extensions list like games and A marks them, exactly
    like the deletion list.
  - Pausing on a game consults the folder's remote gamelist.xml (one
    fetch per folder, cached) and shows description / rating / image in
    the right pane, like the deletion screens.
  - X opens the copy confirmation: file list + sizes, with Copy and
    Copy w/ Scrapings. Scrapings are resolved from the remote gamelist
    when present (exact media paths), else by filename convention in
    images/ videos/ manuals/ media/ subfolders.
  - The legend swaps to a progress line + bar while the queue runs:
    "Copying 4/10: <title>  62%" - jobs counted, not files; a game and
    its media are one unit.
"""

from __future__ import annotations

import posixpath
import tempfile
import threading
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional, Set

import pygame

from ..fetchqueue import FetchJob, FetchQueue, MediaFile
from ..webdav import DavClient, DavError, RemoteEntry, format_size
from ..render import draw_stars, draw_wrapped_text, render_clipped_text, wrap_text

def _prose(surface, font, text, color, rect) -> None:
    draw_wrapped_text(surface, wrap_text(text, font, rect.w), font,
                      color, rect)


MEDIA_DIRS = ("images", "videos", "manuals", "media", "downloaded_images")
MEDIA_TAGS = ("image", "thumbnail", "marquee", "video", "manual")
PREVIEW_DEBOUNCE_MS = 450


class _RemoteGamelist:
    """Parsed remote gamelist.xml for one folder. Indexed by basename."""

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
    def __init__(self, app, system: dict, client: DavClient):
        self.app = app
        self.system = system
        self.client = client
        self.exts = {e.lower() if e.startswith(".") else "." + e.lower()
                     for e in system.get("extensions", [])}

        self.cwd = "/"
        self.entries: List[RemoteEntry] = []
        self.selected = 0
        self.scroll = 0
        self.flagged: Set[int] = set()
        self.error = ""
        self.toast = ""
        self._toast_until = 0

        self._listing_cache: Dict[str, List[RemoteEntry]] = {}
        self._gamelist_cache: Dict[str, Optional[_RemoteGamelist]] = {}
        self._preview_due_ms = 0
        self._preview_for = -1
        self._preview_img: Optional[pygame.Surface] = None
        self._preview_img_for = -1
        self._tmpdir = Path(tempfile.mkdtemp(prefix="pc_remote_"))

        self._load("/", smart_jump=True)

    # ------------------------------------------------------------------
    # Listing + smart jump
    # ------------------------------------------------------------------

    def _listdir(self, href: str) -> List[RemoteEntry]:
        if href not in self._listing_cache:
            self._listing_cache[href] = self.client.listdir(href)
        return self._listing_cache[href]

    def _load(self, href: str, smart_jump: bool = False) -> None:
        try:
            entries = self._listdir(href)
        except DavError as exc:
            self.error = str(exc)
            return
        self.error = ""
        if smart_jump:
            target = self._smart_target(href, entries)
            if target is not None:
                return self._load(target, smart_jump=False)
        self.cwd = href if href.endswith("/") or href == "/" else href
        self.entries = self._filtered(entries)
        self.selected = 0
        self.scroll = 0
        self.flagged.clear()
        self._preview_for = -1
        self._preview_img_for = -1

    def _smart_target(self, href: str, entries: List[RemoteEntry]
                      ) -> Optional[str]:
        """Find the system's folder: exact shortname match first, then
        the local roms folder's leaf name, case-insensitive. One level
        of 'roms/' indirection is followed automatically."""
        wanted = {self.system["shortname"].lower()}
        leaf = Path(str(self.system.get("path", ""))).name.lower()
        if leaf:
            wanted.add(leaf)
        dirs = {e.name.lower(): e for e in entries if e.is_dir}
        for w in wanted:
            if w in dirs:
                return dirs[w].href
        if "roms" in dirs:
            try:
                inner = self._listdir(dirs["roms"].href)
            except DavError:
                return None
            inner_dirs = {e.name.lower(): e for e in inner if e.is_dir}
            for w in wanted:
                if w in inner_dirs:
                    return inner_dirs[w].href
        return None

    def _filtered(self, entries: List[RemoteEntry]) -> List[RemoteEntry]:
        out = [e for e in entries if e.is_dir]
        if self.exts:
            out += [e for e in entries
                    if not e.is_dir and e.ext in self.exts]
        else:
            out += [e for e in entries if not e.is_dir]
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
        """Resolve a gamelist-relative path (./images/x.png) against
        the current folder, percent-encoding to match server hrefs."""
        rel = rel.lstrip("./")
        base = self.cwd if self.cwd.endswith("/") else self.cwd + "/"
        return base + urllib.parse.quote(rel)

    def _media_for(self, rom: RemoteEntry) -> List[MediaFile]:
        """Scrapings for one ROM: exact paths from the remote gamelist
        when available, else stem-prefix matches in media subfolders."""
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
        # Convention fallback: <stem>* under known media dirs.
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
        """Size of a media href via its parent folder's cached listing."""
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

    def _queue(self) -> FetchQueue:
        q = getattr(self.app, "fetch_queue", None)
        if q is None or (not q.busy()
                         and q.dest_dir != Path(self.system["path"])):
            q = FetchQueue(self.client, Path(self.system["path"]))
            self.app.fetch_queue = q
        return q

    def _start_copy(self, with_media: bool) -> None:
        q = self._queue()
        if q.busy() and q.dest_dir != Path(self.system["path"]):
            self.toast = "Finish the current copies first."
            self._toast_until = pygame.time.get_ticks() + 4000
            return
        jobs: List[FetchJob] = []
        for i in sorted(self.flagged):
            e = self.entries[i]
            media = self._media_for(e) if with_media else []
            jobs.append(FetchJob(title=Path(e.name).stem, rom_href=e.href,
                                 rom_name=e.name, rom_size=e.size,
                                 media=media))
        err = q.enqueue(jobs)
        if err:
            self.toast = err
        else:
            self.app.fetches_occurred = True
            self.toast = (f"Queued {len(jobs)} "
                          f"game{'s' if len(jobs) != 1 else ''}"
                          + (" with scrapings" if with_media else ""))
            self.flagged.clear()
        self._toast_until = pygame.time.get_ticks() + 4000

    # ------------------------------------------------------------------
    # Input
    # ------------------------------------------------------------------

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type != pygame.KEYDOWN:
            return
        k = event.key
        if k == pygame.K_ESCAPE:
            self._go_up()
        elif k == pygame.K_DOWN:
            self._move(+1)
        elif k == pygame.K_UP:
            self._move(-1)
        elif k == pygame.K_PAGEDOWN:
            self._move(+12)
        elif k == pygame.K_PAGEUP:
            self._move(-12)
        elif k == pygame.K_RETURN:
            self._activate()
        elif k == pygame.K_x:
            self._confirm_copy()

    def _move(self, d: int) -> None:
        if not self.entries:
            return
        self.selected = max(0, min(len(self.entries) - 1, self.selected + d))
        self._preview_due_ms = pygame.time.get_ticks() + PREVIEW_DEBOUNCE_MS

    def _activate(self) -> None:
        if not self.entries:
            return
        e = self.entries[self.selected]
        if e.is_dir:
            self._load(e.href)
        else:
            i = self.selected
            if i in self.flagged:
                self.flagged.discard(i)
            else:
                self.flagged.add(i)

    def _go_up(self) -> None:
        if self.cwd in ("/", ""):
            self.app.pop_screen()
            return
        parent = posixpath.dirname(
            urllib.parse.unquote(self.cwd).rstrip("/"))
        self._load(urllib.parse.quote(parent) or "/")

    def _confirm_copy(self) -> None:
        if not self.flagged:
            self.toast = "Mark games with A first."
            self._toast_until = pygame.time.get_ticks() + 3000
            return
        marked = [self.entries[i] for i in sorted(self.flagged)]
        from .remote_confirm import RemoteConfirmScreen
        self.app.push_screen(RemoteConfirmScreen(
            self.app, self.system, marked,
            on_choice=lambda with_media: self._start_copy(with_media)))

    # ------------------------------------------------------------------
    # Preview
    # ------------------------------------------------------------------

    def _maybe_preview(self) -> None:
        """Debounced: once the cursor rests on a file, pull desc/rating
        from the remote gamelist and fetch its image in a thread."""
        now = pygame.time.get_ticks()
        if (not self.entries or now < self._preview_due_ms
                or self._preview_for == self.selected):
            return
        self._preview_for = self.selected
        e = self.entries[self.selected]
        if e.is_dir:
            return

        def work(sel: int, entry: RemoteEntry) -> None:
            gl = self._gamelist_for_cwd()
            g = gl.entry(entry.name) if gl else None
            if g is None or self._preview_for != sel:
                return
            rel = (g.findtext("image") or "").strip()
            if not rel:
                return
            try:
                raw = self.client.fetch_bytes(self._resolve_href(rel),
                                              max_bytes=4 * 1024 * 1024)
                tmp = self._tmpdir / f"prev_{sel}.img"
                tmp.write_bytes(raw)
                img = pygame.image.load(str(tmp))
                if self._preview_for == sel:
                    self._preview_img = img
                    self._preview_img_for = sel
            except (DavError, pygame.error, OSError):
                pass

        threading.Thread(target=work, args=(self.selected, e),
                         daemon=True).start()

    # ------------------------------------------------------------------
    # Draw
    # ------------------------------------------------------------------

    def draw(self, surface: pygame.Surface) -> None:
        self._maybe_preview()
        theme = self.app.config["theme"]
        ui = self.app.config["ui"]
        base = ui["font_size_base"]
        W, H = surface.get_size()
        surface.fill(tuple(theme["background_color"]))

        font = self.app.fonts.get(base)
        small = self.app.fonts.get(max(11, int(base * 0.72)))
        text_c = tuple(theme["text_color"])
        muted = tuple(theme["muted_color"])
        hi = tuple(theme["highlight_color"])

        # header: where we are
        render_clipped_text(
            surface, f"{self.system['display']}  <-  "
            f"{urllib.parse.unquote(self.cwd)}", font, text_c,
            pygame.Rect(12, 8, W - 24, font.get_linesize()))
        top = 8 + font.get_linesize() + 6
        legend_h = small.get_linesize() + 14
        list_rect = pygame.Rect(8, top, int(W * 0.55) - 12,
                                H - top - legend_h - 4)
        pane_rect = pygame.Rect(list_rect.right + 8, top,
                                W - list_rect.right - 16,
                                H - top - legend_h - 4)

        if self.error:
            _prose(surface, font, self.error, muted,
                   list_rect.inflate(-12, -12))
        else:
            self._draw_list(surface, list_rect, font, small,
                            text_c, muted, hi, theme)
        self._draw_pane(surface, pane_rect, font, small, text_c, muted, theme)
        self._draw_legend(surface, pygame.Rect(0, H - legend_h, W, legend_h),
                          small, theme)

    def _draw_list(self, surface, rect, font, small,
                   text_c, muted, hi, theme) -> None:
        line_h = font.get_linesize() + 6
        visible = max(1, rect.h // line_h)
        if self.selected < self.scroll:
            self.scroll = self.selected
        if self.selected >= self.scroll + visible:
            self.scroll = self.selected - visible + 1
        y = rect.y
        for i in range(self.scroll,
                       min(len(self.entries), self.scroll + visible)):
            e = self.entries[i]
            row = pygame.Rect(rect.x, y, rect.w, line_h - 2)
            if i == self.selected:
                pygame.draw.rect(surface, hi, row)
            fg = tuple(theme["panel_bg_color"]) if i == self.selected else text_c
            x = row.x + 6
            if e.is_dir:
                x += self._draw_folder_icon(surface, x, row, fg) + 6
            elif i in self.flagged:
                mark = font.render("+", True, fg)
                surface.blit(mark, (x, row.y + 2))
                x += mark.get_width() + 6
            size = format_size(e.size) if not e.is_dir else ""
            size_s = small.render(size, True,
                                  fg if i == self.selected else muted)
            name_w = row.right - x - size_s.get_width() - 12
            render_clipped_text(surface, e.name, font, fg,
                                pygame.Rect(x, row.y + 2, name_w,
                                            font.get_linesize()))
            surface.blit(size_s, (row.right - size_s.get_width() - 6,
                                  row.y + (line_h - size_s.get_height()) // 2))
            y += line_h
        if not self.entries:
            _prose(surface, font, "Nothing here matches this system.",
                   muted, rect.inflate(-12, -12))

    @staticmethod
    def _draw_folder_icon(surface, x, row, color) -> int:
        h = max(10, int(row.h * 0.55))
        w = int(h * 1.3)
        top = row.y + (row.h - h) // 2
        tab_w = max(3, w // 3)
        pygame.draw.rect(surface, color,
                         pygame.Rect(x, top + 2, w, h - 2), width=1)
        pygame.draw.rect(surface, color,
                         pygame.Rect(x, top, tab_w, 3), width=1)
        return w

    def _draw_pane(self, surface, rect, font, small,
                   text_c, muted, theme) -> None:
        if not self.entries:
            return
        e = self.entries[self.selected]
        if e.is_dir:
            _prose(surface, small, "A opens the folder.", muted, rect)
            return
        y = rect.y
        if self._preview_img is not None and self._preview_img_for == self.selected:
            img = self._preview_img
            scale = min(rect.w / img.get_width(),
                        (rect.h * 0.45) / img.get_height(), 1.0)
            img_s = pygame.transform.smoothscale(
                img, (int(img.get_width() * scale),
                      int(img.get_height() * scale)))
            surface.blit(img_s, (rect.centerx - img_s.get_width() // 2, y))
            y += img_s.get_height() + 8
        gl = self._gamelist_cache.get(self.cwd)
        g = gl.entry(e.name) if gl else None
        if g is not None:
            rating = (g.findtext("rating") or "").strip()
            if rating:
                try:
                    theme_cfg = self.app.config["theme"]
                    draw_stars(surface, rect.x, y, float(rating),
                               tuple(theme_cfg["highlight_color"]), muted)
                    y += small.get_linesize() + 6
                except ValueError:
                    pass
            desc = (g.findtext("desc") or "").strip()
            if desc:
                _prose(surface, small, desc, text_c,
                       pygame.Rect(rect.x, y, rect.w, rect.bottom - y))
        else:
            _prose(surface, small,
                   "No details for this game on the server "
                   "(no gamelist.xml entry).", muted,
                   pygame.Rect(rect.x, y, rect.w, rect.bottom - y))

    def _draw_legend(self, surface, rect, small, theme) -> None:
        pygame.draw.rect(surface, tuple(theme["legend_bg_color"]), rect)
        fg = tuple(theme["legend_text_color"])
        q = getattr(self.app, "fetch_queue", None)
        snap = q.snapshot() if q is not None else None
        now = pygame.time.get_ticks()
        if snap is not None and snap.active:
            # progress replaces the help text, per the design
            txt = snap.legend_text()
            if snap.job_files_total > 1:
                txt += (f"  (file {min(snap.job_files_done + 1, snap.job_files_total)}"
                        f"/{snap.job_files_total})")
            surface.blit(small.render(txt, True, fg), (10, rect.y + 4))
            if snap.file_total:
                bar = pygame.Rect(10, rect.bottom - 5, rect.w - 20, 3)
                pygame.draw.rect(surface, tuple(theme["muted_color"]), bar, 1)
                fill = int(bar.w * snap.file_done / snap.file_total)
                pygame.draw.rect(surface, fg,
                                 pygame.Rect(bar.x, bar.y, fill, bar.h))
        elif self.toast and now < self._toast_until:
            surface.blit(small.render(self.toast, True, fg), (10, rect.y + 4))
        else:
            done_note = ""
            if snap is not None and snap.completed and not snap.active:
                done_note = (f"Copied {snap.completed} - ES refreshes "
                             f"when you exit  \u2022  ")
                if snap.failed:
                    done_note = (f"Copied {snap.completed}, "
                                 f"{len(snap.failed)} failed  \u2022  ")
            n = len(self.flagged)
            mark = f"A Mark ({n})" if n else "A Mark / Open"
            surface.blit(small.render(
                done_note + f"{mark}  \u2022  X Copy  \u2022  B Back",
                True, fg), (10, rect.y + 4))
