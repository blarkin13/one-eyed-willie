"""Compressed JSON responses for large, text-only API payloads.

Only used on explicit routes (the library catalog). It is deliberately not a
global middleware: media, HLS segments and artwork are served with byte-range
semantics or are already compressed, and must never be re-encoded.
"""
import gzip
import json

from fastapi import Request, Response
from fastapi.encoders import jsonable_encoder

MIN_COMPRESS_BYTES = 1024


def accepts_gzip(header: str) -> bool:
    """True when Accept-Encoding allows gzip (honours an explicit q=0)."""
    for part in (header or "").lower().split(","):
        token, _, params = part.strip().partition(";")
        if token.strip() not in ("gzip", "*"):
            continue
        quality = params.replace(" ", "")
        if quality.startswith("q="):
            try:
                if float(quality[2:]) <= 0:
                    continue
            except ValueError:
                continue
        return True
    return False


def compressed_json(request: Request, payload) -> Response:
    # The catalog payload is already plain dicts/lists/strings/numbers, so the C
    # JSON encoder handles it directly (~4 ms for 3,000 titles). Running every
    # value through jsonable_encoder first cost ~45 ms; it is now only the
    # fallback for the odd value (a set, a date) that json cannot encode itself.
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False,
                      default=jsonable_encoder).encode("utf-8")
    headers = {"Vary": "Accept-Encoding"}
    if len(body) >= MIN_COMPRESS_BYTES and accepts_gzip(
            request.headers.get("accept-encoding", "")):
        # Level 5 keeps CPU on the NUC low; JSON still shrinks by ~95%.
        body = gzip.compress(body, compresslevel=5, mtime=0)
        headers["Content-Encoding"] = "gzip"
    return Response(body, media_type="application/json", headers=headers)
