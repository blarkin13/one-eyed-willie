"""Stream indexed local media to LAN clients; no filesystem paths accepted from clients.

The server is currently unauthenticated. Only deploy on a trusted LAN.
"""
import mimetypes
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from .catalog import movie_info
from .library import db, MEDIA_ROOT, VIDEO_EXTENSIONS

router = APIRouter(prefix="/api/playback")

def media_file(media_id: int):
    with db() as conn:
        row = conn.execute(
            "SELECT m.path, l.path AS library_path FROM media m "
            "JOIN libraries l ON l.id=m.library_id WHERE m.id=?", (media_id,)
        ).fetchone()
    if row is None:
        raise HTTPException(404, "Media not found")
    video = Path(row["path"])
    library_root = Path(row["library_path"])
    try:
        # Prevent symlink traversal and never permit paths outside the mounted library.
        resolved = video.resolve(strict=True)
        lib = library_root.resolve(strict=True)
        if (video.is_symlink() or not resolved.is_relative_to(lib)
            or not resolved.is_relative_to(MEDIA_ROOT)
            or video.suffix.lower() not in VIDEO_EXTENSIONS
            or not resolved.is_file()):
            raise HTTPException(404, "Media unavailable")
    except (OSError, ValueError) as exc:
        raise HTTPException(404, "Media unavailable") from exc
    return resolved

@router.get("/movie")
def resolve_movie(library_id: int = Query(ge=1), key: str = Query(min_length=1, max_length=300)):
    with db() as conn:
        lib = conn.execute(
            "SELECT path,kind FROM libraries WHERE id=?", (library_id,)
        ).fetchone()
        if not lib or lib["kind"] != "movies":
            raise HTTPException(404, "Movie library not found")
        rows = conn.execute("SELECT id,path FROM media WHERE library_id=? ORDER BY id",
                            (library_id,)).fetchall()
    for row in rows:
        try:
            if movie_info(row["path"], lib["path"])["key"] == key:
                media_file(row["id"])
                return {"media_id": row["id"]}
        except (ValueError, OSError):
            continue
    raise HTTPException(404, "Movie not found")

@router.get("/{media_id}/stream")
def stream(media_id: int):
    if media_id < 1:
        raise HTTPException(404, "Media not found")
    path = media_file(media_id)
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    # Starlette FileResponse handles Range requests on current supported versions.
    return FileResponse(path, media_type=mime, content_disposition_type="inline",
                        headers={"Accept-Ranges": "bytes", "Cache-Control": "no-store"})
