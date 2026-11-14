"""Local read-only media library catalog and folder configuration."""
import os
import sqlite3
from pathlib import Path
from threading import Lock
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

MEDIA_ROOT = Path(os.environ.get("MEDIA_ROOT", "/media")).resolve()
DB_PATH = Path(os.environ.get("DATABASE_PATH", "/data/library.sqlite3"))
VIDEO_EXTENSIONS = {".mkv", ".mp4", ".m4v", ".avi", ".mov", ".wmv", ".ts", ".webm", ".mpg", ".mpeg"}
scan_lock = Lock()
router = APIRouter(prefix="/api")


class LibraryRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    kind: str
    path: str


def db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout=30000")
    connection.execute("CREATE TABLE IF NOT EXISTS libraries (id INTEGER PRIMARY KEY, name TEXT NOT NULL, kind TEXT NOT NULL, path TEXT NOT NULL UNIQUE, last_scanned TEXT)")
    connection.execute("CREATE TABLE IF NOT EXISTS media (id INTEGER PRIMARY KEY, library_id INTEGER NOT NULL, path TEXT NOT NULL UNIQUE, title TEXT NOT NULL, size INTEGER NOT NULL, mtime_ns INTEGER NOT NULL, FOREIGN KEY(library_id) REFERENCES libraries(id))")
    connection.commit()
    return connection


def safe_folder(folder: str):
    candidate = Path(folder).resolve(strict=True)
    if not candidate.is_dir() or not candidate.is_relative_to(MEDIA_ROOT):
        raise HTTPException(400, "Select a directory inside the mounted media drive")
    return candidate


@router.get("/folders")
def folders(path: str = "/media"):
    try:
        parent = safe_folder(path)
        items = [{"name": entry.name, "path": str(entry)}
                 for entry in parent.iterdir()
                 if entry.is_dir() and not entry.is_symlink() and not entry.name.startswith(".")]
        return {"path": str(parent), "folders": sorted(items, key=lambda i: i["name"].casefold())}
    except (OSError, ValueError) as exc:
        raise HTTPException(400, f"Cannot browse folder: {exc}") from exc


@router.get("/libraries")
def libraries():
    with db() as connection:
        rows = connection.execute("""
          SELECT l.*, (SELECT count(*) FROM media WHERE library_id=l.id) AS media_count
          FROM libraries l ORDER BY l.kind, l.name
        """).fetchall()
        return [dict(r) for r in rows]


@router.post("/libraries", status_code=201)
def create_library(item: LibraryRequest):
    if item.kind not in {"movies", "tv"}:
        raise HTTPException(400, "Library type must be movies or tv")
    try:
        folder = safe_folder(item.path)
    except (OSError, ValueError) as exc:
        raise HTTPException(400, f"Invalid folder: {exc}") from exc
    try:
        with db() as connection:
            cursor = connection.execute(
                "INSERT INTO libraries (name,kind,path) VALUES (?,?,?)",
                (item.name.strip(), item.kind, str(folder)),
            )
            return {"id": cursor.lastrowid, "name": item.name.strip(), "kind": item.kind, "path": str(folder)}
    except sqlite3.IntegrityError as exc:
        raise HTTPException(409, "This folder already belongs to a library") from exc


@router.delete("/libraries/{library_id}")
def delete_library(library_id: int):
    with db() as connection:
        existing = connection.execute("SELECT id FROM libraries WHERE id=?", (library_id,)).fetchone()
        if not existing:
            raise HTTPException(404, "Library not found")
        connection.execute("DELETE FROM media WHERE library_id=?", (library_id,))
        connection.execute("DELETE FROM libraries WHERE id=?", (library_id,))
    return {"removed": True, "media_files_deleted": False}


@router.post("/libraries/{library_id}/scan")
def scan_library(library_id: int):
    if not scan_lock.acquire(blocking=False):
        raise HTTPException(409, "A scan is already running")
    try:
        with db() as connection:
            library = connection.execute("SELECT * FROM libraries WHERE id=?", (library_id,)).fetchone()
            if not library:
                raise HTTPException(404, "Library not found")
            try:
                root = safe_folder(library["path"])
            except (OSError, ValueError) as exc:
                raise HTTPException(400, f"Library folder unavailable: {exc}") from exc

            seen = set()
            errors = 0
            for directory, dirs, files in os.walk(root, followlinks=False):
                dirs[:] = [d for d in dirs if not d.startswith(".") and not Path(directory, d).is_symlink()]
                for filename in files:
                    file_path = Path(directory, filename)
                    if file_path.suffix.lower() not in VIDEO_EXTENSIONS or file_path.is_symlink():
                        continue
                    try:
                        stat = file_path.stat()
                        media_path = str(file_path)
                        seen.add(media_path)
                        connection.execute("""
                          INSERT INTO media (library_id,path,title,size,mtime_ns) VALUES (?,?,?,?,?)
                          ON CONFLICT(path) DO UPDATE SET library_id=excluded.library_id,
                          title=excluded.title,size=excluded.size,mtime_ns=excluded.mtime_ns
                        """, (library_id, media_path, file_path.stem, stat.st_size, stat.st_mtime_ns))
                    except OSError:
                        errors += 1
            # Never remove catalog entries if the scan encountered unreadable files.
            if errors == 0:
                existing = connection.execute("SELECT path FROM media WHERE library_id=?", (library_id,)).fetchall()
                for row in existing:
                    if row["path"] not in seen:
                        connection.execute("DELETE FROM media WHERE library_id=? AND path=?", (library_id, row["path"]))
            now = datetime.now(timezone.utc).isoformat()
            connection.execute("UPDATE libraries SET last_scanned=? WHERE id=?", (now, library_id))
            return {"found": len(seen), "errors": errors, "last_scanned": now}
    finally:
        scan_lock.release()


@router.get("/libraries/{library_id}/media")
def media(library_id: int):
    with db() as connection:
        return [dict(row) for row in connection.execute(
            "SELECT id,path,title,size FROM media WHERE library_id=? ORDER BY title LIMIT 500",
            (library_id,)
        )]
