"""Pages and scripts served compressed, with validators, so a repeat visit is cheap.

These files used to be sent whole on every page load (some with ``no-store``).
Here each is gzipped once, cached in memory until the file changes, and sent
with an ETag. ``no-cache`` still makes the browser ask every time, so an edited
file is never stale; an unchanged file costs a tiny 304 reply instead of the
whole body.
"""
import gzip
import os
import threading

from starlette.datastructures import Headers
from starlette.responses import FileResponse, Response

from server.compression import accepts_gzip

MIN_GZIP_BYTES = 1024
_LOCK = threading.Lock()
_CACHE: dict = {}  # path -> (mtime_ns, size, raw, gzipped, etag)


def _load(path):
    stat = os.stat(path)
    key = (stat.st_mtime_ns, stat.st_size)
    with _LOCK:
        hit = _CACHE.get(path)
        if hit and hit[:2] == key:
            return hit
    with open(path, "rb") as handle:
        raw = handle.read()
    packed = gzip.compress(raw, compresslevel=9, mtime=0) if len(raw) >= MIN_GZIP_BYTES else None
    if packed is not None and len(packed) >= len(raw):
        packed = None
    entry = (key[0], key[1], raw, packed, f'"{key[0]:x}-{key[1]:x}"')
    with _LOCK:
        _CACHE[path] = entry
    return entry


def _matches(header, etag):
    for candidate in (header or "").split(","):
        candidate = candidate.strip()
        if candidate == "*" or candidate.removeprefix("W/") == etag:
            return True
    return False


class TextFileResponse(FileResponse):
    """A FileResponse for HTML, JS and CSS: gzip, ETag and 304 handling."""

    def __init__(self, path, media_type=None, headers=None, **kwargs):
        super().__init__(path, media_type=media_type, headers=headers, **kwargs)
        self._extra = {k: v for k, v in (headers or {}).items()}

    async def __call__(self, scope, receive, send):
        try:
            _, _, raw, packed, etag = _load(self.path)
        except OSError:
            # Missing or unreadable: let FileResponse produce its usual error.
            return await super().__call__(scope, receive, send)
        request = Headers(scope=scope)
        headers = {"Cache-Control": "no-cache", **self._extra, "ETag": etag}
        vary = [v.strip() for v in headers.get("Vary", "").split(",") if v.strip()]
        headers["Vary"] = ", ".join(vary + ([] if "Accept-Encoding" in vary else ["Accept-Encoding"]))
        if _matches(request.get("if-none-match"), etag):
            return await Response(status_code=304, headers=headers)(scope, receive, send)
        body = raw
        if packed is not None and accepts_gzip(request.get("accept-encoding", "")):
            body = packed
            headers["Content-Encoding"] = "gzip"
        await Response(body, media_type=self.media_type, headers=headers)(scope, receive, send)
