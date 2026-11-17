"""Local read-only media library catalog and folder configuration."""
import os
import io
import tempfile
import sqlite3
from pathlib import Path
from threading import Lock
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from fastapi.responses import FileResponse
from typing import Literal
from PIL import Image, UnidentifiedImageError

MEDIA_ROOT = Path(os.environ.get("MEDIA_ROOT", "/media")).resolve()
DB_PATH = Path(os.environ.get("DATABASE_PATH", "/data/library.sqlite3"))
VIDEO_EXTENSIONS = {".mkv", ".mp4", ".m4v", ".avi", ".mov", ".wmv", ".ts", ".webm", ".mpg", ".mpeg"}
scan_lock = Lock()
HEADER_DIRECTORY = DB_PATH.parent / 'library-headers'
HEADER_MAX_BYTES = 5 * 1024 * 1024
ICON_DIRECTORY = DB_PATH.parent / 'library-icons'
ICON_MAX_BYTES = 2 * 1024 * 1024
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
    header_x: int | None = Field(None, ge=0, le=100)
    header_y: int | None = Field(None, ge=0, le=100)
    header_scale: int | None = Field(None, ge=40, le=200)
    header_opacity: int | None = Field(None, ge=0, le=100)


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
        ("header_x", "INTEGER NOT NULL DEFAULT 75"),
        ("header_y", "INTEGER NOT NULL DEFAULT 50"),
        ("header_scale", "INTEGER NOT NULL DEFAULT 100"),
        ("header_opacity", "INTEGER NOT NULL DEFAULT 60"),
        ("header_version", "INTEGER NOT NULL DEFAULT 0"),
        ("icon_version", "INTEGER NOT NULL DEFAULT 0"),
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
    # A persistent revision lets open web/Google TV pages detect real media
    # changes without refreshing their entire poster grids every scan.
    connection.execute("""CREATE TABLE IF NOT EXISTS catalog_state (
        id INTEGER PRIMARY KEY CHECK (id=1), revision INTEGER NOT NULL DEFAULT 0
    )""")
    connection.execute("INSERT OR IGNORE INTO catalog_state(id,revision) VALUES (1,0)")
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
    result = []
    for row in rows:
        item = dict(row)
        item["sidebar_hidden"] = bool(row["sidebar_hidden"])
        item["icon_custom"] = bool(row["icon_version"] % 2)
        item["icon_image_url"] = (
            f"/api/libraries/{item['id']}/icon.png?v={item['icon_version']}"
            if item["icon_custom"] else None
        )
        item["folders"] = folders.get(row["id"], [])
        item["header_custom"] = bool(item["header_version"] % 2)
        item["header_image_url"] = (
            f"/api/libraries/{item['id']}/header.png?v={item['header_version']}"
            if item["header_custom"]
            else f"/assets/library-header-{item['kind']}.png"
        )
        result.append(item)
    return result


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
            """UPDATE libraries SET name=?,icon=?,font=?,sidebar_hidden=?,
               header_x=COALESCE(?,header_x), header_y=COALESCE(?,header_y),
               header_scale=COALESCE(?,header_scale),header_opacity=COALESCE(?,header_opacity)
               WHERE id=?""",
            (name, item.icon, item.font, int(item.sidebar_hidden),
             item.header_x, item.header_y, item.header_scale, item.header_opacity,
             library_id))
        return _library_view(connection, library_id)[0]


def _icon_path(library_id: int):
    return ICON_DIRECTORY / f"{library_id}.png"


@router.get("/libraries/{library_id}/icon.png")
def library_icon_image(library_id: int):
    with db() as connection:
        row = connection.execute(
            "SELECT icon_version FROM libraries WHERE id=?", (library_id,)
        ).fetchone()
    if not row:
        raise HTTPException(404, "Library not found")
    if row["icon_version"] % 2 == 0:
        raise HTTPException(404, "This library uses its default icon")
    image = _icon_path(library_id)
    if not image.is_file():
        raise HTTPException(404, "Custom library icon not found")
    return FileResponse(image, media_type="image/png", headers={
        "Cache-Control": "no-cache", "X-Content-Type-Options": "nosniff"
    })


@router.put("/libraries/{library_id}/icon.png")
async def upload_library_icon(library_id: int, request: Request):
    """Validate, resize, and atomically store a user-supplied library icon."""
    with db() as connection:
        if not connection.execute("SELECT 1 FROM libraries WHERE id=?", (library_id,)).fetchone():
            raise HTTPException(404, "Library not found")
    if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "image/png":
        raise HTTPException(415, "Upload a PNG icon")
    parts, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > ICON_MAX_BYTES:
            raise HTTPException(413, "Icon exceeds 2 MB maximum")
        parts.append(chunk)
    data = b"".join(parts)
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise HTTPException(415, "The file is not a PNG")
    try:
        with Image.open(io.BytesIO(data)) as source:
            if source.format != "PNG" or min(source.size) < 32:
                raise ValueError("PNG must be at least 32 pixels in both dimensions")
            if max(source.size) > 4096:
                raise ValueError("PNG dimensions must not exceed 4096 pixels")
            image = source.convert("RGBA")
            image.thumbnail((256, 256), Image.Resampling.LANCZOS)
            # Square canvas preserves non-square artwork without distortion.
            canvas = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
            canvas.alpha_composite(image, ((256-image.width)//2, (256-image.height)//2))
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError, Image.DecompressionBombError) as error:
        raise HTTPException(422, f"Invalid PNG icon: {error}") from error
    ICON_DIRECTORY.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=".icon-", suffix=".png", dir=ICON_DIRECTORY)
    try:
        with os.fdopen(handle, "wb") as stream:
            canvas.save(stream, "PNG", optimize=True)
        with db() as connection:
            row = connection.execute("SELECT icon_version FROM libraries WHERE id=?", (library_id,)).fetchone()
            if not row:
                raise HTTPException(404, "Library not found")
            os.replace(temporary, _icon_path(library_id))
            version = row["icon_version"] + (1 if row["icon_version"] % 2 == 0 else 2)
            connection.execute("UPDATE libraries SET icon_version=? WHERE id=?",
                               (version, library_id))
            return _library_view(connection, library_id)[0]
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@router.delete("/libraries/{library_id}/icon.png")
def revert_library_icon(library_id: int):
    with db() as connection:
        row = connection.execute("SELECT icon_version FROM libraries WHERE id=?", (library_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Library not found")
        if row["icon_version"] % 2:
            connection.execute("UPDATE libraries SET icon_version=icon_version+1 WHERE id=?",
                               (library_id,))
        result = _library_view(connection, library_id)[0]
    _icon_path(library_id).unlink(missing_ok=True)
    return result


def _header_path(library_id: int):
    return HEADER_DIRECTORY / f"{library_id}.png"


@router.get("/libraries/{library_id}/header.png")
def library_header_image(library_id: int):
    with db() as connection:
        row = connection.execute(
            "SELECT header_version FROM libraries WHERE id=?", (library_id,)
        ).fetchone()
    if not row:
        raise HTTPException(404, "Library not found")
    if row["header_version"] % 2 == 0:
        raise HTTPException(404, "This library uses the default header")
    image = _header_path(library_id)
    if not image.is_file():
        raise HTTPException(404, "Custom header not found")
    return FileResponse(image, media_type="image/png",
                        headers={"Cache-Control": "no-cache", "X-Content-Type-Options": "nosniff"})


@router.put("/libraries/{library_id}/header.png")
async def upload_library_header(library_id: int, request: Request):
    """Accept only small, genuine transparent PNGs. Never write to media folders."""
    with db() as connection:
        if not connection.execute(
            "SELECT 1 FROM libraries WHERE id=?", (library_id,)
        ).fetchone():
            raise HTTPException(404, "Library not found")
    if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "image/png":
        raise HTTPException(415, "Upload a transparent PNG image")
    parts, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > HEADER_MAX_BYTES:
            raise HTTPException(413, "Image exceeds 5 MB maximum")
        parts.append(chunk)
    data = b"".join(parts)
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise HTTPException(415, "The file is not a PNG")
    try:
        with Image.open(io.BytesIO(data)) as source:
            if source.format != "PNG" or source.width < 32 or source.height < 32:
                raise ValueError("Invalid PNG")
            if source.width > 4096 or source.height > 4096:
                raise HTTPException(413, "PNG dimensions must not exceed 4096 pixels")
            if not ("A" in source.getbands() or "transparency" in source.info):
                raise ValueError("PNG needs transparency")
            image = source.convert("RGBA")
            if image.getchannel("A").getextrema()[0] == 255:
                raise ValueError("PNG needs transparent pixels")
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError, Image.DecompressionBombError) as error:
        raise HTTPException(422, f"Invalid transparent PNG: {error}") from error
    HEADER_DIRECTORY.mkdir(parents=True, exist_ok=True)
    # Strip EXIF and ancillary metadata by re-encoding the decoded image.
    handle, temporary = tempfile.mkstemp(prefix=".header-", suffix=".png", dir=HEADER_DIRECTORY)
    try:
        with os.fdopen(handle, "wb") as stream:
            image.save(stream, "PNG", optimize=True)
        with db() as connection:
            row = connection.execute(
                "SELECT header_version FROM libraries WHERE id=?", (library_id,)
            ).fetchone()
            if not row:
                raise HTTPException(404, "Library not found")
            os.replace(temporary, _header_path(library_id))
            # Odd revisions = custom image; even revisions = built-in image.
            version = row["header_version"] + (1 if row["header_version"] % 2 == 0 else 2)
            connection.execute(
                "UPDATE libraries SET header_version=? WHERE id=?",
                (version, library_id)
            )
            return _library_view(connection, library_id)[0]
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@router.delete("/libraries/{library_id}/header.png")
def revert_library_header(library_id: int):
    with db() as connection:
        row = connection.execute(
            "SELECT header_version FROM libraries WHERE id=?", (library_id,)
        ).fetchone()
        if not row:
            raise HTTPException(404, "Library not found")
        if row["header_version"] % 2:
            connection.execute(
                "UPDATE libraries SET header_version=header_version+1 WHERE id=?",
                (library_id,),
            )
        result = _library_view(connection, library_id)[0]
    _header_path(library_id).unlink(missing_ok=True)
    return result


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
        connection.execute("UPDATE catalog_state SET revision=revision+1 WHERE id=1")
    _header_path(library_id).unlink(missing_ok=True)
    _icon_path(library_id).unlink(missing_ok=True)
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
            # Count media changes, not the housekeeping last_scanned update.
            media_changes_before = connection.total_changes
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
                          WHERE media.library_id IS NOT excluded.library_id
                             OR media.title IS NOT excluded.title
                             OR media.size IS NOT excluded.size
                             OR media.mtime_ns IS NOT excluded.mtime_ns
                             OR media.source_root IS NOT excluded.source_root
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
            changed = connection.total_changes > media_changes_before
            if changed:
                connection.execute("UPDATE catalog_state SET revision=revision+1 WHERE id=1")
            now = datetime.now(timezone.utc).isoformat()
            connection.execute("UPDATE libraries SET last_scanned=? WHERE id=?", (now, library_id))
            return {"found": len(seen), "errors": errors, "last_scanned": now,
                    "changed": changed}
    finally:
        scan_lock.release()


@router.get("/libraries/{library_id}/media")
def media(library_id: int):
    with db() as connection:
        return [dict(row) for row in connection.execute(
            "SELECT id,path,title,size FROM media WHERE library_id=? ORDER BY title LIMIT 500",
            (library_id,)
        )]
