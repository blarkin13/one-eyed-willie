"""Cached read-only FFprobe metadata for deciding playback before opening a stream."""
import json
import math
import sqlite3
import subprocess
import time
from functools import lru_cache
from pathlib import Path

from .library import db, scan_lock

FFPROBE = "/usr/bin/ffprobe"


@lru_cache(maxsize=2048)
def _inspect(path: str, size: int, mtime_ns: int):
    try:
        result = subprocess.run(
            [FFPROBE, "-v", "error", "-show_entries",
             "format=duration,bit_rate:stream=codec_type,codec_name,profile,width,height,"
             "pix_fmt,channels,sample_rate,bit_rate,color_transfer,color_primaries",
             "-of", "json", path],
            capture_output=True, text=True, timeout=8, check=False,
        )
        if result.returncode or len(result.stdout) > 200_000:
            return {}
        payload = json.loads(result.stdout)
        streams = payload.get("streams") or []
        video = next((s for s in streams if s.get("codec_type") == "video"), {})
        audio = next((s for s in streams if s.get("codec_type") == "audio"), {})
        if not video:
            return {}
        fmt = payload.get("format") or {}
        duration = float(fmt.get("duration") or 0)
        if not math.isfinite(duration) or duration < 0:
            duration = 0
        return {
            "container": Path(path).suffix.lower().lstrip("."),
            "video_codec": str(video.get("codec_name") or "").lower(),
            "audio_codec": str(audio.get("codec_name") or "").lower(),
            "video_profile": str(video.get("profile") or ""),
            "pixel_format": str(video.get("pix_fmt") or ""),
            "width": int(video.get("width") or 0),
            "height": int(video.get("height") or 0),
            "audio_channels": int(audio.get("channels") or 0),
            "bitrate": int(fmt.get("bit_rate") or 0),
            "duration": duration,
            "hdr_transfer": str(video.get("color_transfer") or ""),
        }
    except (OSError, ValueError, TypeError, subprocess.TimeoutExpired, OverflowError):
        return {}



def _table(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS media_playback_profiles (
        path TEXT PRIMARY KEY,
        size INTEGER NOT NULL,
        mtime_ns INTEGER NOT NULL,
        metadata_json TEXT NOT NULL
    )""")


def inspect_media(file: Path):
    """Return a persisted codec profile, invalidating it on file changes."""
    try:
        stat = file.stat()
    except OSError:
        return {}
    path = str(file)
    try:
        with db() as conn:
            _table(conn)
            row = conn.execute(
                "SELECT metadata_json FROM media_playback_profiles "
                "WHERE path=? AND size=? AND mtime_ns=?",
                (path, stat.st_size, stat.st_mtime_ns),
            ).fetchone()
        if row:
            return json.loads(row["metadata_json"])
    except (OSError, sqlite3.Error, ValueError, TypeError):
        pass
    result = _inspect(path, stat.st_size, stat.st_mtime_ns)
    try:
        with db() as conn:
            _table(conn)
            conn.execute(
                "INSERT INTO media_playback_profiles(path,size,mtime_ns,metadata_json) "
                "VALUES(?,?,?,?) ON CONFLICT(path) DO UPDATE SET "
                "size=excluded.size,mtime_ns=excluded.mtime_ns,"
                "metadata_json=excluded.metadata_json",
                (path, stat.st_size, stat.st_mtime_ns, json.dumps(result)),
            )
    except (OSError, sqlite3.Error):
        pass
    return result


def warm_media_profiles(stop):
    """Pre-probe indexed files in a quiet background thread, never on catalog load."""
    if stop.wait(20):
        return
    while not stop.is_set():
        if scan_lock.locked():
            stop.wait(10)
            continue
        try:
            with db() as conn:
                _table(conn)
                rows = conn.execute("""
                    SELECT m.path FROM media m
                    JOIN libraries l ON l.id=m.library_id
                    LEFT JOIN media_playback_profiles p ON p.path=m.path
                    WHERE l.kind IN ('movies','tv')
                      AND (p.path IS NULL OR p.size!=m.size OR p.mtime_ns!=m.mtime_ns)
                    ORDER BY m.added_at DESC LIMIT 20
                """).fetchall()
            if not rows:
                stop.wait(45)
                continue
            for row in rows:
                if stop.is_set():
                    return
                inspect_media(Path(row["path"]))
                # Avoid saturating a small NUC while browsing or transcoding.
                if stop.wait(0.2):
                    return
        except (sqlite3.Error, OSError):
            stop.wait(30)
