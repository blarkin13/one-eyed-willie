"""Read-only Music library API: indexed files, embedded tags and ranged audio streaming."""
from pathlib import Path
from functools import lru_cache
from threading import Lock
import io
import mimetypes
import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response
from mutagen import File as AudioFile, MutagenError
from PIL import Image, UnidentifiedImageError

from . import library as _library
from .library import db, AUDIO_EXTENSIONS

router = APIRouter(prefix="/api/music", tags=["music"])

@lru_cache(maxsize=15000)
def _read_tags(filename, mtime_ns):
    return _read_file_tags(Path(filename))

def _read_file_tags(path):
    # Metadata is cached against the file modification timestamp, not its ID.
    parts = path.parts
    artist = path.parent.parent.name if len(parts) >= 3 else "Unknown Artist"
    album = path.parent.name if path.parent != path.parent.parent else "Unknown Album"
    title = path.stem
    duration = None
    track_number = None
    disc_number = None
    year = None
    genre = None
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
            disc = tag("discnumber")
            if disc:
                try:
                    disc_number = int(disc.split("/")[0])
                except ValueError:
                    pass
            date = tag("originaldate", "date", "year")
            if date and date[:4].isdigit():
                year = int(date[:4])
            genre = (tag("genre") or "").split(";")[0].strip()[:60] or None
            duration = round(float(audio.info.length), 2) if audio.info else None
    except (OSError, ValueError, TypeError, KeyError, MutagenError):
        pass
    return {"title": title, "artist": artist, "album": album,
            "track_number": track_number, "disc_number": disc_number,
            "year": year, "genre": genre, "duration": duration}

# ---------------------------------------------------------------------------
# Tags are stored in the database (like Movies' metadata), keyed by the file's
# modification time recorded by the library scan. A file is opened only when it
# is new or has changed, never on every page load.
TAG_FIELDS = ("title", "artist", "album", "track_number", "disc_number", "year", "genre", "duration")
_table_ready = None  # database path the table was ensured for
_fill_lock = Lock()


def _ensure_table(connection):
    global _table_ready
    if _table_ready == str(_library.DB_PATH):
        return
    connection.execute("""CREATE TABLE IF NOT EXISTS music_tags (
        media_id INTEGER PRIMARY KEY REFERENCES media(id) ON DELETE CASCADE,
        mtime_ns INTEGER, title TEXT, artist TEXT, album TEXT, track_number INTEGER,
        disc_number INTEGER, year INTEGER, genre TEXT, duration REAL)""")
    _table_ready = str(_library.DB_PATH)


def _rows(connection, library_id=None):
    query = """SELECT m.id,m.library_id,m.path,m.added_at,m.mtime_ns,
        t.mtime_ns AS tag_mtime,t.title,t.artist,t.album,t.track_number,t.disc_number,
        t.year,t.genre,t.duration
        FROM media m JOIN libraries l ON l.id=m.library_id
        LEFT JOIN music_tags t ON t.media_id=m.id
        WHERE l.kind='music'"""
    params = ()
    if library_id is not None:
        query += " AND l.id=?"
        params = (library_id,)
    return connection.execute(query + " ORDER BY m.path", params).fetchall()


def refresh_tags(library_id=None):
    """Read tags for new or changed files only. Called after scans and, as a
    fallback, by the catalog. Returns the number of files read."""
    with _fill_lock:
        with db() as connection:
            _ensure_table(connection)
            stale = [(r["id"], r["mtime_ns"], r["path"]) for r in _rows(connection, library_id)
                     if r["tag_mtime"] is None or r["tag_mtime"] != r["mtime_ns"]]
        if not stale:
            return 0
        # Read the files with NO database transaction open: a slow USB drive
        # must never hold the write lock that scans and playback progress need.
        values = []
        for media_id, mtime_ns, path in stale:
            tags = _read_file_tags(Path(path))
            values.append((media_id, mtime_ns, *(tags[f] for f in TAG_FIELDS)))
        with db() as connection:
            connection.executemany(
                "INSERT OR REPLACE INTO music_tags (media_id,mtime_ns," + ",".join(TAG_FIELDS) +
                ") VALUES (?,?," + ",".join("?" * len(TAG_FIELDS)) + ")", values)
        return len(stale)


def _track(row):
    return {"id": row["id"], "library_id": row["library_id"],
            "added_at": row["added_at"], **{f: row[f] for f in TAG_FIELDS}}


def _files(library_id=None):
    with db() as connection:
        _ensure_table(connection)
        rows = _rows(connection, library_id)
    if any(r["tag_mtime"] is None or r["tag_mtime"] != r["mtime_ns"] for r in rows):
        # Normally done right after the scan; only new files are read here.
        refresh_tags(library_id)
        with db() as connection:
            rows = _rows(connection, library_id)
    return rows

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
                track.get("disc_number") or 1,
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

ART_DIR = Path(os.environ.get("ARTWORK_CACHE_DIR", "/data/artwork")) / "music"
ART_SIZE = 640


@router.get("/tracks/{track_id}/art")
def music_art(track_id: int):
    """Embedded cover art, extracted once, resized and cached on disk."""
    with db() as connection:
        row = connection.execute("SELECT mtime_ns FROM media WHERE id=?", (track_id,)).fetchone()
    version = row["mtime_ns"] if row else 0
    cached = ART_DIR / f"{track_id}-{version}.jpg"
    missing = ART_DIR / f"{track_id}-{version}.none"
    headers = {"Cache-Control": "private, max-age=86400"}
    if row and cached.is_file():
        return FileResponse(cached, media_type="image/jpeg", headers=headers)
    if row and missing.exists():
        raise HTTPException(404, "No embedded album artwork")
    data, mime = _embedded_art(_safe_track(track_id))
    ART_DIR.mkdir(parents=True, exist_ok=True)
    for old in ART_DIR.glob(f"{track_id}-*"):
        old.unlink(missing_ok=True)
    if not data:
        missing.touch()
        raise HTTPException(404, "No embedded album artwork")
    try:
        with Image.open(io.BytesIO(data)) as picture:
            picture = picture.convert("RGB")
            picture.thumbnail((ART_SIZE, ART_SIZE), Image.Resampling.LANCZOS)
            buffer = io.BytesIO()
            picture.save(buffer, "JPEG", quality=86, optimize=True)
        tmp = cached.with_suffix(".tmp")
        tmp.write_bytes(buffer.getvalue())
        os.replace(tmp, cached)
        return FileResponse(cached, media_type="image/jpeg", headers=headers)
    except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError):
        return Response(content=data, media_type=mime, headers=headers)


def _embedded_art(path):
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
                        mime = "image/png" if data.startswith(bytes([137,80,78,71])) else "image/jpeg"
                        break
    except (OSError, ValueError, TypeError, KeyError, AttributeError, MutagenError):
        pass
    if not data or len(data) > 15_000_000 or mime not in ("image/jpeg", "image/png"):
        return None, None
    return data, mime
