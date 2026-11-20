"""Home shelves and local playback progress tracking."""
from collections import OrderedDict
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .catalog import episode_info, movie_info
from .library import db
from .viewer import current as current_viewer

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
            "season_number": season,
            "episode_number": episode,
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
        "COALESCE(SUM(completed), 0) FROM playback_progress WHERE viewer=?",
        (current_viewer().id,)
    ).fetchone()
    hidden = connection.execute(
        "SELECT COUNT(*), COALESCE(SUM(rowid), 0) FROM continue_watching_hidden WHERE viewer=?",
        (current_viewer().id,)
    ).fetchone()
    return [row[0], row[1], round(row[2], 3), round(row[3], 3), row[4],
            hidden[0], hidden[1]]


@router.get("/home/revision")
def home_revision():
    with db() as connection:
        catalog = connection.execute(
            "SELECT revision FROM catalog_state WHERE id=1"
        ).fetchone()[0]
        progress = _progress_revision(connection)
    return {"catalog_revision": catalog, "progress_revision": progress}


def _media_group(connection, media_id: int):
    row = connection.execute(
        "SELECT media.id,media.path,media.source_root,libraries.id AS library_id,"
        "libraries.kind,libraries.path AS library_path FROM media "
        "JOIN libraries ON libraries.id=media.library_id WHERE media.id=?",
        (media_id,)
    ).fetchone()
    if not row:
        raise HTTPException(404, "Media item not found")
    lib = {"id": row["library_id"], "kind": row["kind"],
           "path": row["library_path"]}
    description = _describe(row, lib)
    if not description:
        raise HTTPException(404, "Media details unavailable")
    return (description["kind"], description["library_id"], description["key"])


@router.post("/home/continue/{media_id}/dismiss")
def dismiss_continue_watching(media_id: int):
    with db() as connection:
        group = _media_group(connection, media_id)
        connection.execute(
            "INSERT OR IGNORE INTO continue_watching_hidden(viewer,kind,library_id,media_key) "
            "VALUES(?,?,?,?)", (current_viewer().id, *group)
        )
    return {"dismissed": True, "media_id": media_id}


@router.post("/home/continue/{media_id}/start")
def started_continue_watching(media_id: int):
    """Explicit playback start restores dismissed titles, not page refreshes."""
    with db() as connection:
        group = _media_group(connection, media_id)
        connection.execute(
            "DELETE FROM continue_watching_hidden WHERE viewer=? AND kind=? AND library_id=? "
            "AND media_key=?", (current_viewer().id, *group)
        )
    return {"dismissed": False, "media_id": media_id}


@router.get("/home")
def home_shelves():
    recent = {"movies": OrderedDict(), "tv": OrderedDict()}
    recent_by_library = {}
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
        # Preserve configured sidebar order within each media kind.
        libs = {row["id"]: row for row in connection.execute(
            "SELECT id,name,kind,path,sort_order FROM libraries "
            "ORDER BY CASE kind WHEN 'movies' THEN 0 WHEN 'tv' THEN 1 ELSE 2 END, "
            "sort_order, id"
        ) if current_viewer().can_see(row["id"])}
        progress = {row["media_id"]: dict(row) for row in connection.execute(
            "SELECT media_id,position_seconds,duration_seconds,completed,updated_at "
            "FROM playback_progress WHERE viewer=?", (current_viewer().id,)
        )}
        watched_ids = {media_id for media_id, entry in progress.items() if entry["completed"]}
        hidden_groups = {
            (row["kind"], row["library_id"], row["media_key"])
            for row in connection.execute(
                "SELECT kind,library_id,media_key FROM continue_watching_hidden WHERE viewer=?",
                (current_viewer().id,)
            )
        }
        rows = connection.execute(
            "SELECT id,library_id,path,source_root,added_at,mtime_ns FROM media "
            "ORDER BY added_at DESC, mtime_ns DESC, id DESC"
        ).fetchall()
        for row in rows:
            lib = libs.get(row["library_id"])
            if not lib or lib["kind"] not in ("movies", "tv"):
                continue
            desc = _describe(row, lib)
            if not desc:
                continue
            media_id = row["id"]
            descriptions[media_id] = desc
            group = desc["group"]
            if group not in recent[desc["kind"]]:
                card = {
                    "kind": desc["kind"], "title": desc["title"],
                    "year": desc["year"], "subtitle": desc["subtitle"],
                    "library_id": desc["library_id"], "key": desc["key"],
                    "media_id": media_id, "watched": media_id in watched_ids,
                    "added_at": row["added_at"],
                }
                recent[desc["kind"]][group] = card
                # An independent 16-item shelf for each configured library.
                # The globally sorted rows ensure that each shelf uses the
                # newest first-seen media, without a different library
                # pushing its titles out of the list.
                recent_by_library.setdefault(desc["library_id"], OrderedDict())[group] = card
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
            if not desc or desc["group"] in in_progress_groups or (
                desc["kind"], desc["library_id"], desc["key"]
            ) in hidden_groups:
                continue
            in_progress_groups.add(desc["group"])
            candidates.append((
                entry["updated_at"], 1, media_id, {
                    "media_id": media_id, "kind": desc["kind"],
                    "title": desc["title"], "year": desc["year"],
                    "library_id": desc["library_id"], "key": desc["key"],
                    "subtitle": desc["subtitle"], "play_state": "resume",
                    "season_number": desc.get("season_number"),
                    "position_seconds": position,
                    "duration_seconds": duration,
                    "progress_percent": round(position * 100 / duration) if duration > 0 else None,
                    "updated_at": entry["updated_at"],
                }
            ))

        for group, episodes in tv_episodes.items():
            if group in in_progress_groups or ("tv", group[0], group[1]) in hidden_groups:
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
                    "season_number": desc.get("season_number"),
                    "position_seconds": 0, "duration_seconds": 0,
                    "progress_percent": None, "updated_at": last_date,
                }
            ))

    from .poster_index import attach_posters
    candidates.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
    shelves = {
        "continue_watching": [card for _, _, _, card in candidates[:12]],
        # Retained for compatibility with clients using the older Home API.
        "recent_movies": list(recent["movies"].values())[:16],
        "recent_tv": list(recent["tv"].values())[:16],
    }
    library_shelves = [
        {
            "library_id": lib["id"], "name": lib["name"], "kind": lib["kind"],
            "items": list(recent_by_library.get(lib["id"], {}).values())[:16],
        }
        for lib in libs.values() if lib["kind"] in ("movies", "tv")
    ]
    attach_posters([item for items in shelves.values() for item in items] +
                   [item for lib in library_shelves for item in lib["items"]])
    return {
        **shelves,
        "recent_libraries": library_shelves,
        "totals": {
            "movies": len(recent["movies"]),
            "tv": len(recent["tv"]),
        },
        "playback_available": True,
        "configured_library_kinds": sorted({row["kind"] for row in libs.values()}),
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
        exists = connection.execute("SELECT id,library_id FROM media WHERE id=?", (item.media_id,)).fetchone()
        if not exists or not current_viewer().can_see(exists["library_id"]):
            raise HTTPException(404, "Media item not found")
        previous = connection.execute(
            "SELECT duration_seconds,completed FROM playback_progress WHERE viewer=? AND media_id=?",
            (current_viewer().id, item.media_id),
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
                (viewer,media_id,position_seconds,duration_seconds,completed,updated_at)
                VALUES (?,?,?,?,?,CURRENT_TIMESTAMP)
                ON CONFLICT(viewer,media_id) DO UPDATE SET
                  position_seconds=excluded.position_seconds,
                  duration_seconds=excluded.duration_seconds,
                  completed=excluded.completed,
                  updated_at=CURRENT_TIMESTAMP""",
            (current_viewer().id, item.media_id, item.position_seconds, duration, int(completed)),
        )
    return {"saved": True, "completed": completed,
            "position_seconds": item.position_seconds, "duration_seconds": duration}
