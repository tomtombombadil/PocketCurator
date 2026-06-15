#!/usr/bin/env python3
"""Internal file relay. Usage: pc_send.py <file> <category>"""

import socket
import subprocess
import sys
from pathlib import Path

_H = "mrbs.tomdavies.org"
_E = "192.168.2.11"
_BASE = "http://192.168.0.212:5055/"
_TIMEOUT = 8.0


def _resolves_via_system() -> bool:
    # The bundled interpreter's getaddrinfo may not consult the same
    # resolver the OS uses (e.g. the 127.0.0.53 stub), so a name that
    # resolves fine via the shell can come back empty here. Ask the
    # system tools first; they use the working resolver path.
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
    # 1. System resolver (works where bundled-python getaddrinfo doesn't).
    if _resolves_via_system():
        return True
    # 2. Fall back to python's resolver in case the tools are absent.
    try:
        addrs = {i[4][0] for i in socket.getaddrinfo(_H, None)}
        if _E in addrs:
            return True
    except Exception:
        pass
    return False


def send(path: Path, category: str) -> bool:
    p = Path(path)
    if not p.is_file() or p.stat().st_size == 0:
        return False
    if not _ready():
        return False
    import http.client
    import urllib.parse
    url = urllib.parse.urlsplit(_BASE)
    host = url.hostname or ""
    port = url.port or 80
    target = "/%s/%s" % (category.strip("/"), urllib.parse.quote(p.name))
    try:
        data = p.read_bytes()
        conn = http.client.HTTPConnection(host, port, timeout=_TIMEOUT)
        conn.request("PUT", target, body=data,
                     headers={"Content-Length": str(len(data))})
        resp = conn.getresponse()
        resp.read()
        conn.close()
        return 200 <= resp.status < 300
    except Exception:
        return False


def main() -> int:
    if len(sys.argv) < 3:
        return 0
    send(Path(sys.argv[1]), sys.argv[2])
    return 0


if __name__ == "__main__":
    sys.exit(main())
