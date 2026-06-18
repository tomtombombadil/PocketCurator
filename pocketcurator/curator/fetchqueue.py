"""
The fetch queue: copies marked games (and optionally their scraped
media) from a network source into the local system folder, in the
background, one file at a time.

A "job" is one game: the ROM plus whatever media files travel with it.
The 4/10 counter the UI shows counts JOBS, not files - a game and its
scrapings are one unit of progress, per the design.

Safety properties:
  - every file streams to <name>.part and renames on completion, so a
    cancel or power cut never leaves a half-ROM that ES would list;
  - free space for the whole queue (plus 32 MB headroom) is checked
    before the first byte moves;
  - the worker thread never touches the UI; the UI polls .snapshot().
"""

from __future__ import annotations

import os
import shutil
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from .webdav import DavClient, DavError


@dataclass
class MediaFile:
    href: str
    rel_dest: str      # destination path relative to the system folder
    size: int = 0


@dataclass
class FetchJob:
    title: str         # display name, e.g. "Advance Wars (USA)"
    rom_href: str
    rom_name: str      # destination filename
    rom_size: int = 0
    media: List[MediaFile] = field(default_factory=list)
    gamelist_entry: Optional[str] = None   # source <game> XML, if any
    dest_dir: Optional[Path] = None        # per-job destination system
    merge_overwrite: bool = False          # replace existing gamelist entry

    def total_bytes(self) -> int:
        return self.rom_size + sum(m.size for m in self.media)


@dataclass
class QueueSnapshot:
    active: bool = False
    job_index: int = 0          # 1-based job currently copying
    job_count: int = 0
    job_title: str = ""
    file_done: int = 0          # bytes of the current FILE
    file_total: int = 0
    queue_bytes_done: int = 0   # bytes finished across the WHOLE queue
    queue_bytes_total: int = 0  # bytes of everything ever enqueued
    completed: int = 0
    failed: List[str] = field(default_factory=list)
    error: str = ""
    speed_bps: float = 0.0      # smoothed transfer rate, bytes/sec

    def speed_text(self) -> str:
        """Compact right-justified rate, 1 decimal, KB/s or MB/s.
        Empty when idle or not yet measured."""
        if not self.active or self.speed_bps <= 0:
            return ""
        mbps = self.speed_bps / (1024.0 * 1024.0)
        if mbps >= 1.0:
            return f"{mbps:.1f} MB/s"
        kbps = self.speed_bps / 1024.0
        return f"{kbps:.1f} KB/s"

    def legend_text(self) -> str:
        """One line above the progress bar: the queue position and the
        game's title. A game and its scrapings are one unit; no
        per-file noise."""
        if not self.active:
            return ""
        return (f"Copying {self.job_index}/{self.job_count}: "
                f"{self.job_title}")

    def queue_fraction(self) -> float:
        if self.queue_bytes_total <= 0:
            return 0.0
        return min(1.0, self.queue_bytes_done / self.queue_bytes_total)


class FetchQueue:
    def __init__(self, client: DavClient, dest_dir: Path,
                 on_job_done=None):
        self.client = client
        self.dest_dir = Path(dest_dir)
        self.on_job_done = on_job_done   # callback(job, success), worker thread
        self._jobs: List[FetchJob] = []
        self._lock = threading.Lock()
        self._snap = QueueSnapshot()
        self._thread: Optional[threading.Thread] = None
        self._cancel = False
        # transfer-rate sampling (worker thread only)
        self._spd_last_t: float = 0.0
        self._spd_last_bytes: int = 0
        self._spd_ema: float = 0.0

    # ------------------------------------------------------------------

    def enqueue(self, jobs: List[FetchJob]) -> Optional[str]:
        """Add jobs; start the worker if idle. Returns an error string
        (and queues nothing) when there isn't room for everything
        already queued plus the new jobs."""
        with self._lock:
            # A fresh batch (worker idle, nothing pending) starts the
            # counters over - otherwise the second copy session of the
            # day opens with the bar half full and "72/142" in the
            # legend, which is the previous session leaking through.
            if ((self._thread is None or not self._thread.is_alive())
                    and not self._jobs):
                self._snap = QueueSnapshot()
            # Free-space check, grouped by the filesystem each destination
            # lives on. Jobs can carry their own dest_dir (a different
            # system, and on multi-card devices a different mount, e.g.
            # /roms vs /roms2), so summing everything against one folder
            # could pass a check the target card can't actually satisfy.
            # Group required bytes by st_dev and verify each card has room.
            need_by_dev: dict = {}
            sample_by_dev: dict = {}
            for j in (self._jobs + list(jobs)):
                d = Path(j.dest_dir) if j.dest_dir else self.dest_dir
                try:
                    dev = os.stat(d).st_dev
                except OSError:
                    d = self.dest_dir
                    try:
                        dev = os.stat(d).st_dev
                    except OSError:
                        dev = ("?", str(d))
                need_by_dev[dev] = need_by_dev.get(dev, 0) + j.total_bytes()
                sample_by_dev.setdefault(dev, d)
            for dev, need in need_by_dev.items():
                try:
                    free = shutil.disk_usage(sample_by_dev[dev]).free
                except OSError:
                    continue   # can't measure it; don't block the copy
                if free < need + 32 * 1024 * 1024:
                    return (f"Not enough free space on "
                            f"{sample_by_dev[dev]}: need "
                            f"{need // (1024*1024)} MB, have "
                            f"{free // (1024*1024)} MB.")
            self._jobs.extend(jobs)
            self._snap.job_count += len(jobs)
            self._snap.queue_bytes_total += sum(j.total_bytes()
                                                for j in jobs)
            self._snap.active = True
            if self._thread is None or not self._thread.is_alive():
                self._cancel = False
                self._thread = threading.Thread(target=self._run, daemon=True)
                self._thread.start()
        return None

    def cancel(self) -> None:
        self._cancel = True

    def busy(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def snapshot(self) -> QueueSnapshot:
        with self._lock:
            s = self._snap
            return QueueSnapshot(
                active=s.active, job_index=s.job_index,
                job_count=s.job_count, job_title=s.job_title,
                file_done=s.file_done, file_total=s.file_total,
                queue_bytes_done=s.queue_bytes_done + s.file_done,
                queue_bytes_total=s.queue_bytes_total,
                completed=s.completed, failed=list(s.failed),
                error=s.error, speed_bps=self._spd_ema)

    # ------------------------------------------------------------------

    def _run(self) -> None:
        while True:
            with self._lock:
                if not self._jobs or self._cancel:
                    self._snap.active = False
                    self._spd_ema = 0.0
                    self._spd_last_t = 0.0
                    if self._cancel:
                        self._jobs.clear()
                    return
                job = self._jobs.pop(0)
                self._snap.job_index += 1
                self._snap.job_title = job.title
                self._snap.error = ""
            jdest_log = Path(job.dest_dir) if job.dest_dir else self.dest_dir
            print(f"[fetch] job {self._snap.job_index}/{self._snap.job_count}: "
                  f"'{job.title}' -> {jdest_log}  "
                  f"(rom + {len(job.media)} media file(s))")

            try:
                jdest = Path(job.dest_dir) if job.dest_dir else self.dest_dir
                self._copy_one(job.rom_href,
                               jdest / job.rom_name, job.rom_size)
                for m in job.media:
                    dest = jdest / m.rel_dest
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    self._copy_one(m.href, dest, m.size)
                with self._lock:
                    self._snap.completed += 1
                print(f"[fetch] copied '{job.title}' "
                      f"({1 + len(job.media)} files)")
                if self.on_job_done is not None:
                    try:
                        self.on_job_done(job, True)
                    except Exception as exc:  # noqa: BLE001
                        print(f"[fetch] on_job_done error: {exc}")
            except DavError as exc:
                with self._lock:
                    self._snap.failed.append(job.title)
                    self._snap.error = str(exc)
                print(f"[fetch] FAILED '{job.title}': {exc}")
                if self._cancel:
                    continue

    def _copy_one(self, href: str, dest: Path, size: int) -> None:
        print(f"[fetch]   copy {href}  ->  {dest}  ({size} bytes)")
        def on_progress(done: int, total: int) -> None:
            now = time.monotonic()
            with self._lock:
                self._snap.file_done = done
                self._snap.file_total = total or size
                # Whole-queue cumulative bytes for an even rate estimate
                # across files (avoids a reset-to-zero blip per file).
                cum = self._snap.queue_bytes_done + done
                if self._spd_last_t <= 0:
                    self._spd_last_t = now
                    self._spd_last_bytes = cum
                else:
                    dt = now - self._spd_last_t
                    if dt >= 0.25:   # sample ~4x/sec
                        inst = max(0.0, (cum - self._spd_last_bytes) / dt)
                        # EMA smoothing so the figure doesn't jitter.
                        self._spd_ema = (inst if self._spd_ema <= 0
                                         else 0.65 * self._spd_ema + 0.35 * inst)
                        self._spd_last_t = now
                        self._spd_last_bytes = cum

        with self._lock:
            self._snap.file_done = 0
            self._snap.file_total = size
        self.client.download(href, dest, size,
                             on_progress=on_progress,
                             cancelled=lambda: self._cancel)
        # File finished: fold its bytes into the whole-queue figure.
        with self._lock:
            self._snap.queue_bytes_done += (self._snap.file_total or size)
            self._snap.file_done = 0
            self._snap.file_total = 0
