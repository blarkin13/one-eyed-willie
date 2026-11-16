"""Local or connected user Plex-server movie and TV theme playback.

Never fetch Plex hosted themes from third-party metadata services directly.
A user's configured Plex LAN server is the only external audio source.
"""
import re
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response

from .library import MEDIA_ROOT
from .playback import _item

router = APIRouter(prefix="/api/themes")
EXTENSIONS = (".mp3", ".m4a", ".ogg", ".flac", ".wav")
MIME = {
    ".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".ogg": "audio/ogg",
    ".flac": "audio/flac", ".wav": "audio/wav",
}
MAX_BYTES = 50 * 1024 * 1024
PLEX_THEME_PATH = re.compile(r"^/library/metadata/[0-9]+/theme/[0-9]+$")
INDEX_TTL = 15 * 60
_index_lock = threading.RLock()
_index = {"url": None, "expires": 0, "items": {}}


def theme_for_media(media_id: int):
    item, video = _item(media_id)
    root = Path(item["root"]).resolve(strict=True)
    if item["kind"] == "tv":
        relative = video.relative_to(root)
        if len(relative.parts) < 2:
            return None
        folder = root / relative.parts[0]
    elif item["kind"] == "movies":
        folder = video.parent
        if folder == root:
            return None
    else:
        return None
    try:
        folder = folder.resolve(strict=True)
        if not folder.is_dir() or not folder.is_relative_to(root):
            return None
    except (OSError, ValueError, RuntimeError):
        return None
    for extension in EXTENSIONS:
        candidate = folder / ("theme" + extension)
        try:
            if candidate.is_symlink():
                continue
            resolved = candidate.resolve(strict=True)
            if (resolved.is_relative_to(folder) and resolved.is_relative_to(MEDIA_ROOT)
                    and resolved.is_file() and 0 < resolved.stat().st_size <= MAX_BYTES):
                return resolved
        except (OSError, ValueError, RuntimeError):
            continue
    return None


def _plex_index(settings):
    """Bounded, read-only Plex catalog. Network activity only if Plex is configured."""
    from . import plex_import
    with _index_lock:
        now = time.monotonic()
        identifier = (settings["url"], settings["token"])
        if _index["url"] == identifier and now < _index["expires"]:
            return _index["items"]
        sections = plex_import._plex_get(settings["url"], settings["token"],
                                         "/library/sections").get("Directory") or []
        found = {}
        for section in sections:
            kind = section.get("type")
            if kind not in ("show", "movie"):
                continue
            section_id = plex_import._number(section.get("key"))
            if section_id is None:
                continue
            for offset in range(0, 10000, 250):
                page = plex_import._plex_get(
                    settings["url"], settings["token"],
                    "/library/sections/" + str(section_id) + "/all",
                    {"X-Plex-Container-Start": offset, "X-Plex-Container-Size": 250})
                rows = page.get("Metadata") or []
                if not isinstance(rows, list):
                    break
                for row in rows:
                    if not isinstance(row, dict) or row.get("type") != kind:
                        continue
                    title = plex_import._norm(row.get("title"))
                    year = plex_import._number(row.get("year"))
                    rating_key = plex_import._number(row.get("ratingKey"))
                    if title and rating_key is not None:
                        found.setdefault((kind, title), []).append((year, rating_key))
                total = plex_import._number(page.get("totalSize"))
                if not rows or len(rows) < 250 or (
                    total is not None and offset + len(rows) >= total
                ):
                    break
        _index.update(url=identifier, expires=time.monotonic() + INDEX_TTL, items=found)
        return found


def _plex_theme(media_id):
    """Resolve an exact title/year match in the user's configured LAN Plex server."""
    from . import plex_import
    from .catalog import episode_info, movie_info
    try:
        settings = plex_import._require_config()
    except HTTPException:
        return None
    item, video = _item(media_id)
    kind = "show" if item["kind"] == "tv" else "movie" if item["kind"] == "movies" else None
    if not kind:
        return None
    parsed = (episode_info(str(video), item["root"]) if kind == "show"
              else movie_info(str(video), item["root"]))
    title = plex_import._norm(parsed["title"])
    if not title:
        return None
    try:
        choices = _plex_index(settings).get((kind, title), [])
        year = parsed["year"]
        if year is not None:
            choices = [c for c in choices if c[0] is not None and abs(c[0] - year) <= 1]
        if len(choices) != 1:
            return None
        key = choices[0][1]
        details = plex_import._plex_get(settings["url"], settings["token"],
                                        "/library/metadata/" + str(key))
        matches = details.get("Metadata") or []
        if len(matches) != 1:
            return None
        theme = matches[0].get("theme")
        if isinstance(theme, str) and PLEX_THEME_PATH.fullmatch(theme):
            return (settings, theme)
    except (HTTPException, OSError, ValueError):
        return None
    return None


@router.get("/{media_id}/info")
def theme_info(media_id: int):
    local = theme_for_media(media_id)
    if local:
        return {"available": True, "source": "local",
                "url": f"/api/themes/{media_id}/audio"}
    plex = _plex_theme(media_id)
    return {"available": bool(plex), "source": "plex" if plex else None,
            "url": f"/api/themes/{media_id}/audio" if plex else None}


@router.get("/{media_id}/audio")
def theme_audio(media_id: int):
    local = theme_for_media(media_id)
    if local:
        return FileResponse(local, media_type=MIME[local.suffix.lower()],
                            headers={"Cache-Control": "private, no-store",
                                     "X-Content-Type-Options": "nosniff",
                                     "Content-Disposition": "inline"})
    plex = _plex_theme(media_id)
    if not plex:
        raise HTTPException(404, "No theme music available for this title")
    settings, path = plex
    from . import plex_import
    request = urllib.request.Request(
        settings["url"] + path,
        headers={"X-Plex-Token": settings["token"],
                 "X-Plex-Client-Identifier": "one-eyed-willie-plex-themes",
                 "Accept": "audio/mpeg",
                 "User-Agent": "OneEyedWillie/1.0"})
    try:
        with plex_import.OPENER.open(request, timeout=12) as remote:
            if remote.status != 200:
                raise HTTPException(502, "Plex theme audio unavailable")
            length = remote.headers.get("Content-Length")
            if length and int(length) > MAX_BYTES:
                raise HTTPException(502, "Plex theme exceeds size limit")
            audio = remote.read(MAX_BYTES + 1)
            if len(audio) > MAX_BYTES or not audio:
                raise HTTPException(502, "Plex theme audio unavailable or too large")
            content_type = remote.headers.get("Content-Type", "").split(";")[0].lower()
            if content_type not in ("audio/mpeg", "audio/mp3", "application/octet-stream"):
                raise HTTPException(502, "Plex did not return MP3 theme audio")
    except (urllib.error.HTTPError, urllib.error.URLError, OSError, ValueError) as error:
        raise HTTPException(502, "Could not load theme from connected Plex server") from error
    return Response(audio, media_type="audio/mpeg",
                    headers={"Cache-Control": "private, no-store",
                             "X-Content-Type-Options": "nosniff"})
