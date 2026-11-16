"""Serve user-supplied theme music only from a media item's own show/movie folder.

No third-party downloads, arbitrary file paths, or remote audio URLs.
"""
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from .library import MEDIA_ROOT
from .playback import _item

router = APIRouter(prefix="/api/themes")
EXTENSIONS = (".mp3", ".m4a", ".ogg", ".flac", ".wav")
MIME = {
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".ogg": "audio/ogg",
    ".flac": "audio/flac",
    ".wav": "audio/wav",
}
MAX_BYTES = 50 * 1024 * 1024


def theme_for_media(media_id: int):
    item, video = _item(media_id)
    root = Path(item["root"]).resolve(strict=True)
    if item["kind"] == "tv":
        # Episode: /TV/Show/Season XX/Episode.mkv (also /TV/Show/Episode.mkv).
        relative = video.relative_to(root)
        if len(relative.parts) < 2:
            return None
        folder = root / relative.parts[0]
    elif item["kind"] == "movies":
        # Movie: /Movies/Title (Year)/Title.mkv. Never use a generic
        # theme.mp3 sitting at the top of a library for every movie.
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


@router.get("/{media_id}/info")
def theme_info(media_id: int):
    theme = theme_for_media(media_id)
    return {"available": bool(theme),
            "url": f"/api/themes/{media_id}/audio" if theme else None}


@router.get("/{media_id}/audio")
def theme_audio(media_id: int):
    theme = theme_for_media(media_id)
    if theme is None:
        raise HTTPException(404, "No local theme music for this title")
    return FileResponse(theme, media_type=MIME[theme.suffix.lower()],
                        headers={"Cache-Control": "private, no-store",
                                 "X-Content-Type-Options": "nosniff",
                                 "Content-Disposition": "inline"})
