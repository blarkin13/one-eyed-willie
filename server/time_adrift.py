"""Time Adrift: opt-in, local per-video pause and replay-time accounting.

An event identifier makes retransmissions idempotent. Video identifiers come
from the user's existing library; no media files are modified or uploaded.
"""
import sqlite3
from typing import Literal
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from .library import db

router = APIRouter(prefix="/api/time-adrift")


class TimeAdriftSettings(BaseModel):
    enabled: bool = False


class TimeAdriftEvent(BaseModel):
    event_id: str = Field(pattern=r"^[a-f0-9]{24,64}$")
    kind: Literal["pause", "rewind"]
    seconds: float = Field(gt=0, le=86400)


def _setup(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    conn.execute("""CREATE TABLE IF NOT EXISTS time_adrift_totals (
      media_id INTEGER PRIMARY KEY,
      paused_ms INTEGER NOT NULL DEFAULT 0,
      rewound_ms INTEGER NOT NULL DEFAULT 0,
      pause_count INTEGER NOT NULL DEFAULT 0,
      rewind_count INTEGER NOT NULL DEFAULT 0
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS time_adrift_events (
      event_id TEXT PRIMARY KEY,
      media_id INTEGER NOT NULL,
      kind TEXT NOT NULL,
      elapsed_ms INTEGER NOT NULL
    )""")


def _enabled(conn):
    row = conn.execute(
        "SELECT value FROM app_settings WHERE key='time_adrift_enabled'"
    ).fetchone()
    return row is not None and row["value"] == "true"


def _totals(conn, media_id):
    row = conn.execute(
        "SELECT paused_ms, rewound_ms, pause_count, rewind_count "
        "FROM time_adrift_totals WHERE media_id=?", (media_id,)
    ).fetchone()
    return {
        "media_id": media_id,
        "paused_seconds": round(row["paused_ms"] / 1000, 3) if row else 0.0,
        "rewound_seconds": round(row["rewound_ms"] / 1000, 3) if row else 0.0,
        "pause_count": row["pause_count"] if row else 0,
        "rewind_count": row["rewind_count"] if row else 0,
    }


@router.get("/settings")
def get_settings():
    with db() as conn:
        _setup(conn)
        return {"enabled": _enabled(conn)}


@router.put("/settings")
def save_settings(value: TimeAdriftSettings):
    with db() as conn:
        _setup(conn)
        conn.execute(
            "INSERT INTO app_settings(key,value) VALUES('time_adrift_enabled',?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            ("true" if value.enabled else "false",)
        )
        conn.commit()
    return value.model_dump()


@router.get("/media/{media_id}")
def get_media_totals(media_id: int):
    if media_id < 1:
        raise HTTPException(404, "Video not found")
    with db() as conn:
        _setup(conn)
        if conn.execute("SELECT id FROM media WHERE id=?", (media_id,)).fetchone() is None:
            raise HTTPException(404, "Video not found")
        return {"enabled": _enabled(conn), **_totals(conn, media_id)}


@router.post("/media/{media_id}/events")
def record_event(media_id: int, event: TimeAdriftEvent):
    if media_id < 1:
        raise HTTPException(404, "Video not found")
    elapsed = round(event.seconds * 1000)
    if elapsed < 1:
        raise HTTPException(422, "Duration too short")
    with db() as conn:
        _setup(conn)
        if conn.execute("SELECT id FROM media WHERE id=?", (media_id,)).fetchone() is None:
            raise HTTPException(404, "Video not found")
        if not _enabled(conn):
            return {"enabled": False, **_totals(conn, media_id)}
        try:
            conn.execute("INSERT INTO time_adrift_events(event_id,media_id,kind,elapsed_ms)"
                         " VALUES(?,?,?,?)",
                         (event.event_id, media_id, event.kind, elapsed))
        except sqlite3.IntegrityError:
            # A network retry must never add the same pause/rewind twice.
            return {"enabled": True, **_totals(conn, media_id)}
        if event.kind == "pause":
            conn.execute(
                "INSERT INTO time_adrift_totals(media_id,paused_ms,pause_count) VALUES(?,?,1) "
                "ON CONFLICT(media_id) DO UPDATE SET "
                "paused_ms=paused_ms+excluded.paused_ms,pause_count=pause_count+1",
                (media_id, elapsed)
            )
        else:
            conn.execute(
                "INSERT INTO time_adrift_totals(media_id,rewound_ms,rewind_count) VALUES(?,?,1) "
                "ON CONFLICT(media_id) DO UPDATE SET "
                "rewound_ms=rewound_ms+excluded.rewound_ms,rewind_count=rewind_count+1",
                (media_id, elapsed)
            )
        conn.commit()
        return {"enabled": True, **_totals(conn, media_id)}
