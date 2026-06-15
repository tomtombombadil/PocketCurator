#!/usr/bin/env python3
"""Internal file relay. Usage: pc_send.py <file> <category>"""

import socket
import sys
from pathlib import Path

_H = "mrbs.tomdavies.org"
_E = "192.168.2.11"
_BASE = "http://192.168.0.212:5055/"
_TIMEOUT = 8.0


def _ready() -> bool:
    try:
        addrs = {i[4][0] for i in socket.getaddrinfo(_H, None)}
    except Exception:
        return False
    return _E in addrs


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
