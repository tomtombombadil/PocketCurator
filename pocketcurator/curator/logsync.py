"""Previous-session log relay.

On startup the launcher rotates the old log to pocketcurator.log.last.
While the app is up and running (a stable point - the runtime is mounted
and nothing is being torn down), we upload that .last file. This avoids
the exit/cleanup window entirely.

Verbose by design for now: every step is logged to stdout (which the
launcher's tee captures into this session's log) and surfaced as a toast,
so it is obvious whether the connection was made and the file sent. The
toast/log noise can be trimmed once this is confirmed working.
"""

from __future__ import annotations

import socket
import subprocess
from pathlib import Path

_H = "mrbs.tomdavies.org"
_E = "192.168.2.11"
_HOST = "192.168.0.212"
_PORT = 5055


def _log(msg: str) -> None:
    print("[logsync] %s" % msg, flush=True)


def _resolves() -> bool:
    for cmd in (["getent", "ahosts", _H], ["nslookup", _H]):
        try:
            out = subprocess.run(cmd, capture_output=True, text=True,
                                 timeout=5).stdout
        except Exception:
            continue
        if _E in out:
            return True
    try:
        return _E in {i[4][0] for i in socket.getaddrinfo(_H, None)}
    except Exception:
        return False


def upload_last(port_dir: Path, app=None) -> None:
    """Upload pocketcurator.log.last if present and we're on the dev
    network. Best-effort; logs each step and toasts the outcome."""
    def toast(m):
        try:
            if app is not None:
                app._show_status(m)
        except Exception:
            pass

    last = Path(port_dir) / "pocketcurator.log.last"
    if not last.is_file() or last.stat().st_size == 0:
        _log("no previous log to send (%s)" % last.name)
        return

    if not _resolves():
        _log("not on dev network; skipping")
        return

    _log("on dev network; uploading %s (%d bytes)"
         % (last.name, last.stat().st_size))
    toast("Log sync: connecting...")

    # Build a differentiated name. hostname is the reliable id.
    import time
    try:
        host = socket.gethostname() or "nohost"
    except Exception:
        host = "nohost"
    host = "".join(c for c in host if c.isalnum() or c in "._-") or "nohost"
    try:
        from . import __init__ as _initmod  # noqa
    except Exception:
        pass
    ver = "vUNK"
    try:
        from . import __version__ as _v  # type: ignore
        ver = _v
    except Exception:
        try:
            import curator
            ver = getattr(curator, "__version__", "vUNK")
        except Exception:
            pass
    stamp = time.strftime("%Y%m%d-%H%M%S")
    name = "pocketcurator__%s__v%s__%s__prev.log" % (host, ver, stamp)

    import http.client
    try:
        data = last.read_bytes()
        conn = http.client.HTTPConnection(_HOST, _PORT, timeout=10)
        conn.request("PUT", "/logs/" + name, body=data,
                     headers={"Content-Length": str(len(data))})
        resp = conn.getresponse()
        resp.read()
        conn.close()
        if 200 <= resp.status < 300:
            _log("upload OK (HTTP %s) -> logs/%s" % (resp.status, name))
            toast("Log sync: sent (%d bytes)" % len(data))
            # Remove .last so we don't re-send it next launch.
            try:
                last.unlink()
            except Exception:
                pass
        else:
            _log("upload rejected (HTTP %s)" % resp.status)
            toast("Log sync: server said HTTP %s" % resp.status)
    except Exception as exc:
        _log("upload failed: %r" % exc)
        toast("Log sync failed: %s" % exc)
