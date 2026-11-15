"""Read-only home shelves and future-client playback progress tracking.

Playback is not implemented yet. Progress updates are used by future clients;
the dashboard never claims an item can play until streaming exists.
"""
from collections import OrderedDict
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .catalog import episode_info, movie_info
from .library import db

router = APIRouter(prefix="/api")


class PlaybackUpdate(BaseModel):
    media_id: int = Field(gt=0)
    position_seconds: float = Field(ge=0, le=10000000)
    duration_seconds: float = Field(gt=0, le=10000000)
    completed: bool = False


def _describe(media, lib):
    try:
        if lib["kind"] == "movies":
            info = movie_info(media["path"], lib["path"])
            return {
                "kind": "movies", "title": info["title"], "year": info["year"],
                "subtitle": str(info["year"]) if info["year"] else "Movie",
                "library_id": lib["id"], "key": info["key"],
                "group": (lib["id"], info["key"]),
            }
        info = episode_info(media["path"], lib["path"])
        season = info["season"]
        episode = info["episode"]
        parts = []
        if season is not None:
            parts.append("S" + str(season).zfill(2))
        if episode is not None:
            parts.append("E" + str(episode).zfill(2))
        return {
            "kind": "tv", "title": info["title"], "year": info["year"],
            "subtitle": " · ".join(parts) if parts else "TV Show",
            "library_id": lib["id"], "key": info["key"],
            "group": (lib["id"], info["key"]),
        }
    except (ValueError, OSError):
        return None


@router.get("/home")
def home_shelves():
    recent = {"movies": OrderedDict(), "tv": OrderedDict()}
    watching = OrderedDict()
    with db() as connection:
        libs = {row["id"]: row for row in connection.execute("SELECT id,kind,path FROM libraries")}
        rows = connection.execute(
            "SELECT id,library_id,path,added_at FROM media "
            "ORDER BY added_at DESC, id DESC"
        ).fetchall()
        for row in rows:
            lib = libs.get(row["library_id"])
            if not lib:
                continue
            desc = _describe(row, lib)
            if not desc:
                continue
            key = desc["group"]
            if key not in recent[desc["kind"]]:
                recent[desc["kind"]][key] = {
                    "kind": desc["kind"], "title": desc["title"],
                    "year": desc["year"], "subtitle": desc["subtitle"],
                    "library_id": desc["library_id"], "key": desc["key"],
                    "added_at": row["added_at"],
                }

        progress_rows = connection.execute(
            "SELECT m.id,m.path,m.library_id,p.position_seconds,p.duration_seconds,"
            "p.updated_at FROM playback_progress p JOIN media m ON m.id=p.media_id "
            "WHERE p.completed=0 AND p.position_seconds>=30 "
            "AND p.position_seconds < p.duration_seconds*0.95 "
            "ORDER BY p.updated_at DESC, m.id DESC"
        ).fetchall()
        for row in progress_rows:
            lib = libs.get(row["library_id"])
            if not lib:
                continue
            desc = _describe(row, lib)
            if not desc or desc["group"] in watching:
                continue
            watching[desc["group"]] = {
                "media_id": row["id"], "kind": desc["kind"],
                "title": desc["title"], "year": desc["year"],
                "library_id": desc["library_id"], "key": desc["key"],
                "subtitle": desc["subtitle"],
                "position_seconds": row["position_seconds"],
                "duration_seconds": row["duration_seconds"],
                "progress_percent": round(row["position_seconds"] * 100 / row["duration_seconds"]),
                "updated_at": row["updated_at"],
            }
            if len(watching) >= 12:
                break

    return {
        "continue_watching": list(watching.values()),
        "recent_movies": list(recent["movies"].values())[:16],
        "recent_tv": list(recent["tv"].values())[:16],
        "totals": {
            "movies": len(recent["movies"]),
            "tv": len(recent["tv"]),
        },
        "playback_available": False,
    }


@router.put("/playback/progress")
def update_playback(item: PlaybackUpdate):
    if item.position_seconds > item.duration_seconds:
        raise HTTPException(422, "Playback position cannot exceed duration")
    completed = item.completed or item.position_seconds >= item.duration_seconds * 0.95
    with db() as connection:
        exists = connection.execute("SELECT id FROM media WHERE id=?", (item.media_id,)).fetchone()
        if not exists:
            raise HTTPException(404, "Media item not found")
        connection.execute(
            """INSERT INTO playback_progress
                (media_id,position_seconds,duration_seconds,completed,updated_at)
                VALUES (?,?,?,?,CURRENT_TIMESTAMP)
                ON CONFLICT(media_id) DO UPDATE SET
                  position_seconds=excluded.position_seconds,
                  duration_seconds=excluded.duration_seconds,
                  completed=excluded.completed,
                  updated_at=CURRENT_TIMESTAMP""",
            (item.media_id, item.position_seconds, item.duration_seconds, int(completed)),
        )
    return {"saved": True, "completed": completed}
