"""Plex-style TV library hierarchy built from the user's own indexed media."""
from collections import defaultdict
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from .catalog import episode_info
from .library import db
from .artwork import localize, local_show_poster, register_remote
from .metadata import show_metadata as tmdb_show_metadata, show_metadata_by_id as tmdb_by_id, season_metadata, token_status, _call as tmdb_call, image_url as tmdb_image
from .tvmaze import show_metadata as tvmaze_show_metadata, show_metadata_by_id as tvmaze_by_id, season_metadata as tvmaze_season_metadata, show_cast as tvmaze_show_cast, _get as tvmaze_get, image_url as tvmaze_image
from .arr import sonarr_metadata

def _manual_table(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS tv_manual_matches (library_id INTEGER NOT NULL, show_key TEXT NOT NULL, provider TEXT NOT NULL, provider_id INTEGER NOT NULL, PRIMARY KEY (library_id, show_key))")


def manual_match(library_id, key):
    with db() as conn:
        _manual_table(conn)
        row = conn.execute("SELECT provider,provider_id FROM tv_manual_matches WHERE library_id=? AND show_key=?", (library_id, key)).fetchone()
    return dict(row) if row else None


def show_metadata(title, year=None, library_id=None, show_key=None):
    if library_id is not None and show_key is not None:
        chosen = manual_match(library_id, show_key)
        if chosen:
            return (tmdb_by_id(chosen["provider_id"]) if chosen["provider"] == "TMDB"
                    else tvmaze_by_id(chosen["provider_id"]))
    if token_status():
        tmdb = tmdb_show_metadata(title, year)
        if tmdb:
            return tmdb
    automatic = tvmaze_show_metadata(title, year)
    sonarr = sonarr_metadata(title, year)
    if automatic:
        if sonarr.get("overview") and not automatic.get("overview"):
            automatic["overview"] = sonarr["overview"]
        return automatic
    return sonarr



def provider_season(meta, number):
    if meta.get("source") == "TVmaze":
        return tvmaze_season_metadata(meta.get("tvmaze_id"), number)
    if meta.get("source") == "Sonarr":
        return {}
    return season_metadata(meta.get("tmdb_id"), number)


router = APIRouter(prefix="/api/tv")


class MatchRequest(BaseModel):
    provider: str
    provider_id: int


@router.get("/match/search")
def search_matches(library_id: int = Query(ge=1), key: str = Query(min_length=1, max_length=300),
                   query: str = Query(min_length=2, max_length=120)):
    local_show(library_id, key)
    results = []
    raw_tmdb = tmdb_call("search/tv", query={"query": query, "language": "en-US", "include_adult": "false"}) if token_status() else None
    if isinstance(raw_tmdb, dict):
        for item in raw_tmdb.get("results", [])[:15]:
            if not isinstance(item, dict) or not isinstance(item.get("id"), int) or item["id"] <= 0:
                continue
            results.append({"provider": "TMDB", "provider_id": item["id"],
                            "title": str(item.get("name") or item.get("original_name") or "")[:120],
                            "year": str(item.get("first_air_date") or "")[:4],
                            "overview": str(item.get("overview") or "")[:240],
                            "poster_url": tmdb_image(item.get("poster_path"))})
    raw_tvmaze = tvmaze_get("/search/shows", {"q": query})
    if isinstance(raw_tvmaze, list):
        for entry in raw_tvmaze[:15]:
            item = entry.get("show") if isinstance(entry, dict) else None
            if not isinstance(item, dict) or not isinstance(item.get("id"), int) or item["id"] <= 0:
                continue
            results.append({"provider": "TVmaze", "provider_id": item["id"],
                            "title": str(item.get("name") or "")[:120],
                            "year": str(item.get("premiered") or "")[:4],
                            "overview": "", "poster_url": tvmaze_image(item.get("image"))})
    return {"results": results, "tmdb_connected": token_status()}


@router.put("/match")
def save_match(library_id: int = Query(ge=1), key: str = Query(min_length=1, max_length=300),
               change: MatchRequest = None):
    local_show(library_id, key)
    if change is None or change.provider not in ("TMDB", "TVmaze") or change.provider_id <= 0:
        raise HTTPException(422, "Choose a valid metadata result")
    details = tmdb_by_id(change.provider_id) if change.provider == "TMDB" else tvmaze_by_id(change.provider_id)
    if not details:
        raise HTTPException(422, "The selected metadata record could not be loaded")
    with db() as conn:
        _manual_table(conn)
        conn.execute("INSERT INTO tv_manual_matches(library_id,show_key,provider,provider_id) VALUES(?,?,?,?) ON CONFLICT(library_id,show_key) DO UPDATE SET provider=excluded.provider,provider_id=excluded.provider_id",
                     (library_id, key, change.provider, change.provider_id))
    from .poster_index import invalidate
    invalidate("tv", library_id, key)
    return {"matched": True, "provider": change.provider, "provider_id": change.provider_id, "title": details.get("title")}


@router.delete("/match")
def clear_match(library_id: int = Query(ge=1), key: str = Query(min_length=1, max_length=300)):
    local_show(library_id, key)
    with db() as conn:
        _manual_table(conn)
        conn.execute("DELETE FROM tv_manual_matches WHERE library_id=? AND show_key=?", (library_id, key))
    from .poster_index import invalidate
    invalidate("tv", library_id, key)
    return {"matched": False}


class BulkWatched(BaseModel):
    watched: bool


def _bulk_watched(library_id, show_key, watched, season_number=None):
    show = local_show(library_id, show_key)
    ids = [episode["id"] for episode in show["episodes"]
           if season_number is None or episode["season"] == season_number]
    if not ids:
        raise HTTPException(404, "No matching episodes")
    with db() as conn:
        if watched:
            conn.executemany(
                "INSERT INTO playback_progress(media_id,position_seconds,duration_seconds,"
                "completed,updated_at) VALUES(?,0,0,1,CURRENT_TIMESTAMP) "
                "ON CONFLICT(media_id) DO UPDATE SET completed=1,"
                "position_seconds=duration_seconds,updated_at=CURRENT_TIMESTAMP",
                [(id,) for id in ids],
            )
        else:
            conn.executemany("DELETE FROM playback_progress WHERE media_id=?",
                             [(id,) for id in ids])
    return {"watched": watched, "updated": len(ids)}


@router.put("/show/watched")
def set_show_watched(library_id: int, key: str, change: BulkWatched):
    return _bulk_watched(library_id, key, change.watched)


@router.put("/season/watched")
def set_season_watched(library_id: int, key: str, season_number: int, change: BulkWatched):
    if season_number < 0 or season_number > 999:
        raise HTTPException(422, "Invalid season")
    return _bulk_watched(library_id, key, change.watched, season_number)



def local_show(library_id: int, show_key: str):
    with db() as conn:
        library = conn.execute(
            "SELECT id,kind,path FROM libraries WHERE id=?", (library_id,)
        ).fetchone()
        if library is None or library["kind"] != "tv":
            raise HTTPException(404, "TV library not found")
        entries = conn.execute(
            "SELECT id,path,added_at FROM media WHERE library_id=? ORDER BY path",
            (library_id,),
        ).fetchall()

    with db() as conn:
        playback = {row["media_id"]: dict(row) for row in conn.execute(
            "SELECT media_id,position_seconds,duration_seconds,completed FROM playback_progress"
        )}
        watched_ids = {id for id, state in playback.items() if state["completed"]}
    found = []
    info = None
    for entry in entries:
        try:
            parsed = episode_info(entry["path"], library["path"])
        except (ValueError, OSError):
            continue
        if parsed["key"] != show_key:
            continue
        if info is None:
            info = parsed
        found.append({
            "id": entry["id"],
            "season": parsed["season"],
            "episode": parsed["episode"],
            "filename": Path(entry["path"]).name,
            "added_at": entry["added_at"],
            "watched": entry["id"] in watched_ids,
            "position_seconds": playback.get(entry["id"], {}).get("position_seconds", 0),
            "duration_seconds": playback.get(entry["id"], {}).get("duration_seconds", 0),
        })
    if not info or not found:
        raise HTTPException(404, "TV show not found")
    found.sort(key=lambda x: (
        x["season"] if x["season"] is not None else 999,
        x["episode"] if x["episode"] is not None else 999,
        x["id"],
    ))
    return {
        "library_id": library_id, "key": show_key, "title": info["title"],
        "year": info["year"], "episodes": found,
    }


def merged_show(library_id: int, show_key: str):
    show = local_show(library_id, show_key)
    metadata = show_metadata(show["title"], show["year"], library_id, show_key)
    grouped = defaultdict(list)
    for episode in show["episodes"]:
        grouped[episode["season"]].append(episode)
    metadata_seasons = {
        season.get("number"): season for season in metadata.get("seasons", [])
    }
    seasons = []
    for number in sorted(grouped, key=lambda n: (n is None, n if n is not None else 0)):
        details = metadata_seasons.get(number, {})
        seasons.append({
            "number": number,
            "name": details.get("name") or
                    ("Unsorted episodes" if number is None else
                     ("Specials" if number == 0 else "Season " + str(number))),
            "overview": details.get("overview", ""),
            "poster_url": details.get("poster_url") or metadata.get("poster_url"),
            "episode_count": len(grouped[number]),
            "watched_count": sum(1 for e in grouped[number] if e["watched"]),
        })
    return show, metadata, seasons


@router.get("/poster")
def poster(library_id: int = Query(ge=1), key: str = Query(min_length=1, max_length=300)):
    show = local_show(library_id, key)
    metadata = show_metadata(show["title"], show["year"], library_id, key)
    result = {
        "poster_url": metadata.get("poster_url"),
        "overview": metadata.get("overview", ""),
        "metadata_available": bool(metadata), "metadata_source": metadata.get("source"), "source_url": metadata.get("source_url"),
    }
    result = localize(result)
    result["poster_url"] = local_show_poster(library_id, key) or result["poster_url"]
    if result["poster_url"]:
        from .poster_index import remember
        remember("tv", library_id, key, result["poster_url"])
    return result


@router.get("/show")
def show_details(library_id: int = Query(ge=1), key: str = Query(min_length=1, max_length=300)):
    show, meta, seasons = merged_show(library_id, key)
    cast = []
    actors = (tvmaze_show_cast(meta.get("tvmaze_id"))
              if meta.get("source") == "TVmaze" else meta.get("cast") or [])
    for actor in actors:
        cast.append({"name": actor["name"], "tmdb_id": actor.get("tmdb_id"), "tvmaze_id": actor.get("tvmaze_id"), "character": actor.get("character") or "",
                     "photo": register_remote(actor.get("photo_url"))})
    result = {
        "cast": cast,
        "reviews": meta.get("reviews") or [],
        "rating": meta.get("rating"),
        "network": meta.get("network"),
        "genres": meta.get("genres") or [],
        "trailer_key": meta.get("trailer_key"),
        "library_id": library_id, "key": key, "title": meta.get("title") or show["title"],
        "year": show["year"], "overview": meta.get("overview", ""),
        "poster_url": meta.get("poster_url"),
        "backdrop_url": meta.get("backdrop_url"),
        "seasons": seasons,
        "episode_count": len(show["episodes"]),
        "watched_count": sum(1 for e in show["episodes"] if e["watched"]),
        "metadata_available": bool(meta), "metadata_source": meta.get("source"), "source_url": meta.get("source_url"),
        "manual_match": manual_match(library_id, key),
    }
    result = localize(result)
    result["poster_url"] = local_show_poster(library_id, key) or result["poster_url"]
    if result["poster_url"]:
        from .poster_index import remember
        remember("tv", library_id, key, result["poster_url"])
    return result


@router.get("/season")
def season_details(
    library_id: int = Query(ge=1),
    key: str = Query(min_length=1, max_length=300),
    season_number: int = Query(ge=0, le=999),
):
    show, meta, seasons = merged_show(library_id, key)
    season = next((s for s in seasons if s["number"] == season_number), None)
    if season is None:
        raise HTTPException(404, "Season not found in your library")
    detail = provider_season(meta, season_number)
    metadata_episodes = detail.get("episodes", {})
    entries = []
    for episode in show["episodes"]:
        if episode["season"] != season_number:
            continue
        episode_meta = metadata_episodes.get(str(episode["episode"]), {})
        entries.append({
            **episode, "title": episode_meta.get("title") or
            ("Episode " + str(episode["episode"]) if episode["episode"] is not None else episode["filename"]),
            "overview": episode_meta.get("overview", ""),
            "still_url": episode_meta.get("still_url"),
            "air_date": episode_meta.get("air_date", ""),
            "runtime": episode_meta.get("runtime"),
        })
    result = {
        "show": {"library_id": library_id, "key": key, "title": meta.get("title") or show["title"],
                 "poster_url": meta.get("poster_url"), "overview": meta.get("overview", "")},
        "season": {**season,
                   "overview": detail.get("overview") or season["overview"],
                   "poster_url": detail.get("poster_url") or season["poster_url"]},
        "episodes": entries,
        "metadata_available": bool(meta), "metadata_source": meta.get("source"), "source_url": meta.get("source_url"),
    }
    result = localize(result)
    result["show"]["poster_url"] = local_show_poster(library_id, key) or result["show"]["poster_url"]
    return result


@router.get("/next")
def next_episode(media_id: int = Query(ge=1)):
    """Next locally indexed, numbered and unwatched episode in series order."""
    with db() as conn:
        row = conn.execute(
            "SELECT m.path,m.library_id,l.path AS root,l.kind "
            "FROM media m JOIN libraries l ON l.id=m.library_id WHERE m.id=?",
            (media_id,),
        ).fetchone()
    if row is None or row["kind"] != "tv":
        return {"next": None}
    try:
        current = episode_info(row["path"], row["root"])
    except (ValueError, OSError):
        return {"next": None}
    season, number = current.get("season"), current.get("episode")
    if season is None or number is None:
        return {"next": None}
    try:
        show = local_show(row["library_id"], current["key"])
    except HTTPException:
        return {"next": None}
    for entry in show["episodes"]:
        next_season, next_number = entry["season"], entry["episode"]
        if next_season is None or next_number is None or entry["watched"]:
            continue
        if (next_season, next_number) > (season, number):
            return {"next": {
                "media_id": entry["id"],
                "title": show["title"] + " · S" + str(next_season).zfill(2) +
                         " E" + str(next_number).zfill(2),
                "season": next_season, "episode": next_number,
            }}
    return {"next": None}


@router.get("/episode")
def episode_details(media_id: int = Query(ge=1)):
    with db() as conn:
        row = conn.execute(
            "SELECT m.id,m.path,m.library_id,l.path AS root,l.kind "
            "FROM media m JOIN libraries l ON l.id=m.library_id WHERE m.id=?",
            (media_id,),
        ).fetchone()
    if row is None or row["kind"] != "tv":
        raise HTTPException(404, "TV episode not found")
    try:
        parsed = episode_info(row["path"], row["root"])
    except (ValueError, OSError) as error:
        raise HTTPException(404, "TV episode unavailable") from error
    show, meta, _ = merged_show(row["library_id"], parsed["key"])
    detail = provider_season(meta, parsed["season"]) if parsed["season"] is not None else {}
    episode_meta = detail.get("episodes", {}).get(str(parsed["episode"]), {})
    result = {
        "id": media_id, "library_id": row["library_id"], "key": parsed["key"],
        "show_title": meta.get("title") or show["title"], "season_number": parsed["season"],
        "episode_number": parsed["episode"],
        "title": episode_meta.get("title") or
        ("Episode " + str(parsed["episode"]) if parsed["episode"] is not None else Path(row["path"]).name),
        "overview": episode_meta.get("overview", ""),
        "still_url": episode_meta.get("still_url"),
        "air_date": episode_meta.get("air_date", ""),
        "runtime": episode_meta.get("runtime"),
        "filename": Path(row["path"]).name,
        "playback_available": True,
        "watched": next((e["watched"] for e in show["episodes"] if e["id"] == media_id), False),
        "position_seconds": next((e["position_seconds"] for e in show["episodes"] if e["id"] == media_id), 0),
        "duration_seconds": next((e["duration_seconds"] for e in show["episodes"] if e["id"] == media_id), 0),
        "metadata_available": bool(meta), "metadata_source": meta.get("source"), "source_url": meta.get("source_url"),
    }
    from .video_info import video_format
    result["video_format"] = video_format(row["path"])
    return localize(result)
