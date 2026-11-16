"""Optional TMDB artwork and descriptions for personal-use TV libraries.

The token stays in /data, never in GitHub, HTML or API responses. Absence of
metadata is not treated as a reason to hide locally indexed seasons/episodes.
"""
import json
import os
import re
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from threading import RLock

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .library import db

router = APIRouter(prefix="/api/metadata")
TOKEN_FILE = Path(os.environ.get("METADATA_CONFIG_PATH", "/data/metadata-settings.json"))
LOCK = RLock()
IMG_PATH = re.compile(r"^/[a-zA-Z0-9_-]+\.(?:jpg|png|webp)$")
VALID_TITLE = re.compile(r"[^a-z0-9]+")
CACHE_SECONDS = 30 * 24 * 60 * 60


class TokenRequest(BaseModel):
    token: str = Field(min_length=20, max_length=500)


def _token():
    env = os.environ.get("TMDB_READ_ACCESS_TOKEN", "").strip()
    if env:
        return env
    try:
        data = json.loads(TOKEN_FILE.read_text())
        return str(data.get("token", "")).strip()
    except (FileNotFoundError, ValueError, OSError):
        return ""


def token_status():
    return bool(_token())


def _call(path, *, token=None, query=None):
    bearer = token if token is not None else _token()
    if not bearer:
        return None
    url = "https://api.themoviedb.org/3/" + path.lstrip("/")
    if query:
        url += "?" + urllib.parse.urlencode(query)
    request = urllib.request.Request(
        url,
        headers={"Authorization": "Bearer " + bearer,
                 "Accept": "application/json", "User-Agent": "OneEyedWillie/0.6"},
    )
    try:
        with urllib.request.urlopen(request, timeout=6) as response:
            return json.loads(response.read(2_000_000))
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError, ValueError):
        return None


def _cache_get(key):
    with db() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS metadata_cache "
            "(cache_key TEXT PRIMARY KEY, payload TEXT NOT NULL, fetched_at INTEGER NOT NULL)"
        )
        row = conn.execute(
            "SELECT payload, fetched_at FROM metadata_cache WHERE cache_key=?", (key,)
        ).fetchone()
    if row:
        try:
            result = json.loads(row["payload"])
            # Retry an unmatched title soon; don't hide new provider artwork for 30 days.
            ttl = 12 * 60 * 60 if not result else CACHE_SECONDS
            if time.time() - row["fetched_at"] < ttl:
                return result
        except ValueError:
            pass
    return None


def _cache_put(key, data):
    with db() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS metadata_cache "
            "(cache_key TEXT PRIMARY KEY, payload TEXT NOT NULL, fetched_at INTEGER NOT NULL)"
        )
        conn.execute(
            "INSERT INTO metadata_cache(cache_key,payload,fetched_at) VALUES(?,?,?) "
            "ON CONFLICT(cache_key) DO UPDATE SET payload=excluded.payload, "
            "fetched_at=excluded.fetched_at",
            (key, json.dumps(data), int(time.time())),
        )


def image_url(path, size="w342"):
    if isinstance(path, str) and IMG_PATH.fullmatch(path):
        return "https://image.tmdb.org/t/p/" + size + path
    return None


def _simple(value):
    return VALID_TITLE.sub("", (value or "").casefold())


def show_metadata(title, year=None):
    """Only exact-normalized title matches, avoiding incorrect posters for similar shows."""
    if not token_status():
        return {}
    key = "tv:v2:" + _simple(title) + ":" + str(year or "")
    with LOCK:
        cached = _cache_get(key)
        if cached is not None:
            return cached
        result = _call("search/tv", query={"query": title, "language": "en-US", "include_adult": "false"})
        if result is None:
            return {}
        matches = [
            entry for entry in result.get("results", [])
            if _simple(entry.get("name")) == _simple(title)
            or _simple(entry.get("original_name")) == _simple(title)
        ]
        if year:
            matches = [
                entry for entry in matches
                if not entry.get("first_air_date") or
                abs(int(entry["first_air_date"][:4]) - int(year)) <= 1
            ]
        if not matches:
            _cache_put(key, {})
            return {}
        tmdb_id = matches[0].get("id")
        metadata = show_metadata_by_id(tmdb_id, fallback=matches[0])
        if metadata:
            _cache_put(key, metadata)
        return metadata

def show_metadata_by_id(tmdb_id, fallback=None):
    """Read a selected TV series by provider ID, bypassing title matching."""
    if not token_status() or not isinstance(tmdb_id, int) or tmdb_id <= 0:
        return {}
    details = _call("tv/" + str(tmdb_id), query={
        "language": "en-US", "append_to_response": "videos,credits,reviews"
    })
    if not isinstance(details, dict):
        details = fallback
    if not isinstance(details, dict) or details.get("id") != tmdb_id:
        return {}
    seasons = []
    for season in details.get("seasons", []):
        seasons.append({
            "number": season.get("season_number"),
            "name": season.get("name") or "Season " + str(season.get("season_number")),
            "overview": season.get("overview") or "",
            "poster_url": image_url(season.get("poster_path")),
            "episode_count": season.get("episode_count"),
        })
    trailer = next((
        v.get("key") for v in (details.get("videos") or {}).get("results", [])
        if isinstance(v, dict) and v.get("site") == "YouTube"
        and v.get("type") == "Trailer"
        and isinstance(v.get("key"), str)
        and re.fullmatch(r"[A-Za-z0-9_-]{11}", v["key"])
    ), None)
    cast = [
        {"tmdb_id": actor.get("id"), "name": str(actor.get("name") or "")[:90],
         "character": str(actor.get("character") or "")[:90],
         "photo_url": image_url(actor.get("profile_path"), "w185")}
        for actor in (details.get("credits") or {}).get("cast", [])[:18]
        if isinstance(actor, dict) and actor.get("name")
    ]
    reviews = [
        {"author": str(review.get("author") or "TMDB contributor")[:80],
         "excerpt": str(review.get("content") or "")[:3500], "source": "TMDB"}
        for review in (details.get("reviews") or {}).get("results", [])[:12]
        if isinstance(review, dict) and review.get("content")
    ]
    metadata = {
        "cast": cast,
        "reviews": reviews,
        "trailer_key": trailer,
        "rating": details.get("vote_average"),
        "episode_run_time": details.get("episode_run_time"),
        "genres": [g.get("name") for g in details.get("genres", []) if isinstance(g, dict) and g.get("name")],
        "network": ", ".join(n.get("name") for n in details.get("networks", []) if isinstance(n, dict) and n.get("name")),
        "tmdb_id": tmdb_id,
        "title": details.get("name") or str(tmdb_id),
        "overview": details.get("overview") or "",
        "poster_url": image_url(details.get("poster_path")),
        "backdrop_url": image_url(details.get("backdrop_path"), "w780"),
        "seasons": seasons,
        "source": "TMDB",
    }

    return metadata


def season_metadata(tmdb_id, season_number):
    if not token_status() or not isinstance(tmdb_id, int):
        return {}
    key = "season:" + str(tmdb_id) + ":" + str(season_number)
    with LOCK:
        cached = _cache_get(key)
        if cached is not None:
            return cached
        result = _call(
            "tv/" + str(tmdb_id) + "/season/" + str(season_number),
            query={"language": "en-US"},
        )
        if result is None:
            return {}
        data = {
            "name": result.get("name") or "Season " + str(season_number),
            "overview": result.get("overview") or "",
            "poster_url": image_url(result.get("poster_path")),
            "episodes": {
                str(ep.get("episode_number")): {
                    "title": ep.get("name") or "",
                    "overview": ep.get("overview") or "",
                    "still_url": image_url(ep.get("still_path"), "w300"),
                    "air_date": ep.get("air_date") or "",
                    "runtime": ep.get("runtime"),
                }
                for ep in result.get("episodes", [])
                if isinstance(ep.get("episode_number"), int)
            },
        }
        _cache_put(key, data)
        return data


@router.get("/settings")
def metadata_settings():
    return {
        "automatic_tv_metadata": True,
        "automatic_provider": "TVmaze",
        "tmdb_configured": token_status(),
        "optional_provider": "TMDB",
        "notice": "TVmaze data is CC BY-SA; TMDB is optional and requires a key.",
    }


@router.post("/settings")
def set_metadata_settings(data: TokenRequest):
    token = data.token.strip()
    # Validate credentials before replacing previously working settings.
    if _call("authentication", token=token) is None:
        raise HTTPException(422, "TMDB rejected this token or could not be reached")
    with LOCK:
        TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        fd, path = tempfile.mkstemp(prefix=".metadata-", dir=TOKEN_FILE.parent)
        try:
            with os.fdopen(fd, "w") as stream:
                json.dump({"token": token}, stream)
            os.chmod(path, 0o600)
            os.replace(path, TOKEN_FILE)
        finally:
            if os.path.exists(path):
                os.unlink(path)
    return {"tmdb_configured": True}


@router.delete("/settings")
def clear_metadata_settings():
    if os.environ.get("TMDB_READ_ACCESS_TOKEN"):
        raise HTTPException(409, "Token is configured in the server environment")
    with LOCK:
        TOKEN_FILE.unlink(missing_ok=True)
    return {"tmdb_configured": False}
