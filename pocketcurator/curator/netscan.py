"""
Local-network discovery of WebDAV / HTTP file servers.

Strategy: learn our own IPv4 the portable way (UDP "connect" to a
public address - no packet is sent), then TCP-probe every host on the
/24 at the handful of ports file servers actually use. A connect scan
of 254 hosts x 4 ports with a 0.4s timeout and 64 workers completes in
a few seconds on a LAN. Hosts that accept are then asked OPTIONS to
sort genuine WebDAV from plain HTTP.

This finds anything that's listening regardless of how chatty it is -
unlike NetBIOS/mDNS, which only find devices that announce themselves.
AP isolation (guest WiFi) defeats any scan, which is why the UI always
offers manual entry too.
"""

from __future__ import annotations

import http.client
import socket
import threading
from dataclasses import dataclass
from typing import Callable, List, Optional

# Order matters for the per-host dedupe: prefer the dedicated WebDAV
# ports over generic web ports when a host serves several.
PROBE_PORTS = [5005, 5006, 8080, 80]
CONNECT_TIMEOUT = 0.4
VERIFY_TIMEOUT = 2.5
WORKERS = 64


@dataclass
class Found:
    host: str
    port: int
    dialect: str        # "webdav" | "http"

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"


def local_ipv4() -> Optional[str]:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))   # no packet leaves; routing only
            return s.getsockname()[0]
        finally:
            s.close()
    except OSError:
        return None


def scan(progress: Optional[Callable[[int, int], None]] = None,
         cancelled: Optional[Callable[[], bool]] = None) -> List[Found]:
    """Scan the local /24. Returns verified servers, WebDAV first."""
    me = local_ipv4()
    if not me or me.startswith("127."):
        return []
    prefix = me.rsplit(".", 1)[0]
    targets = [(f"{prefix}.{i}", p)
               for i in range(1, 255) for p in PROBE_PORTS]

    open_ports: List[tuple] = []
    lock = threading.Lock()
    idx = {"n": 0}
    total = len(targets)

    def worker():
        while True:
            if cancelled is not None and cancelled():
                return
            with lock:
                if idx["n"] >= total:
                    return
                host, port = targets[idx["n"]]
                idx["n"] += 1
                if progress is not None:
                    progress(idx["n"], total)
            try:
                s = socket.create_connection((host, port), CONNECT_TIMEOUT)
                s.close()
                with lock:
                    open_ports.append((host, port))
            except OSError:
                pass

    threads = [threading.Thread(target=worker, daemon=True)
               for _ in range(WORKERS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Verify what's actually behind each open port; one entry per host,
    # preferring WebDAV and the PROBE_PORTS ordering.
    by_host: dict = {}
    for host, port in sorted(open_ports,
                             key=lambda hp: PROBE_PORTS.index(hp[1])):
        if cancelled is not None and cancelled():
            break
        if host in by_host and by_host[host].dialect == "webdav":
            continue
        dialect = _identify(host, port)
        if dialect is None:
            continue
        cur = by_host.get(host)
        if cur is None or (cur.dialect != "webdav" and dialect == "webdav"):
            by_host[host] = Found(host, port, dialect)

    out = list(by_host.values())
    out.sort(key=lambda f: (f.dialect != "webdav", f.host))
    return out


def _identify(host: str, port: int) -> Optional[str]:
    """OPTIONS the root: a DAV header (or 401, which only a real server
    sends) marks WebDAV; any sane HTTP answer marks plain HTTP."""
    try:
        conn = http.client.HTTPConnection(host, port, timeout=VERIFY_TIMEOUT)
        conn.request("OPTIONS", "/",
                     headers={"User-Agent": "PocketCurator",
                              "Connection": "close"})
        resp = conn.getresponse()
        dav = resp.getheader("DAV")
        allow = resp.getheader("Allow", "")
        resp.read()
        conn.close()
        if dav or "PROPFIND" in allow or resp.status == 401:
            return "webdav"
        if resp.status in (405, 501):
            # Doesn't speak OPTIONS at all (python -m http.server says
            # 501) - that's still a perfectly good plain-HTTP source.
            return "http"
        if resp.status < 500:
            return "http"
    except (OSError, http.client.HTTPException):
        pass
    return None
