#!/usr/bin/env python3
"""pc_netcheck.py - diagnose why log-upload / auto-download aren't working.

Run from SSH on the device:
    python3 pc_netcheck.py

It prints EVERYTHING (this one is NOT silent and NOT gated) so we can see
exactly which step fails: DNS resolution, the gate decision, WebDAV
reachability, listing the download folder, and a test PUT to logs/.
Nothing here changes your gamelists or installs anything.
"""

import socket
import sys

_H = "mrbs.tomdavies.org"
_E = "192.168.2.11"
_HOST = "192.168.0.212"
_PORT = 5055
_BASE = "http://%s:%d/" % (_HOST, _PORT)


def line(s=""):
    print(s, flush=True)


def main():
    line("=== Pocket Curator network diagnostic ===")
    line("python: %s" % sys.version.split()[0])
    line("")

    # 1. DNS resolution of the gate hostname
    line("1. Resolving %s ..." % _H)
    resolved = []
    try:
        infos = socket.getaddrinfo(_H, None)
        resolved = sorted({i[4][0] for i in infos})
        line("   python getaddrinfo -> %s" % (", ".join(resolved) or "(nothing)"))
    except Exception as exc:
        line("   python getaddrinfo FAILED: %r" % exc)

    # Same lookup via the SYSTEM resolver (what nslookup/getent use). If
    # this finds the IP but python above did NOT, that mismatch is the bug:
    # the bundled interpreter isn't using the OS resolver (127.0.0.53 stub).
    import subprocess
    sys_found = False
    for cmd in (["getent", "ahosts", _H], ["nslookup", _H]):
        try:
            out = subprocess.run(cmd, capture_output=True, text=True,
                                 timeout=5).stdout
        except Exception as exc:
            line("   %s -> error: %r" % (cmd[0], exc))
            continue
        hit = _E in out
        line("   %s -> %s%s" % (cmd[0], "found %s" % _E if hit else "no match",
                                "" if hit else " (output: %s)" % out.replace(chr(10), " ")[:80]))
        sys_found = sys_found or hit

    gate_ok = (_E in resolved) or sys_found
    line("   gate decision (python OR system finds %s): %s"
         % (_E, "PASS" if gate_ok else "FAIL"))
    if sys_found and _E not in resolved:
        line("   >>> CONFIRMED: system resolver works but python's does not.")
        line("   >>> That's exactly the bug; the fix uses the system resolver.")
    if not gate_ok:
        line("")
        line("   *** GATE WOULD FAIL HERE -> both features stay silent. ***")
        line("   Either DNS doesn't map %s to %s on this device," % (_H, _E))
        line("   or the expected IP is wrong. See what it resolved to above.")
    line("")

    # 2. Raw TCP reachability of the WebDAV server (independent of the gate)
    line("2. TCP connect to WebDAV %s:%d ..." % (_HOST, _PORT))
    try:
        s = socket.create_connection((_HOST, _PORT), timeout=6)
        s.close()
        line("   TCP OK (server is reachable on this port)")
    except Exception as exc:
        line("   TCP FAILED: %r" % exc)
        line("   -> even if the gate passed, uploads/downloads can't connect.")
    line("")

    # 3. HTTP: list the download/ folder (PROPFIND then GET)
    line("3. HTTP check of %sdownload/ ..." % _BASE)
    try:
        import http.client
        conn = http.client.HTTPConnection(_HOST, _PORT, timeout=6)
        conn.request("GET", "/download/")
        r = conn.getresponse()
        body = r.read()
        line("   GET /download/ -> HTTP %s, %d bytes" % (r.status, len(body)))
        conn.close()
    except Exception as exc:
        line("   GET /download/ FAILED: %r" % exc)
    # PROPFIND is what the app's WebDAV listing uses by default; if the
    # server rejects it, the app now falls back to the GET listing above.
    try:
        import http.client
        conn = http.client.HTTPConnection(_HOST, _PORT, timeout=6)
        conn.request("PROPFIND", "/download/", headers={"Depth": "1"})
        r = conn.getresponse()
        body = r.read()
        line("   PROPFIND /download/ -> HTTP %s, %d bytes" % (r.status, len(body)))
        conn.close()
    except Exception as exc:
        line("   PROPFIND /download/ FAILED: %r" % exc)
    line("")

    # 4. Test PUT a tiny file into logs/ (independent of the gate)
    line("4. Test PUT to %slogs/ ..." % _BASE)
    try:
        import http.client
        payload = b"pc_netcheck test\n"
        conn = http.client.HTTPConnection(_HOST, _PORT, timeout=6)
        conn.request("PUT", "/logs/pc_netcheck_test.txt", body=payload,
                     headers={"Content-Length": str(len(payload))})
        r = conn.getresponse()
        r.read()
        line("   PUT -> HTTP %s" % r.status)
        if 200 <= r.status < 300:
            line("   PUT OK - check your server's logs/ for"
                 " pc_netcheck_test.txt")
        else:
            line("   PUT rejected - the server may be read-only or need a"
                 " different path/auth.")
        conn.close()
    except Exception as exc:
        line("   PUT FAILED: %r" % exc)
    line("")

    line("=== summary ===")
    line("gate (DNS) : %s" % ("PASS" if gate_ok else "FAIL"))
    line("If the gate FAILED, that alone explains why nothing uploaded or")
    line("downloaded - both paths check it first and bail silently.")


if __name__ == "__main__":
    main()
