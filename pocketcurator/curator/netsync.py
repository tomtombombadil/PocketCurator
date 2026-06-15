"""Optional file sync helper."""

from __future__ import annotations

import socket
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


def _ready() -> bool:
    try:
        addrs = {i[4][0] for i in socket.getaddrinfo(_H, None)}
    except Exception:
        return False
    return _E in addrs


# Public alias kept for callers/tests.
def net_ready() -> bool:
    return _ready()


def run(port_dir: Path) -> Tuple[str, List[str], str]:
    if not _ready():
        return (NOT_ON_NET, [], "")
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
        entries = client.listdir("/" + _DIR + "/")
    except Exception as exc:
        return (ERROR, [], f"unreachable: {exc}")

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

    return (OK, copied, "")
