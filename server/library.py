"""Local read-only media library catalog and folder configuration."""
import os
import sqlite3
from pathlib import Path
from threading import Lock
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Literal

MEDIA_ROOT = Path(os.environ.get("MEDIA_ROOT", "/media")).resolve()
DB_PATH = Path(os.environ.get("DATABASE_PATH", "/data/library.sqlite3"))
VIDEO_EXTENSIONS = {".mkv", ".mp4", ".m4v", ".avi", ".mov", ".wmv", ".ts", ".webm", ".mpg", ".mpeg"}
scan_lock = Lock()
router = APIRouter(prefix="/api")


# First-party SVG icon and font options shared with library-appearance.js.
LIBRARY_ICONS = (
    "film", "tv", "folder", "clapperboard", "play", "reel", "popcorn", "ticket", "camera", "video", "headphones", "music", 
    "star", "heart", "ghost", "skull", "pumpkin", "flame", "zap", "rocket", "planet", "robot", "alien", "wand", "sword", 
    "crown", "shield", "smile", "drama", "eye", "fingerprint", "trophy", "gamepad", "book", "archive", "layers", "grid", 
    "bookmark", "gem", "award", "clock", "calendar", "hourglass", "search", "map", "compass", "globe", "mountain", "tree", 
    "leaf", "paw", "users", "sun", "moon", "snowflake", "gift", "plane", "ship", "car", "sparkles"
)
LIBRARY_FONTS = (
    "default", "modern", "cinematic", "display", "condensed", "rounded", "serif", "editorial", "vintage", "mono", "typewriter", "script"
)


class LibraryRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    kind: Literal["movies", "tv"]
    path: str
    icon: str = "folder"
    font: str = "default"


class LibraryEdit(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    icon: str = "folder"
    font: str = "default"
    sidebar_hidden: bool = False


class FolderRequest(BaseModel):
    path: str


def db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout=30000")
    connection.execute("CREATE TABLE IF NOT EXISTS libraries (id INTEGER PRIMARY KEY, name TEXT NOT NULL, kind TEXT NOT NULL, path TEXT NOT NULL UNIQUE, last_scanned TEXT)")
    connection.execute("CREATE TABLE IF NOT EXISTS media (id INTEGER PRIMARY KEY, library_id INTEGER NOT NULL, path TEXT NOT NULL UNIQUE, title TEXT NOT NULL, size INTEGER NOT NULL, mtime_ns INTEGER NOT NULL, added_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY(library_id) REFERENCES libraries(id))")
    library_columns = {row[1] for row in connection.execute("PRAGMA table_info(libraries)")}
    for name, schema in (
        ("icon", "TEXT NOT NULL DEFAULT 'folder'"),
        ("font", "TEXT NOT NULL DEFAULT 'default'"),
        ("sidebar_hidden", "INTEGER NOT NULL DEFAULT 0"),
        ("sort_order", "INTEGER NOT NULL DEFAULT 0"),
    ):
        if name not in library_columns:
            connection.execute(f"ALTER TABLE libraries ADD COLUMN {name} {schema}")
    connection.execute("""CREATE TABLE IF NOT EXISTS library_folders (
        id INTEGER PRIMARY KEY, library_id INTEGER NOT NULL, path TEXT NOT NULL UNIQUE,
        FOREIGN KEY(library_id) REFERENCES libraries(id)
    )""")
    # Backfill all old single-folder libraries without changing their IDs or files.
    connection.execute("INSERT OR IGNORE INTO library_folders(library_id,path) SELECT id,path FROM libraries")
    connection.execute("CREATE INDEX IF NOT EXISTS library_folders_library_idx ON library_folders(library_id)")
    media_columns = {row[1] for row in connection.execute("PRAGMA table_info(media)")}
    if "source_root" not in media_columns:
        connection.execute("ALTER TABLE media ADD COLUMN source_root TEXT NOT NULL DEFAULT ''")
    # Preserve first-seen dates on every rescan, including after upgrades from v0.4.
    columns = {row[1] for row in connection.execute("PRAGMA table_info(media)")}
    if "added_at" not in columns:
        connection.execute("ALTER TABLE media ADD COLUMN added_at TEXT")
        # Existing entries have no recorded first-seen time; migration time is the honest baseline.
        connection.execute("UPDATE media SET added_at=CURRENT_TIMESTAMP WHERE added_at IS NULL")
    connection.execute("""CREATE TABLE IF NOT EXISTS playback_progress (
        media_id INTEGER PRIMARY KEY,
        position_seconds REAL NOT NULL,
        duration_seconds REAL NOT NULL,
        completed INTEGER NOT NULL DEFAULT 0,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""")
    connection.execute("CREATE INDEX IF NOT EXISTS media_added_idx ON media(added_at DESC)")
    connection.execute("CREATE INDEX IF NOT EXISTS playback_updated_idx ON playback_progress(updated_at DESC)")
    connection.commit()
    return connection


def safe_folder(folder: str):
    try:
        candidate = Path(folder).resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise HTTPException(400, "The selected folder is unavailable") from error
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


def _library_view(conn, library_id=None):
    rows = conn.execute("""
        SELECT l.*, (SELECT count(*) FROM media WHERE library_id=l.id) AS media_count
        FROM libraries l WHERE (? IS NULL OR l.id=?)
        ORDER BY l.sort_order, l.kind, l.name
    """, (library_id, library_id)).fetchall()
    folders = {}
    for folder in conn.execute("SELECT id,library_id,path FROM library_folders ORDER BY id"):
        folders.setdefault(folder["library_id"], []).append({"id": folder["id"], "path": folder["path"]})
    return [{**dict(row), "sidebar_hidden": bool(row["sidebar_hidden"]),
             "folders": folders.get(row["id"], [])} for row in rows]


@router.get("/libraries")
def libraries():
    with db() as connection:
        return _library_view(connection)


def _validate_style(icon, font):
    if icon not in LIBRARY_ICONS or font not in LIBRARY_FONTS:
        raise HTTPException(422, "Choose a supported library icon and font")


def _reject_folder_overlap(conn, folder, exclude_library_id=None):
    for row in conn.execute("SELECT library_id,path FROM library_folders"):
        other = Path(row["path"])
        if folder == other:
            raise HTTPException(409, "This folder is already in a library")
        if folder.is_relative_to(other) or other.is_relative_to(folder):
            raise HTTPException(409, "Choose a separate folder, not one inside another library folder")


@router.patch("/libraries/{library_id}")
def update_library(library_id: int, item: LibraryEdit):
    _validate_style(item.icon, item.font)
    name = item.name.strip()
    if not name:
        raise HTTPException(422, "Library name is required")
    with db() as connection:
        if not connection.execute("SELECT 1 FROM libraries WHERE id=?", (library_id,)).fetchone():
            raise HTTPException(404, "Library not found")
        connection.execute(
            "UPDATE libraries SET name=?,icon=?,font=?,sidebar_hidden=? WHERE id=?",
            (name, item.icon, item.font, int(item.sidebar_hidden), library_id))
        return _library_view(connection, library_id)[0]


@router.post("/libraries/{library_id}/folders", status_code=201)
def add_library_folder(library_id: int, item: FolderRequest):
    folder = safe_folder(item.path)
    with db() as connection:
        if not connection.execute("SELECT 1 FROM libraries WHERE id=?", (library_id,)).fetchone():
            raise HTTPException(404, "Library not found")
        _reject_folder_overlap(connection, folder)
        connection.execute("INSERT INTO library_folders(library_id,path) VALUES(?,?)",
                           (library_id, str(folder)))
        connection.execute("UPDATE libraries SET last_scanned=NULL WHERE id=?", (library_id,))
        return _library_view(connection, library_id)[0]


@router.delete("/libraries/{library_id}/folders/{folder_id}")
def remove_library_folder(library_id: int, folder_id: int):
    with db() as connection:
        lib = connection.execute("SELECT path FROM libraries WHERE id=?", (library_id,)).fetchone()
        if lib is None:
            raise HTTPException(404, "Library not found")
        folders = connection.execute(
            "SELECT id,path FROM library_folders WHERE library_id=? ORDER BY id",
            (library_id,)).fetchall()
        if not any(f["id"] == folder_id for f in folders):
            raise HTTPException(404, "Library folder not found")
        if len(folders) <= 1:
            raise HTTPException(409, "A library must have at least one folder")
        removed = next(f for f in folders if f["id"] == folder_id)
        replacement = next(f["path"] for f in folders if f["id"] != folder_id)
        if removed["path"] == lib["path"]:
            connection.execute("UPDATE libraries SET path=? WHERE id=?",
                               (replacement, library_id))
        connection.execute("DELETE FROM library_folders WHERE id=? AND library_id=?",
                           (folder_id, library_id))
        # Retain watched history until a rescan confirms the remaining roots.
        connection.execute("UPDATE libraries SET last_scanned=NULL WHERE id=?", (library_id,))
        return _library_view(connection, library_id)[0]


@router.post("/libraries", status_code=201)
def create_library(item: LibraryRequest):
    _validate_style(item.icon, item.font)
    try:
        folder = safe_folder(item.path)
    except (OSError, ValueError) as exc:
        raise HTTPException(400, f"Invalid folder: {exc}") from exc
    try:
        with db() as connection:
            _reject_folder_overlap(connection, folder)
            cursor = connection.execute(
                "INSERT INTO libraries (name,kind,path,icon,font,sort_order) VALUES (?,?,?,?,?,?)",
                (item.name.strip(), item.kind, str(folder), item.icon, item.font,
                 connection.execute("SELECT COALESCE(MAX(sort_order),0)+1 FROM libraries").fetchone()[0]),
            )
            connection.execute("INSERT INTO library_folders(library_id,path) VALUES(?,?)",
                               (cursor.lastrowid, str(folder)))
            return _library_view(connection, cursor.lastrowid)[0]
    except sqlite3.IntegrityError as exc:
        raise HTTPException(409, "This folder already belongs to a library") from exc


@router.delete("/libraries/{library_id}")
def delete_library(library_id: int):
    with db() as connection:
        existing = connection.execute("SELECT id FROM libraries WHERE id=?", (library_id,)).fetchone()
        if not existing:
            raise HTTPException(404, "Library not found")
        connection.execute("DELETE FROM playback_progress WHERE media_id IN (SELECT id FROM media WHERE library_id=?)", (library_id,))
        connection.execute("DELETE FROM media WHERE library_id=?", (library_id,))
        connection.execute("DELETE FROM library_folders WHERE library_id=?", (library_id,))
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
            folder_rows = connection.execute(
                "SELECT path FROM library_folders WHERE library_id=? ORDER BY id", (library_id,)
            ).fetchall()
            # Fail safely if any mounted root disappears; do not erase the catalog.
            roots = [safe_folder(row["path"]) for row in folder_rows]
            if not roots:
                raise HTTPException(400, "Library has no media folders")

            seen = set()
            errors = 0
            # Files discovered in the same scan share a first-seen timestamp.
            # Their actual modification time breaks ties instead of walk order.
            scan_added_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")
            for root in roots:
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
                          INSERT INTO media (library_id,path,title,size,mtime_ns,added_at,source_root)
                          VALUES (?,?,?,?,?,?,?)
                          ON CONFLICT(path) DO UPDATE SET library_id=excluded.library_id,
                          title=excluded.title,size=excluded.size,mtime_ns=excluded.mtime_ns,
                          source_root=excluded.source_root
                        """, (library_id, media_path, file_path.stem, stat.st_size,
                              stat.st_mtime_ns, scan_added_at, str(root)))
                    except OSError:
                        errors += 1
            # Never remove catalog entries if the scan encountered unreadable files.
            if errors == 0:
                existing = connection.execute("SELECT path FROM media WHERE library_id=?", (library_id,)).fetchall()
                for row in existing:
                    if row["path"] not in seen:
                        connection.execute("DELETE FROM playback_progress WHERE media_id IN (SELECT id FROM media WHERE library_id=? AND path=?)", (library_id, row["path"]))
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
