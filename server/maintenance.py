"""Scheduled, bounded local maintenance for One-Eyed Willie.

Nothing in the mounted media library is modified. Video previews and analyses are
opt-in; retained metadata, manually fixed matches and playback history are safe.
"""
import hashlib
import json
import logging
import os
import re
import shutil
import sqlite3
import subprocess
import threading
import time
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .library import db, scan_library, VIDEO_EXTENSIONS
from .playback import _item

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/maintenance")
DATA = Path(os.environ.get("MAINTENANCE_DIR", "/data/maintenance"))
PREVIEWS = DATA / "previews"
MANAGED_BUNDLES = DATA / "bundles"
LOCK = threading.RLock()
WORKING = threading.Lock()
WEEK = 7 * 86400
THREE_DAYS = 3 * 86400
IMAGE_ID = re.compile(r"^[a-f0-9]{24}$")
MAX_ANALYSIS = 40
MAX_EXTENSIVE = 3
MAX_PREVIEWS = 4
MAX_PREVIEW_BYTES = 800000
DEFAULTS = {
    "optimize_database": True,
    "remove_old_bundles": True,
    "remove_old_cache_files": True,
    "refresh_local_metadata": True,
    "update_all_libraries": True,
    "upgrade_media_analysis": True,
    "refresh_library_metadata": True,
    "extensive_media_analysis": True,
    "video_preview_thumbnails": True,
}
CADENCE = {
    "optimize_database": WEEK,
    "remove_old_bundles": WEEK,
    "remove_old_cache_files": WEEK,
    "refresh_local_metadata": THREE_DAYS,
    "update_all_libraries": WEEK,
    "upgrade_media_analysis": WEEK,
    "refresh_library_metadata": THREE_DAYS,
    "extensive_media_analysis": WEEK,
    "video_preview_thumbnails": 86400,
}
# Run at 4 AM Central time, including daylight-saving transitions.
try:
    MAINTENANCE_ZONE = ZoneInfo("America/Chicago")
except ZoneInfoNotFoundError:
    MAINTENANCE_ZONE = timezone(timedelta(hours=-6))
    logger.warning("System time-zone data unavailable; using fixed Central Standard Time")


class Settings(BaseModel):
    optimize_database: bool = True
    remove_old_bundles: bool = True
    remove_old_cache_files: bool = True
    refresh_local_metadata: bool = True
    update_all_libraries: bool = True
    upgrade_media_analysis: bool = True
    refresh_library_metadata: bool = True
    extensive_media_analysis: bool = True
    video_preview_thumbnails: bool = True


def _tables(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS maintenance_status (
      task TEXT PRIMARY KEY, last_completed INTEGER NOT NULL DEFAULT 0,
      last_result TEXT NOT NULL DEFAULT ''
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS media_analysis (
      media_id INTEGER PRIMARY KEY, fingerprint TEXT NOT NULL,
      payload TEXT NOT NULL, analyzed_at INTEGER NOT NULL
    )""")


def settings():
    with db() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS maintenance_settings (name TEXT PRIMARY KEY, enabled INTEGER NOT NULL)")
        values = {row["name"]: bool(row["enabled"]) for row in
                  conn.execute("SELECT name,enabled FROM maintenance_settings")}
    return {**DEFAULTS, **{key: enabled for key, enabled in values.items() if key in DEFAULTS}}


@router.get("/settings")
def get_settings():
    with db() as conn:
        _tables(conn)
        records = {row["task"]: dict(row) for row in
                   conn.execute("SELECT task,last_completed,last_result FROM maintenance_status")}
    return {"settings": settings(), "cadence_seconds": CADENCE,
            "last_runs": records, "running": WORKING.locked(),
            "next_window": "04:00 America/Chicago (Central time), each enabled task when due",
            "maintenance_hour": 4, "timezone": "America/Chicago"}


@router.put("/settings")
def update_settings(request: Settings):
    values = request.model_dump()
    with db() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS maintenance_settings (name TEXT PRIMARY KEY, enabled INTEGER NOT NULL)")
        conn.executemany(
            "INSERT INTO maintenance_settings(name,enabled) VALUES(?,?) "
            "ON CONFLICT(name) DO UPDATE SET enabled=excluded.enabled",
            [(name, int(value)) for name, value in values.items()],
        )
    return get_settings()


def _media_rows(limit=MAX_ANALYSIS, offset=0):
    with db() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT m.id,m.path,m.size,m.mtime_ns FROM media m "
            "JOIN libraries l ON l.id=m.library_id "
            "WHERE l.kind IN ('tv','movies') ORDER BY m.id LIMIT ? OFFSET ?", (limit, offset)
        )]


def _next_media_batch(task, count):
    """Move a task-specific cursor across the library rather than revisiting the first movies."""
    with db() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS maintenance_cursor (task TEXT PRIMARY KEY, offset INTEGER NOT NULL)")
        total = conn.execute("SELECT COUNT(*) FROM media").fetchone()[0]
        row = conn.execute("SELECT offset FROM maintenance_cursor WHERE task=?", (task,)).fetchone()
        offset = (row["offset"] if row else 0) % max(1, total)
        count = min(count, total)
        query = ("SELECT m.id,m.path,m.size,m.mtime_ns FROM media m "
                 "JOIN libraries l ON l.id=m.library_id "
                 "WHERE l.kind IN ('tv','movies') ORDER BY m.id LIMIT ? OFFSET ?")
        batch = [dict(row) for row in conn.execute(query, (count, offset))]
        if len(batch) < count and total > len(batch):
            batch += [dict(row) for row in conn.execute(query, (count-len(batch), 0))]
        conn.execute("INSERT INTO maintenance_cursor(task,offset) VALUES(?,?) "
                     "ON CONFLICT(task) DO UPDATE SET offset=excluded.offset",
                     (task, (offset+len(batch)) % max(1, total)))
    return batch


def _safe_media(row):
    try:
        _, path = _item(row["id"])
        return path if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS else None
    except (OSError, HTTPException, ValueError):
        return None


def _probe(row, extensive=False):
    path = _safe_media(row)
    if not path:
        return None
    command = ["/usr/bin/ffprobe", "-v", "error", "-show_streams",
               "-show_format", "-of", "json", str(path)]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=20,
                                check=True)
        info = json.loads(result.stdout[:160000])
        payload = {
            "duration": (info.get("format") or {}).get("duration"),
            "streams": [{"codec": s.get("codec_name"), "type": s.get("codec_type"),
                         "width": s.get("width"), "height": s.get("height"),
                         "channels": s.get("channels")}
                        for s in info.get("streams", [])[:20]]
        }
        if extensive:
            # Sample only one minute, one concurrent FFmpeg job, lowest priority.
            ffmpeg = ["nice", "-n", "15", "/usr/bin/ffmpeg", "-nostdin",
                      "-v", "info", "-t", "60", "-i", str(path),
                      "-map", "0:v:0?", "-map", "0:a:0?",
                      "-vf", "blackdetect=d=0.5:pix_th=0.10",
                      "-af", "volumedetect,silencedetect=noise=-35dB:d=1",
                      "-f", "null", "-"]
            try:
                deep = subprocess.run(ffmpeg, capture_output=True, text=True, timeout=90)
                tail = deep.stderr[-10000:]
                found = re.search(r"mean_volume:\s*(-?[0-9.]+) dB", tail)
                payload["sample_mean_db"] = float(found.group(1)) if found else None
                payload["sample_black_segments"] = min(100, tail.count("black_start:"))
                payload["sample_silence_segments"] = min(100, tail.count("silence_start:"))
            except (OSError, subprocess.TimeoutExpired):
                payload["sample_mean_db"] = None
                payload["sample_black_segments"] = None
                payload["sample_silence_segments"] = None
        with db() as conn:
            _tables(conn)
            fingerprint = f'{row["size"]}:{row["mtime_ns"]}'
            conn.execute(
                "INSERT INTO media_analysis(media_id,fingerprint,payload,analyzed_at) VALUES(?,?,?,?) "
                "ON CONFLICT(media_id) DO UPDATE SET fingerprint=excluded.fingerprint,"
                "payload=excluded.payload,analyzed_at=excluded.analyzed_at",
                (row["id"], fingerprint, json.dumps(payload), int(time.time())),
            )
        return payload
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError, ValueError):
        logger.warning("Video metadata analysis failed for media ID %s", row["id"])
        return None


def _preview_key(row):
    return hashlib.sha256(f'{row["id"]}:{row["size"]}:{row["mtime_ns"]}'.encode()).hexdigest()[:24]


def _create_preview(row):
    path = _safe_media(row)
    if path is None:
        return False
    token = _preview_key(row)
    target = PREVIEWS / token
    if (target / "000.jpg").is_file():
        return False
    try:
        PREVIEWS.mkdir(parents=True, exist_ok=True)
        target.mkdir(mode=0o700, exist_ok=True)
        duration = 0
        with db() as conn:
            _tables(conn)
            record = conn.execute("SELECT payload FROM media_analysis WHERE media_id=?", (row["id"],)).fetchone()
        if record:
            duration = float(json.loads(record["payload"]).get("duration") or 0)
        # Never process entire movies if duration could not be determined.
        if duration <= 15:
            info = _probe(row)
            duration = float(info.get("duration") or 0) if info else 0
        if duration <= 15:
            return False
        success = 0
        for index in range(6):
            if not (target / f"{index:03}.jpg").exists():
                offset = max(1, duration * (index + 1) / 7)
                command = ["nice", "-n", "15", "/usr/bin/ffmpeg", "-nostdin",
                           "-v", "error", "-ss", str(offset), "-i", str(path),
                           "-frames:v", "1", "-vf", "scale=320:-2",
                           "-q:v", "7", "-y", str(target / f"{index:03}.jpg")]
                try:
                    subprocess.run(command, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, timeout=35, check=True)
                    if (target / f"{index:03}.jpg").stat().st_size <= MAX_PREVIEW_BYTES:
                        success += 1
                    else:
                        (target / f"{index:03}.jpg").unlink(missing_ok=True)
                except (OSError, subprocess.TimeoutExpired, subprocess.CalledProcessError):
                    pass
        if success == 0:
            shutil.rmtree(target, ignore_errors=True)
        return bool(success)
    except OSError:
        return False


def _safe_clean(directory, cutoff, allowed_suffixes=None):
    if not directory.is_dir() or directory.is_symlink():
        return 0
    removed = 0
    for entry in list(directory.iterdir())[:20000]:
        try:
            if entry.is_symlink() or entry.stat().st_mtime > cutoff:
                continue
            if entry.is_file() and (allowed_suffixes is None or entry.suffix in allowed_suffixes):
                entry.unlink()
                removed += 1
            elif entry.is_dir() and allowed_suffixes is None:
                shutil.rmtree(entry)
                removed += 1
        except OSError:
            continue
    return removed


def _run_task(name):
    now = time.time()
    if name == "optimize_database":
        # Short locks: checkpoint WAL before VACUUM; separate connection required.
        with db() as conn:
            conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
        conn = db()
        try:
            conn.execute("PRAGMA optimize")
            conn.commit()
            conn.execute("VACUUM")
        finally:
            conn.close()
        return "Database optimized"
    if name == "remove_old_bundles":
        return f"{_safe_clean(MANAGED_BUNDLES, now - 7 * 86400)} obsolete generated bundles removed"
    if name == "remove_old_cache_files":
        from .hls import ROOT as HLS_ROOT, ACTIVE, LOCK as HLS_LOCK
        from .subtitles import CACHE as SUBTITLE_CACHE
        count = _safe_clean(SUBTITLE_CACHE, now - 30 * 86400, {".vtt"})
        # Downloaded SRT subtitle files are intentionally retained.
        # Keep precomputed artwork and thumbnails: they are referenced by the\n        # persistent poster index and should not be re-downloaded weekly.
        with HLS_LOCK:
            active = {entry.directory.name for entry in ACTIVE.values()}
            if HLS_ROOT.is_dir():
                for folder in HLS_ROOT.iterdir():
                    if folder.name not in active and folder.is_dir() and not folder.is_symlink() and folder.stat().st_mtime < now - 86400:
                        shutil.rmtree(folder, ignore_errors=True)
                        count += 1
        return f"{count} stale cache entries removed"
    if name == "update_all_libraries":
        with db() as conn:
            ids = [r["id"] for r in conn.execute("SELECT id FROM libraries")]
        done = 0
        for library_id in ids:
            try:
                scan_library(library_id)
                done += 1
            except HTTPException as exc:
                if exc.status_code == 409:
                    break
                logger.warning("Maintenance scan failed: library %s", library_id)
        return f"{done}/{len(ids)} libraries scanned"
    if name in ("refresh_local_metadata", "refresh_library_metadata"):
        # Expire cached provider lookups but keep user-selected matches intact.
        with db() as conn:
            exists = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='metadata_cache'").fetchone()
            if not exists:
                return "No metadata cache yet"
            if name == "refresh_local_metadata":
                result = conn.execute("DELETE FROM metadata_cache WHERE fetched_at < ?", (int(now - THREE_DAYS),))
            else:
                result = conn.execute("UPDATE metadata_cache SET fetched_at=0 WHERE cache_key LIKE 'tv:%' OR cache_key LIKE 'tvmaze:%' OR cache_key LIKE 'season:%'")
            return f"{result.rowcount} metadata cache entries queued for refresh on next use"
    if name in ("upgrade_media_analysis", "extensive_media_analysis"):
        extensive = name == "extensive_media_analysis"
        rows = _next_media_batch(name, MAX_EXTENSIVE if extensive else MAX_ANALYSIS)
        done = 0
        for row in rows:
            if extensive and done >= MAX_EXTENSIVE:
                break
            if not extensive and done >= MAX_ANALYSIS:
                break
            with db() as conn:
                _tables(conn)
                record = conn.execute("SELECT fingerprint FROM media_analysis WHERE media_id=?", (row["id"],)).fetchone()
            fingerprint = f'{row["size"]}:{row["mtime_ns"]}'
            if not extensive and record and record["fingerprint"] == fingerprint:
                continue
            if _probe(row, extensive=extensive):
                done += 1
        return f"{done} media files analyzed (max {MAX_EXTENSIVE if extensive else MAX_ANALYSIS} per maintenance run)"
    if name == "video_preview_thumbnails":
        done = 0
        for row in _next_media_batch(name, 20):
            if done >= MAX_PREVIEWS:
                break
            if (PREVIEWS / _preview_key(row) / "000.jpg").is_file():
                continue
            if _create_preview(row):
                done += 1
        return f"{done} new preview sets created (max {MAX_PREVIEWS} per run)"
    return "Skipped"


def _due(name, last, now):
    return now - int(last) >= CADENCE[name]


def run_due(now=None, force=False):
    if not WORKING.acquire(blocking=False):
        return False
    try:
        now = int(now or time.time())
        enabled = settings()
        with db() as conn:
            _tables(conn)
            runs = {row["task"]: row["last_completed"] for row in
                    conn.execute("SELECT task,last_completed FROM maintenance_status")}
        for name in CADENCE:
            if not enabled[name] or (not force and not _due(name, runs.get(name, 0), now)):
                continue
            try:
                outcome = _run_task(name)
            except Exception:
                logger.exception("Maintenance task %s failed", name)
                continue
            with db() as conn:
                _tables(conn)
                conn.execute("INSERT INTO maintenance_status(task,last_completed,last_result) VALUES(?,?,?) "
                             "ON CONFLICT(task) DO UPDATE SET last_completed=excluded.last_completed,"
                             "last_result=excluded.last_result", (name, now, outcome))
        return True
    finally:
        WORKING.release()


def maintenance_loop(stop):
    # First run at the next scheduled maintenance hour; do not saturate
    # disks or CPU immediately after a server restart.
    while not stop.wait(60):
        local = datetime.now(MAINTENANCE_ZONE)
        if local.hour == 4:
            run_due()


@router.post("/run")
def run_maintenance():
    if WORKING.locked():
        raise HTTPException(409, "Maintenance is already running")
    threading.Thread(target=run_due, kwargs={"force": True}, daemon=True,
                     name="manual-maintenance").start()
    return {"started": True}


def _run_previews_only():
    if not WORKING.acquire(blocking=False):
        return False
    try:
        result = _run_task("video_preview_thumbnails")
        with db() as conn:
            _tables(conn)
            conn.execute("INSERT INTO maintenance_status(task,last_completed,last_result) VALUES(?,?,?) "
                         "ON CONFLICT(task) DO UPDATE SET last_completed=excluded.last_completed,last_result=excluded.last_result",
                         ("video_preview_thumbnails", int(time.time()), result))
        return True
    except Exception:
        logger.exception("Preview generation failed")
        return False
    finally:
        WORKING.release()


@router.post("/previews/generate")
def start_preview_generation():
    if not settings()["video_preview_thumbnails"]:
        raise HTTPException(409, "Enable previews in maintenance settings first")
    if WORKING.locked():
        raise HTTPException(409, "Maintenance or previews are already running")
    threading.Thread(target=_run_previews_only, daemon=True,
                     name="preview-generation").start()
    return {"started": True, "limit": MAX_PREVIEWS}


@router.get("/preview/{media_id}")
def preview_info(media_id: int):
    if not settings()["video_preview_thumbnails"]:
        return {"enabled": False, "images": []}
    row, path = _item(media_id)
    stat = path.stat()
    entry = {"id": media_id, "size": stat.st_size, "mtime_ns": stat.st_mtime_ns}
    token = _preview_key(entry)
    return {"enabled": True, "images": [
        f"/api/maintenance/preview/{media_id}/{i:03}.jpg"
        for i in range(6) if (PREVIEWS / token / f"{i:03}.jpg").is_file()
    ]}


@router.get("/preview/{media_id}/{filename}")
def preview_image(media_id: int, filename: str):
    if not settings()["video_preview_thumbnails"]:
        raise HTTPException(404, "Previews disabled")
    if not re.fullmatch(r"00[0-5]\.jpg", filename):
        raise HTTPException(404, "Preview not found")
    _, path = _item(media_id)
    stat = path.stat()
    token = _preview_key({"id": media_id, "size": stat.st_size, "mtime_ns": stat.st_mtime_ns})
    target = PREVIEWS / token / filename
    if target.is_symlink() or not target.is_file() or target.stat().st_size > MAX_PREVIEW_BYTES:
        raise HTTPException(404, "Preview unavailable")
    return FileResponse(target, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=604800"})
