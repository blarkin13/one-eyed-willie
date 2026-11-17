"""Home shelves and local playback progress tracking."""
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
    duration_seconds: float = Field(ge=0, le=10000000)
    completed: bool = False
    replaying: bool = False  # An explicitly restarted, previously watched episode


def _describe(media, lib):
    try:
        if lib["kind"] == "movies":
            info = movie_info(media["path"], media["source_root"] or lib["path"])
            return {
                "kind": "movies", "title": info["title"], "year": info["year"],
                "subtitle": str(info["year"]) if info["year"] else "Movie",
                "library_id": lib["id"], "key": info["key"],
                "group": (lib["id"], info["key"]),
            }
        info = episode_info(media["path"], media["source_root"] or lib["path"])
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


def _progress_revision(connection):
    """Lightweight fingerprint of progress changes for active Home pages.

    Catalog revisions only change when media is scanned; playback updates
    must also invalidate Continue Watching. Include aggregate positions to
    distinguish checkpoints within the same SQLite timestamp second.
    """
    row = connection.execute(
        "SELECT COUNT(*), COALESCE(MAX(updated_at), ''), "
        "COALESCE(SUM(position_seconds), 0), "
        "COALESCE(SUM(duration_seconds), 0), "
        "COALESCE(SUM(completed), 0) FROM playback_progress"
    ).fetchone()
    return [row[0], row[1], round(row[2], 3), round(row[3], 3), row[4]]


@router.get("/home/revision")
def home_revision():
    with db() as connection:
        catalog = connection.execute(
            "SELECT revision FROM catalog_state WHERE id=1"
        ).fetchone()[0]
        progress = _progress_revision(connection)
    return {"catalog_revision": catalog, "progress_revision": progress}


@router.get("/home")
def home_shelves():
    recent = {"movies": OrderedDict(), "tv": OrderedDict()}
    # Candidates consist of (last activity, priority, media id, card).
    # A completed TV episode is replaced by the next available unwatched one.
    candidates = []
    in_progress_groups = set()
    tv_episodes = {}
    descriptions = {}
    with db() as connection:
        revision = connection.execute(
            "SELECT revision FROM catalog_state WHERE id=1"
        ).fetchone()[0]
        progress_revision = _progress_revision(connection)
        libs = {row["id"]: row for row in connection.execute("SELECT id,kind,path FROM libraries")}
        progress = {row["media_id"]: dict(row) for row in connection.execute(
            "SELECT media_id,position_seconds,duration_seconds,completed,updated_at "
            "FROM playback_progress"
        )}
        watched_ids = {media_id for media_id, entry in progress.items() if entry["completed"]}
        rows = connection.execute(
            "SELECT id,library_id,path,source_root,added_at,mtime_ns FROM media "
            "ORDER BY added_at DESC, mtime_ns DESC, id DESC"
        ).fetchall()
        for row in rows:
            lib = libs.get(row["library_id"])
            if not lib:
                continue
            desc = _describe(row, lib)
            if not desc:
                continue
            media_id = row["id"]
            descriptions[media_id] = desc
            group = desc["group"]
            if group not in recent[desc["kind"]]:
                recent[desc["kind"]][group] = {
                    "kind": desc["kind"], "title": desc["title"],
                    "year": desc["year"], "subtitle": desc["subtitle"],
                    "library_id": desc["library_id"], "key": desc["key"],
                    "media_id": media_id, "watched": media_id in watched_ids,
                    "added_at": row["added_at"],
                }
            if desc["kind"] == "tv":
                # Parse once per indexed episode, not once per new Home card.
                info = episode_info(row["path"], row["source_root"] or lib["path"])
                if info["season"] is not None and info["episode"] is not None:
                    tv_episodes.setdefault(group, []).append((
                        info["season"], info["episode"], media_id, desc
                    ))

        for media_id, entry in sorted(
            progress.items(),
            key=lambda pair: (pair[1]["updated_at"], pair[0]), reverse=True
        ):
            if entry["completed"] or entry["position_seconds"] < 30:
                continue
            duration = entry["duration_seconds"]
            position = entry["position_seconds"]
            if duration > 0 and position >= duration * .95:
                continue
            desc = descriptions.get(media_id)
            if not desc or desc["group"] in in_progress_groups:
                continue
            in_progress_groups.add(desc["group"])
            candidates.append((
                entry["updated_at"], 1, media_id, {
                    "media_id": media_id, "kind": desc["kind"],
                    "title": desc["title"], "year": desc["year"],
                    "library_id": desc["library_id"], "key": desc["key"],
                    "subtitle": desc["subtitle"], "play_state": "resume",
                    "position_seconds": position,
                    "duration_seconds": duration,
                    "progress_percent": round(position * 100 / duration) if duration > 0 else None,
                    "updated_at": entry["updated_at"],
                }
            ))

        for group, episodes in tv_episodes.items():
            if group in in_progress_groups:
                continue
            # Completed episodes establish series history. Next means the
            # first indexed, unwatched episode after the latest completed one,
            # not an unplayed show which the viewer has never started.
            completed = [(season, number, media_id) for season, number, media_id, _ in episodes
                         if media_id in watched_ids]
            if not completed:
                continue
            last_season, last_number, last_id = max(completed)
            completed_numbers = {(season, number) for season, number, media_id, _ in episodes
                                 if media_id in watched_ids}
            options = sorted(
                ((season, number, media_id, desc)
                 for season, number, media_id, desc in episodes
                 if (season, number) > (last_season, last_number)
                 and (season, number) not in completed_numbers),
                key=lambda option: (option[0], option[1], option[2]),
            )
            if not options:
                continue
            _season, _episode, media_id, desc = options[0]
            last_date = progress[last_id]["updated_at"]
            candidates.append((
                last_date, 0, media_id, {
                    "media_id": media_id, "kind": "tv",
                    "title": desc["title"], "year": desc["year"],
                    "library_id": desc["library_id"], "key": desc["key"],
                    "subtitle": desc["subtitle"], "play_state": "next",
                    "position_seconds": 0, "duration_seconds": 0,
                    "progress_percent": None, "updated_at": last_date,
                }
            ))

    from .poster_index import attach_posters
    candidates.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
    shelves = {
        "continue_watching": [card for _, _, _, card in candidates[:12]],
        "recent_movies": list(recent["movies"].values())[:16],
        "recent_tv": list(recent["tv"].values())[:16],
    }
    attach_posters([item for items in shelves.values() for item in items])
    return {
        **shelves,
        "totals": {
            "movies": len(recent["movies"]),
            "tv": len(recent["tv"]),
        },
        "playback_available": True,
        "revision": revision,
        "progress_revision": progress_revision,
    }


@router.put("/playback/progress")
@router.post("/playback/progress")
def update_playback(item: PlaybackUpdate):
    """Persist a resume point, even when HLS has not reported its duration."""
    if item.duration_seconds > 0 and item.position_seconds > item.duration_seconds:
        raise HTTPException(422, "Playback position cannot exceed duration")
    with db() as connection:
        exists = connection.execute("SELECT id FROM media WHERE id=?", (item.media_id,)).fetchone()
        if not exists:
            raise HTTPException(404, "Media item not found")
        previous = connection.execute(
            "SELECT duration_seconds,completed FROM playback_progress WHERE media_id=?",
            (item.media_id,),
        ).fetchone()
        # A transient unknown duration must not wipe a previously probed one.
        duration = item.duration_seconds
        if duration == 0 and previous and previous["duration_seconds"] >= item.position_seconds:
            duration = previous["duration_seconds"]
        # Preserve a manual/completed watched state against late checkpoints,
        # except when the viewer explicitly starts replaying a watched item.
        # A replay must be allowed to become in-progress and show on Home.
        finished = duration > 0 and item.position_seconds >= duration * .95
        completed = bool(item.completed or finished or (
            previous and previous["completed"] and not item.replaying
        ))
        connection.execute(
            """INSERT INTO playback_progress
                (media_id,position_seconds,duration_seconds,completed,updated_at)
                VALUES (?,?,?,?,CURRENT_TIMESTAMP)
                ON CONFLICT(media_id) DO UPDATE SET
                  position_seconds=excluded.position_seconds,
                  duration_seconds=excluded.duration_seconds,
                  completed=excluded.completed,
                  updated_at=CURRENT_TIMESTAMP""",
            (item.media_id, item.position_seconds, duration, int(completed)),
        )
    return {"saved": True, "completed": completed,
            "position_seconds": item.position_seconds, "duration_seconds": duration}
