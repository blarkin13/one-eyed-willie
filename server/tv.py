"""Plex-style TV library hierarchy built from the user's own indexed media."""
from collections import defaultdict
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from .catalog import episode_info
from .library import db
from .metadata import show_metadata as tmdb_show_metadata, season_metadata, token_status
from .tvmaze import show_metadata as tvmaze_show_metadata, season_metadata as tvmaze_season_metadata

def show_metadata(title, year=None):
    """Use optional TMDB credentials when present, else automatic keyless TVmaze."""
    if token_status():
        tmdb = tmdb_show_metadata(title, year)
        if tmdb:
            return tmdb
    return tvmaze_show_metadata(title, year)

def provider_season(meta, number):
    if meta.get("source") == "TVmaze":
        return tvmaze_season_metadata(meta.get("tvmaze_id"), number)
    return season_metadata(meta.get("tmdb_id"), number)


router = APIRouter(prefix="/api/tv")


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
    metadata = show_metadata(show["title"], show["year"])
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
        })
    return show, metadata, seasons


@router.get("/poster")
def poster(library_id: int = Query(ge=1), key: str = Query(min_length=1, max_length=300)):
    show = local_show(library_id, key)
    metadata = show_metadata(show["title"], show["year"])
    return {
        "poster_url": metadata.get("poster_url"),
        "overview": metadata.get("overview", ""),
        "metadata_available": bool(metadata), "metadata_source": metadata.get("source"), "source_url": metadata.get("source_url"),
    }


@router.get("/show")
def show_details(library_id: int = Query(ge=1), key: str = Query(min_length=1, max_length=300)):
    show, meta, seasons = merged_show(library_id, key)
    return {
        "library_id": library_id, "key": key, "title": show["title"],
        "year": show["year"], "overview": meta.get("overview", ""),
        "poster_url": meta.get("poster_url"),
        "backdrop_url": meta.get("backdrop_url"),
        "seasons": seasons,
        "episode_count": len(show["episodes"]),
        "metadata_available": bool(meta), "metadata_source": meta.get("source"), "source_url": meta.get("source_url"),
    }


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
    return {
        "show": {"library_id": library_id, "key": key, "title": show["title"],
                 "poster_url": meta.get("poster_url"), "overview": meta.get("overview", "")},
        "season": {**season,
                   "overview": detail.get("overview") or season["overview"],
                   "poster_url": detail.get("poster_url") or season["poster_url"]},
        "episodes": entries,
        "metadata_available": bool(meta), "metadata_source": meta.get("source"), "source_url": meta.get("source_url"),
    }


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
    return {
        "id": media_id, "library_id": row["library_id"], "key": parsed["key"],
        "show_title": show["title"], "season_number": parsed["season"],
        "episode_number": parsed["episode"],
        "title": episode_meta.get("title") or
        ("Episode " + str(parsed["episode"]) if parsed["episode"] is not None else Path(row["path"]).name),
        "overview": episode_meta.get("overview", ""),
        "still_url": episode_meta.get("still_url"),
        "air_date": episode_meta.get("air_date", ""),
        "runtime": episode_meta.get("runtime"),
        "filename": Path(row["path"]).name,
        "playback_available": False,
        "metadata_available": bool(meta), "metadata_source": meta.get("source"), "source_url": meta.get("source_url"),
    }
