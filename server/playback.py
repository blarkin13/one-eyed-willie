"""Local authenticated-by-origin media playback, status and watch history.

Streaming is intentionally served by the NUC, NOT the Cloudflare Worker.
The remote Worker blocks video bytes; clients must navigate to the protected
Caddy HTTPS origin to play. Files are never modified.
"""
import asyncio
import mimetypes
import os
import subprocess
import json
import math
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from .library import MEDIA_ROOT, db
from .media_probe import inspect_media
from . import usage

router = APIRouter(prefix="/api/watch")
TRANSCODE_SLOTS = asyncio.Semaphore(2)

BROWSER_TYPES = {
    ".mp4": "video/mp4", ".m4v": "video/mp4", ".mov": "video/quicktime",
    ".webm": "video/webm", ".ogv": "video/ogg",
}

# These containers can be served to capable native players (e.g. Media3).
DIRECT_TYPES = {
    **BROWSER_TYPES,
    ".mkv": "video/x-matroska",
    ".avi": "video/x-msvideo",
    ".ts": "video/mp2t",
    ".m2ts": "video/mp2t",
    ".mpg": "video/mpeg",
    ".mpeg": "video/mpeg",
}


class WatchedRequest(BaseModel):
    watched: bool


def _item(media_id: int):
    with db() as conn:
        row = conn.execute(
            "SELECT m.id,m.path,m.size,m.library_id,l.path AS root,l.kind "
            "FROM media m JOIN libraries l ON l.id=m.library_id "
            "WHERE m.id=?", (media_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(404, "Media not found")
    file = Path(row["path"])
    try:
        # Never trust paths as authorization, even when indexed in SQLite.
        if file.is_symlink():
            raise ValueError("Symlink files cannot be streamed")
        safe = file.resolve(strict=True)
        if not safe.is_file() or not safe.is_relative_to(MEDIA_ROOT):
            raise ValueError("Outside mounted media drive")
        if not safe.is_relative_to(Path(row["root"]).resolve(strict=True)):
            raise ValueError("Outside configured library")
    except (ValueError, OSError):
        raise HTTPException(404, "Media file is not available")
    return dict(row), safe


def probe_duration(file: Path):
    """Best-effort duration for streams whose fragmented MP4 timeline is infinite."""
    try:
        result = subprocess.run(
            ["/usr/bin/ffprobe", "-v", "error", "-show_entries",
             "format=duration", "-of", "json", str(file)],
            capture_output=True, text=True, timeout=6, check=False,
        )
        seconds = float(json.loads(result.stdout).get("format", {}).get("duration", 0))
        return seconds if math.isfinite(seconds) and 0 < seconds <= 10000000 else 0
    except (OSError, ValueError, subprocess.TimeoutExpired, TypeError):
        return 0


@router.get("/{media_id}/status")
def watch_status(media_id: int):
    row, file = _item(media_id)
    with db() as conn:
        existing = conn.execute(
            "SELECT position_seconds,duration_seconds,completed,updated_at "
            "FROM playback_progress WHERE media_id=?", (media_id,),
        ).fetchone()
    progress = dict(existing) if existing else None
    return {
        "media_id": media_id,
        "watched": bool(progress and progress["completed"]),
        "position_seconds": progress["position_seconds"] if progress else 0,
        "duration_seconds": (progress["duration_seconds"] if progress and progress["duration_seconds"] else probe_duration(file)),
        "extension": file.suffix.lower(),
        "media": inspect_media(file),
        "mode": "direct" if file.suffix.lower() in BROWSER_TYPES else "compatible",
        "stream_url": f"/api/watch/{media_id}/stream",
        "compatible_url": f"/api/watch/{media_id}/transcode",
    }


@router.put("/{media_id}/watched")
def mark_watched(media_id: int, update: WatchedRequest):
    _item(media_id)
    with db() as conn:
        previous = conn.execute(
            "SELECT position_seconds,duration_seconds FROM playback_progress WHERE media_id=?",
            (media_id,),
        ).fetchone()
        duration = previous["duration_seconds"] if previous else 0
        if update.watched:
            # Duration is unknown if the media has never been played; retain a
            # completed row with zero duration and no misleading resume position.
            position = duration
            conn.execute(
                "INSERT INTO playback_progress(media_id,position_seconds,duration_seconds,completed,updated_at) "
                "VALUES(?,?,?,?,CURRENT_TIMESTAMP) ON CONFLICT(media_id) DO UPDATE SET "
                "position_seconds=excluded.position_seconds,duration_seconds=excluded.duration_seconds,"
                "completed=excluded.completed,updated_at=CURRENT_TIMESTAMP",
                (media_id, position, duration, 1),
            )
        else:
            # Unwatched resets resume as well; the next play starts at beginning.
            conn.execute("DELETE FROM playback_progress WHERE media_id=?", (media_id,))
    return {"media_id": media_id, "watched": update.watched}


@router.get("/{media_id}/stream")
@router.head("/{media_id}/stream")
def stream_media(media_id: int, viewing: str = Query("", max_length=64)):
    _, file = _item(media_id)
    suffix = file.suffix.lower()
    if suffix not in DIRECT_TYPES:
        raise HTTPException(415, "This file is not supported for direct streaming")
    return usage.CountingFileResponse(
        file, viewing=viewing, media_type=DIRECT_TYPES[suffix], filename=None,
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            "Accept-Ranges": "bytes",
        },
    )


@router.get("/{media_id}/transcode")
async def transcode_media(
    media_id: int,
    request: Request,
    start: float = Query(0, ge=0, le=10000000),
):
    """Compatibility playback for MKV/AVI/etc. FFmpeg outputs fragmented MP4.

    Playback is progressive and intentionally not seekable via byte ranges;
    a new request with start=seconds restarts the transcoder at that position.
    """
    _, file = _item(media_id)
    if not os.path.isfile("/usr/bin/ffmpeg"):
        raise HTTPException(503, "Compatibility player is not installed")
    # Avoid using the remote Cloudflare Worker to stream video or to trigger
    # a server-side ffmpeg process. Worker traffic is blocked independently.
    command = ["/usr/bin/ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin",
               "-ss", str(start), "-i", str(file),
               "-map", "0:v:0", "-map", "0:a:0?",
               "-c:v", "libx264", "-preset", "ultrafast", "-threads", "2",
               "-pix_fmt", "yuv420p", "-crf", "25",
               "-c:a", "aac", "-b:a", "160k",
               "-movflags", "frag_keyframe+empty_moov+default_base_moof",
               "-f", "mp4", "pipe:1"]

    async def output():
        async with TRANSCODE_SLOTS:
            proc = await asyncio.create_subprocess_exec(
                *command, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            try:
                while True:
                    if await request.is_disconnected():
                        break
                    chunk = await proc.stdout.read(128 * 1024)
                    if not chunk:
                        break
                    yield chunk
            finally:
                if proc.returncode is None:
                    proc.kill()
                await proc.wait()

    return StreamingResponse(output(), media_type="video/mp4", headers={
        "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
        "Accept-Ranges": "none",
    })
