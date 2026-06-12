"""
WebDAV / plain-HTTP client for fetching ROMs from a network source.

Read-only by construction: the only verbs this module can emit are
OPTIONS, PROPFIND, HEAD, and GET. The writing half of WebDAV (PUT,
DELETE, MKCOL, MOVE, COPY, PROPPATCH) is simply not implemented, so no
bug in a UI layer can ever modify the source.

Entirely python stdlib (http.client, ssl, xml.etree, html.parser): no
bundled protocol library, identical behavior on every firmware.

Speaks two dialects through one interface:
  - WebDAV: PROPFIND Depth:1 -> structured XML listing. Preferred.
  - Plain HTTP autoindex (python -m http.server, nginx/Apache
    autoindex): GET -> parse <a href> links. Fallback, detected
    automatically when a server doesn't answer PROPFIND.

HTTPS with self-signed certificates (every NAS out of the box) is
accepted: LAN ROM transfer doesn't justify failing closed on cert
verification, and the alternative every WebDAV client app picks is a
"trust this server" prompt that users click through anyway.
"""

from __future__ import annotations

import html.parser
import http.client
import posixpath
import time
import urllib.parse

# ssl is intentionally NOT imported at module level: the bundled Pyxel
# runtime on dArkOS/ROCKNIX lacks libssl.so.1.1, so `import ssl` raises
# ImportError there - which, when done at import time, crashed the whole
# app the moment Y was pressed (v0.63.0 on R36S/RG35xxSP). HTTPS is
# optional for LAN fetching; we import ssl only when an https:// URL
# actually needs it and degrade with a clear message when it's absent.
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

DAV_NS = "{DAV:}"
CHUNK = 1024 * 256


class DavError(Exception):
    """All failures surface as this, with a human-usable message."""


class DavAuthRequired(DavError):
    """Server answered 401: credentials needed (or wrong)."""


@dataclass
class RemoteEntry:
    name: str               # display name, percent-decoded
    href: str               # absolute path on the server (still encoded)
    is_dir: bool
    size: int = 0           # bytes; 0/unknown for dirs
    mtime: str = ""         # display string, best effort

    @property
    def ext(self) -> str:
        return Path(self.name).suffix.lower()


@dataclass
class Source:
    """A saved network source. Password intentionally not persisted to
    settings.json - it's remembered for the session only."""
    url: str                          # e.g. http://192.168.1.20:5005/
    name: str = ""
    username: str = ""
    password: str = field(default="", repr=False)
    dialect: str = ""                 # "webdav" | "http" | "" (unknown)

    def display(self) -> str:
        return self.name or self.url


class DavClient:
    def __init__(self, source: Source, timeout: float = 15.0):
        self.source = source
        self.timeout = timeout
        u = urllib.parse.urlsplit(source.url if "://" in source.url
                                  else "http://" + source.url)
        self._https = u.scheme == "https"
        self._host = u.hostname or ""
        self._port = u.port or (443 if self._https else 80)
        self._base = u.path.rstrip("/")  # may be "" or "/dav" etc.
        if not self._host:
            raise DavError(f"'{source.url}' is not a valid server address.")

    # ------------------------------------------------------------------
    # Connection plumbing
    # ------------------------------------------------------------------

    def _conn(self) -> http.client.HTTPConnection:
        if self._https:
            try:
                import ssl
            except ImportError:
                raise DavError(
                    "HTTPS isn't available on this firmware's runtime - "
                    "use an http:// address instead.")
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE   # see module docstring
            return http.client.HTTPSConnection(
                self._host, self._port, timeout=self.timeout, context=ctx)
        return http.client.HTTPConnection(
            self._host, self._port, timeout=self.timeout)

    def _headers(self, extra: Optional[dict] = None) -> dict:
        h = {"User-Agent": "PocketCurator", "Connection": "close"}
        if self.source.username or self.source.password:
            import base64
            cred = f"{self.source.username}:{self.source.password}"
            h["Authorization"] = "Basic " + base64.b64encode(
                cred.encode("utf-8")).decode("ascii")
        if extra:
            h.update(extra)
        return h

    def _url_path(self, path: str) -> str:
        """Join the base path with a server-side path and quote it."""
        if path.startswith("/"):
            joined = path  # hrefs from PROPFIND are already absolute
        else:
            joined = posixpath.join(self._base or "/", path)
        # hrefs arrive encoded; manual paths arrive raw. Decode-then-
        # encode normalizes both without double-encoding.
        return urllib.parse.quote(urllib.parse.unquote(joined))

    def _request(self, method: str, path: str, body: Optional[bytes] = None,
                 extra_headers: Optional[dict] = None):
        # One automatic retry: handhelds drop a beat of WiFi or hit a
        # half-open socket constantly, and a single transient failure
        # was surfacing as "server isn't answering" while the server
        # was plainly up. A fresh connection on the second try clears
        # both stale-socket and momentary-blip cases.
        last_exc = None
        for attempt in (1, 2):
            conn = self._conn()
            try:
                conn.request(method, self._url_path(path), body=body,
                             headers=self._headers(extra_headers))
                resp = conn.getresponse()
            except (OSError, http.client.HTTPException) as exc:
                conn.close()
                last_exc = exc
                if attempt == 1:
                    import time as _t
                    _t.sleep(0.4)
                    continue
                raise DavError(self._excuse(exc)) from exc
            if resp.status == 401:
                conn.close()
                raise DavAuthRequired("This server requires a login.")
            return conn, resp
        raise DavError(self._excuse(last_exc))   # unreachable

    def _excuse(self, exc: Exception) -> str:
        s = str(exc)
        if "timed out" in s:
            return "The server didn't answer in time. Right address?"
        if "Connection refused" in s:
            return "Nothing is listening at that address and port."
        if "No route to host" in s or "unreachable" in s.lower():
            return "Can't reach that address. Is WiFi connected?"
        if "CERTIFICATE" in s.upper() or "SSL" in s.upper():
            return "Secure connection failed. Try http:// instead."
        return f"Connection failed: {s}"

    # ------------------------------------------------------------------
    # Listing
    # ------------------------------------------------------------------

    def listdir(self, path: str = "/") -> List[RemoteEntry]:
        """List a directory, auto-detecting the dialect on first use."""
        if self.source.dialect == "http":
            return self._list_autoindex(path)
        try:
            entries = self._list_propfind(path)
            self.source.dialect = "webdav"
            return entries
        except DavAuthRequired:
            raise
        except DavError:
            if self.source.dialect == "webdav":
                raise
            # Unknown dialect and PROPFIND failed: try autoindex once.
            entries = self._list_autoindex(path)
            self.source.dialect = "http"
            return entries

    def _list_propfind(self, path: str) -> List[RemoteEntry]:
        body = (b'<?xml version="1.0" encoding="utf-8"?>'
                b'<d:propfind xmlns:d="DAV:"><d:prop>'
                b'<d:displayname/><d:resourcetype/>'
                b'<d:getcontentlength/><d:getlastmodified/>'
                b'</d:prop></d:propfind>')
        conn, resp = self._request(
            "PROPFIND", path, body=body,
            extra_headers={"Depth": "1",
                           "Content-Type": "application/xml"})
        try:
            if resp.status not in (207,):
                raise DavError(
                    f"Server didn't answer the folder listing "
                    f"(HTTP {resp.status}).")
            data = resp.read()
        finally:
            conn.close()

        try:
            root = ET.fromstring(data)
        except ET.ParseError as exc:
            raise DavError("Server sent an unreadable listing.") from exc

        req_path = urllib.parse.unquote(self._url_path(path)).rstrip("/")
        out: List[RemoteEntry] = []
        for resp_el in root.iter(DAV_NS + "response"):
            href_el = resp_el.find(DAV_NS + "href")
            if href_el is None or not href_el.text:
                continue
            href = urllib.parse.urlsplit(href_el.text.strip()).path
            decoded = urllib.parse.unquote(href).rstrip("/")
            if decoded == req_path:
                continue  # the folder itself
            is_dir = resp_el.find(
                f".//{DAV_NS}resourcetype/{DAV_NS}collection") is not None
            size_el = resp_el.find(f".//{DAV_NS}getcontentlength")
            mtime_el = resp_el.find(f".//{DAV_NS}getlastmodified")
            try:
                size = int(size_el.text) if size_el is not None and size_el.text else 0
            except ValueError:
                size = 0
            out.append(RemoteEntry(
                name=posixpath.basename(decoded),
                href=href if href.startswith("/") else "/" + href,
                is_dir=is_dir,
                size=size,
                mtime=(mtime_el.text or "") if mtime_el is not None else ""))
        out.sort(key=lambda e: (not e.is_dir, e.name.lower()))
        return out

    def _list_autoindex(self, path: str) -> List[RemoteEntry]:
        conn, resp = self._request("GET", path if path.endswith("/")
                                   else path + "/")
        try:
            if resp.status != 200:
                raise DavError(f"Folder listing failed (HTTP {resp.status}).")
            ctype = resp.getheader("Content-Type", "")
            if "html" not in ctype:
                raise DavError("That address serves files, not a "
                               "browsable folder listing.")
            data = resp.read(4 * 1024 * 1024).decode("utf-8", "replace")
        finally:
            conn.close()

        base = self._url_path(path if path.endswith("/") else path + "/")
        parser = _LinkParser()
        parser.feed(data)
        out: List[RemoteEntry] = []
        seen = set()
        for href in parser.links:
            href = href.split("?", 1)[0].split("#", 1)[0]
            if not href or href.startswith(("..", "/..")):
                continue
            absolute = urllib.parse.urljoin(base, href)
            if urllib.parse.urlsplit(absolute).netloc:
                absolute = urllib.parse.urlsplit(absolute).path
            # only descendants of the listed folder, one level deep
            if not absolute.startswith(base) or absolute == base:
                continue
            rel = absolute[len(base):]
            if "/" in rel.rstrip("/"):
                continue
            if absolute in seen:
                continue
            seen.add(absolute)
            is_dir = absolute.endswith("/")
            name = urllib.parse.unquote(rel.rstrip("/"))
            out.append(RemoteEntry(name=name,
                                   href=urllib.parse.unquote(absolute).rstrip("/")
                                   if False else absolute.rstrip("/"),
                                   is_dir=is_dir))
        out.sort(key=lambda e: (not e.is_dir, e.name.lower()))
        return out

    # ------------------------------------------------------------------
    # Fetching
    # ------------------------------------------------------------------

    def fetch_bytes(self, path: str, max_bytes: int = 8 * 1024 * 1024) -> bytes:
        """Small-file GET (remote gamelist.xml, preview images)."""
        conn, resp = self._request("GET", path)
        try:
            if resp.status != 200:
                raise DavError(f"Download failed (HTTP {resp.status}).")
            return resp.read(max_bytes)
        finally:
            conn.close()

    def download(self, path: str, dest: Path,
                 expected_size: int = 0,
                 on_progress: Optional[Callable[[int, int], None]] = None,
                 cancelled: Optional[Callable[[], bool]] = None) -> None:
        """Stream a file to dest via a .part neighbor, resuming a
        previous partial transfer when the server honors Range."""
        part = dest.with_name(dest.name + ".part")
        offset = part.stat().st_size if part.is_file() else 0

        headers = {}
        if offset > 0:
            headers["Range"] = f"bytes={offset}-"
        conn, resp = self._request("GET", path, extra_headers=headers)
        try:
            if resp.status == 200:
                offset = 0          # server ignored Range; start over
                mode = "wb"
            elif resp.status == 206:
                mode = "ab"
            else:
                raise DavError(f"Download failed (HTTP {resp.status}).")

            total = expected_size
            clen = resp.getheader("Content-Length")
            if clen and clen.isdigit():
                total = offset + int(clen)

            done = offset
            with open(part, mode) as f:
                while True:
                    if cancelled is not None and cancelled():
                        raise DavError("Cancelled.")
                    chunk = resp.read(CHUNK)
                    if not chunk:
                        break
                    f.write(chunk)
                    done += len(chunk)
                    if on_progress is not None:
                        on_progress(done, total)
            if total and done < total:
                raise DavError(
                    "The connection dropped before the file finished. "
                    "Run the copy again to resume it.")
        except Exception:
            conn.close()
            raise
        conn.close()
        part.replace(dest)

    # ------------------------------------------------------------------

    def probe(self) -> str:
        """Connect + identify dialect. Returns 'webdav' or 'http'.
        Raises DavAuthRequired / DavError otherwise."""
        self.listdir("/")
        return self.source.dialect or "http"


class _LinkParser(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.links: List[str] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "a":
            return
        for k, v in attrs:
            if k.lower() == "href" and v:
                self.links.append(v)


def format_size(n: int) -> str:
    if n <= 0:
        return ""
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024.0
    return ""
