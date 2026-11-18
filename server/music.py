"""Read-only Music library API: indexed files, embedded tags and ranged audio streaming."""
from collections import defaultdict
from pathlib import Path
import mimetypes

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response
from mutagen import File as AudioFile

from .library import db, AUDIO_EXTENSIONS

router = APIRouter(prefix="/api/music", tags=["music"])

def _track(row):
    path = Path(row["path"])
    parts = path.parts
    artist = path.parent.parent.name if len(parts) >= 3 else "Unknown Artist"
    album = path.parent.name if path.parent != path.parent.parent else "Unknown Album"
    title = path.stem
    duration = None
    track_number = None
    try:
        audio = AudioFile(str(path), easy=True)
        if audio is not None:
            def tag(*keys):
                for key in keys:
                    value = audio.get(key)
                    if value:
                        return str(value[0])
                return None
            artist = tag("albumartist", "artist") or artist
            album = tag("album") or album
            title = tag("title") or title
            number = tag("tracknumber")
            if number:
                try:
                    track_number = int(number.split("/")[0])
                except ValueError:
                    pass
            duration = round(float(audio.info.length), 2) if audio.info else None
    except (OSError, ValueError, TypeError, KeyError):
        pass
    return {"id": row["id"], "library_id": row["library_id"], "title": title,
            "artist": artist, "album": album, "track_number": track_number,
            "duration": duration, "added_at": row["added_at"]}

def _files(library_id=None):
    with db() as connection:
        query = """SELECT m.id,m.library_id,m.path,m.added_at FROM media m
            JOIN libraries l ON l.id=m.library_id WHERE l.kind='music'"""
        params = ()
        if library_id is not None:
            query += " AND l.id=?"
            params = (library_id,)
        return connection.execute(query+" ORDER BY m.path", params).fetchall()

@router.get("/catalog")
def music_catalog(library_id: int | None = None, search: str = ""):
    if library_id is not None:
        with db() as connection:
            row = connection.execute("SELECT kind FROM libraries WHERE id=?", (library_id,)).fetchone()
        if not row or row["kind"] != "music":
            raise HTTPException(404, "Music library not found")
    query = search.strip().casefold()[:120]
    tracks = [_track(row) for row in _files(library_id)]
    if query:
        tracks = [track for track in tracks if query in
                  (track["title"]+" "+track["artist"]+" "+track["album"]).casefold()]
    tracks.sort(key=lambda track: (track["artist"].casefold(),track["album"].casefold(),
                track["track_number"] if track["track_number"] is not None else 9999,
                track["title"].casefold()))
    grouped = {}
    for track in tracks:
        key = (track["artist"].casefold(),track["album"].casefold())
        if key not in grouped:
            grouped[key] = {"artist": track["artist"], "title": track["album"],
                            "track_count": 0, "track_ids": []}
        grouped[key]["track_count"] += 1
        grouped[key]["track_ids"].append(track["id"])
    return {"total": len(tracks), "tracks": tracks, "albums": list(grouped.values())}

def _safe_track(track_id):
    with db() as connection:
        row = connection.execute("""SELECT m.path,m.library_id FROM media m
            JOIN libraries l ON l.id=m.library_id
            WHERE m.id=? AND l.kind='music'""", (track_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Track not found")
        roots = [Path(root["path"]).resolve() for root in connection.execute(
            "SELECT path FROM library_folders WHERE library_id=?", (row["library_id"],))]
    path = Path(row["path"]).resolve()
    if not any(path.is_relative_to(root) for root in roots) or path.suffix.lower() not in AUDIO_EXTENSIONS:
        raise HTTPException(403, "Track is outside its configured music folder")
    if not path.is_file():
        raise HTTPException(404, "Audio file missing")
    return path

@router.get("/tracks/{track_id}/stream")
def music_stream(track_id: int):
    path = _safe_track(track_id)
    mime = {".flac": "audio/flac", ".m4a": "audio/mp4", ".aiff":"audio/aiff",
            ".opus": "audio/ogg", ".ogg": "audio/ogg"}.get(path.suffix.lower())
    return FileResponse(path, media_type=mime or mimetypes.guess_type(path.name)[0]
                        or "application/octet-stream", filename=None,
                        headers={"Cache-Control":"private, no-store",
                                 "X-Content-Type-Options":"nosniff"})

@router.get("/tracks/{track_id}/art")
def music_art(track_id: int):
    path = _safe_track(track_id)
    data = None
    mime = "image/jpeg"
    try:
        audio = AudioFile(str(path))
        if audio:
            pictures = getattr(audio, "pictures", None)
            if pictures:
                data = pictures[0].data
                mime = pictures[0].mime or mime
            elif getattr(audio, "tags", None):
                for key, value in audio.tags.items():
                    if str(key).startswith("APIC"):
                        data = value.data
                        mime = getattr(value, "mime", mime)
                        break
                    if str(key) == "covr" and value:
                        data = bytes(value[0])
                        mime = "image/png" if data.startswith(b"\\x89PNG") else "image/jpeg"
                        break
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        pass
    if not data or len(data) > 5_000_000 or mime not in ("image/jpeg", "image/png"):
        raise HTTPException(404, "No embedded album artwork")
    return Response(content=data,media_type=mime,headers={"Cache-Control":"private, max-age=3600"})
