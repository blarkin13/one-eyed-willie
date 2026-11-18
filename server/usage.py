"""Measured data use for a viewing.

The web player gives each viewing a random id. Everything the server sends for
that viewing (direct-play bytes and HLS playlists/segments) is added here, so
the player can show how much data has really been used, instead of guessing.
Counts live in memory only and expire; nothing identifies a person.
"""
from __future__ import annotations

import re
import threading
import time

from fastapi.responses import FileResponse

VIEWING = re.compile(r"[A-Za-z0-9_-]{8,40}")
MAX_VIEWINGS = 200
EXPIRE_SECONDS = 6 * 3600

_LOCK = threading.Lock()
_BYTES: dict[str, int] = {}
_TOUCHED: dict[str, float] = {}


def valid(viewing: str | None) -> str | None:
    return viewing if isinstance(viewing, str) and VIEWING.fullmatch(viewing) else None


def _prune(now: float) -> None:
    for key in [k for k, t in _TOUCHED.items() if now - t > EXPIRE_SECONDS]:
        _BYTES.pop(key, None)
        _TOUCHED.pop(key, None)
    while len(_TOUCHED) > MAX_VIEWINGS:
        oldest = min(_TOUCHED, key=_TOUCHED.get)
        _BYTES.pop(oldest, None)
        _TOUCHED.pop(oldest, None)


def add(viewing: str | None, count: int) -> None:
    viewing = valid(viewing)
    if not viewing or count <= 0:
        return
    now = time.monotonic()
    with _LOCK:
        _BYTES[viewing] = _BYTES.get(viewing, 0) + int(count)
        _TOUCHED[viewing] = now
        _prune(now)


def total(viewing: str | None) -> int:
    viewing = valid(viewing)
    with _LOCK:
        return _BYTES.get(viewing, 0) if viewing else 0


def reset() -> None:
    with _LOCK:
        _BYTES.clear()
        _TOUCHED.clear()


class CountingFileResponse(FileResponse):
    """A FileResponse that records the body bytes actually written to the client."""

    def __init__(self, *args, viewing: str | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.viewing = valid(viewing)

    async def __call__(self, scope, receive, send):
        if not self.viewing or scope.get("method") == "HEAD":
            return await super().__call__(scope, receive, send)

        async def counting_send(message):
            if message.get("type") == "http.response.body":
                add(self.viewing, len(message.get("body") or b""))
            await send(message)

        return await super().__call__(scope, receive, counting_send)
