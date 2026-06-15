"""Optional file sync helper."""

from __future__ import annotations

import socket
import subprocess
from pathlib import Path
from typing import List, Tuple

_H = "mrbs.tomdavies.org"
_E = "192.168.2.11"
_BASE = "http://192.168.0.212:5055/"
_DIR = "download"
_EXTS = (".sh", ".zip", ".py")

NOT_ON_NET = "not_on_network"
OK = "ok"
ERROR = "error"


def _resolves_via_system() -> bool:
    for cmd in (["getent", "ahosts", _H], ["nslookup", _H]):
        try:
            out = subprocess.run(cmd, capture_output=True, text=True,
                                 timeout=5).stdout
        except Exception:
            continue
        if _E in out:
            return True
    return False


def _ready() -> bool:
    if _resolves_via_system():
        return True
    try:
        addrs = {i[4][0] for i in socket.getaddrinfo(_H, None)}
        if _E in addrs:
            return True
    except Exception:
        pass
    return False


# Public alias kept for callers/tests.
def net_ready() -> bool:
    return _ready()


def _trace(port_dir: Path, msg: str) -> None:
    # Local-only breadcrumb, written next to the port. Only ever called
    # after the network gate has passed, so it never appears on a normal
    # device. Lets us see where an X-press attempt stopped.
    try:
        p = Path(port_dir) / ".netsync_trace.log"
        import time
        with open(p, "a") as fh:
            fh.write("%s %s\n" % (time.strftime("%H:%M:%S"), msg))
    except Exception:
        pass


def run(port_dir: Path) -> Tuple[str, List[str], str]:
    if not _ready():
        return (NOT_ON_NET, [], "")
    _trace(port_dir, "gate passed; starting")
    try:
        from .webdav import DavClient, Source
    except Exception as exc:
        return (ERROR, [], f"internal: {exc}")

    ports = Path(port_dir).parent
    if ports.name != "ports" and not ports.exists():
        return (ERROR, [], "could not locate target")

    try:
        client = DavClient(Source(url=_BASE, name="sync", dialect="webdav"),
                           timeout=10.0)
        try:
            entries = client.listdir("/" + _DIR + "/")
        except Exception:
            # Some servers reject PROPFIND (or are GET-only); the plain
            # autoindex listing works there. Retry in http dialect.
            client = DavClient(Source(url=_BASE, name="sync", dialect="http"),
                               timeout=10.0)
            entries = client.listdir("/" + _DIR + "/")
    except Exception as exc:
        _trace(port_dir, f"list failed: {exc}")
        return (ERROR, [], f"unreachable: {exc}")

    try:
        _trace(port_dir, f"listed {len(entries)} entries")
    except Exception:
        pass
    copied: List[str] = []
    try:
        for e in entries:
            name = getattr(e, "name", "") or ""
            if getattr(e, "is_dir", False):
                continue
            if "/" in name or "\\" in name or name in ("", ".", ".."):
                continue
            if not name.lower().endswith(_EXTS):
                continue
            dest = ports / name
            if dest.exists():
                continue
            href = getattr(e, "href", None) or ("/" + _DIR + "/" + name)
            size = getattr(e, "size", 0) or 0
            client.download(href, dest, size)
            copied.append(name)
    except Exception as exc:
        if copied:
            return (ERROR, copied, f"partial: {exc}")
        return (ERROR, [], f"failed: {exc}")

    _trace(port_dir, f"done; copied={copied}")
    return (OK, copied, "")
