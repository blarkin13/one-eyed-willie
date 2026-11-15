"""Automatic movie metadata from local movie folders and an optional local Radarr instance.

No IMDb or Rotten Tomatoes scraping. Movie title/year from indexed files are
authoritative. Poster images are copied into the existing local artwork cache.
"""
import ipaddress
import json
import os
import re
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from threading import RLock

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from .artwork import MEDIA_ROOT, register_local, register_remote, register_radarr
from .catalog import movie_info
from .library import db
from .metadata import _simple

router = APIRouter(prefix="/api/movies")
SETTINGS_PATH = Path(os.environ.get("RADARR_CONFIG_PATH", "/data/radarr-settings.json"))
LOCK = RLock()
SNAPSHOT_SECONDS = 6 * 60 * 60
MAX_RESPONSE = 20 * 1024 * 1024
IMAGE_NAMES = ("poster.jpg", "poster.jpeg", "poster.png", "poster.webp",
               "folder.jpg", "folder.png", "cover.jpg", "cover.png")
IMDB_ID = re.compile(r"^tt[0-9]{7,10}$")


class RadarrSettingsInput(BaseModel):
    url: str = Field(min_length=7, max_length=180)
    api_key: str = Field(min_length=12, max_length=128)


class MovieReference(BaseModel):
    library_id: int = Field(gt=0)
    key: str = Field(min_length=1, max_length=300)


class PosterBatch(BaseModel):
    items: list[MovieReference] = Field(min_length=1, max_length=60)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _base_url(raw):
    """Only explicit local Radarr URLs; never proxy arbitrary internet addresses."""
    try:
        parsed = urllib.parse.urlsplit(raw.strip())
        host = (parsed.hostname or "").lower()
        if parsed.scheme not in ("http", "https") or not host:
            raise ValueError
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError
        if parsed.path not in ("", "/") or not parsed.port:
            raise ValueError
        if host not in ("host.docker.internal", "radarr", "sonarr"):
            address = ipaddress.ip_address(host)
            if not isinstance(address, ipaddress.IPv4Address):
                raise ValueError
            if not address.is_private or address.is_link_local or address.is_multicast:
                raise ValueError
            if address.is_loopback or address.is_unspecified or address.is_reserved:
                raise ValueError
        return f"{parsed.scheme}://{host}:{parsed.port}"
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            422,
            "Use Radarr's LAN address, for example http://192.168.86.29:7878. "
            "Public addresses are not accepted.",
        ) from exc


def _settings():
    env_url = os.environ.get("RADARR_URL", "").strip()
    env_key = os.environ.get("RADARR_API_KEY", "").strip()
    if env_url and env_key:
        try:
            return {"url": _base_url(env_url), "api_key": env_key, "managed": "environment"}
        except HTTPException:
            return None
    try:
        data = json.loads(SETTINGS_PATH.read_text())
        if not data.get("api_key"):
            return None
        return {
            "url": _base_url(data["url"]), "api_key": data["api_key"],
            "managed": "settings",
        }
    except (ValueError, OSError, KeyError, TypeError, HTTPException):
        return None


def _call(url, key, endpoint):
    # The only reachable endpoint is Radarr's movie list.
    if endpoint != "/api/v3/movie":
        return None
    request = urllib.request.Request(
        _base_url(url) + endpoint,
        headers={"X-Api-Key": key, "Accept": "application/json",
                 "User-Agent": "OneEyedWillie/0.8"},
    )
    try:
        opener = urllib.request.build_opener(_NoRedirect())
        with opener.open(request, timeout=8) as response:
            data = response.read(MAX_RESPONSE + 1)
            if len(data) > MAX_RESPONSE:
                return None
            result = json.loads(data)
            return result if isinstance(result, list) else None
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, ValueError):
        return None


def _snapshot_table(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS radarr_snapshot (
        id INTEGER PRIMARY KEY CHECK (id=1),
        snapshot TEXT NOT NULL, updated_at INTEGER NOT NULL,
        source_url TEXT NOT NULL
    )""")


def _snapshot():
    settings = _settings()
    if not settings:
        return []
    with LOCK:
        with db() as conn:
            _snapshot_table(conn)
            row = conn.execute(
                "SELECT snapshot,updated_at,source_url FROM radarr_snapshot WHERE id=1"
            ).fetchone()
        if row and row["source_url"] == settings["url"]:
            try:
                cached = json.loads(row["snapshot"])
                if time.time() - row["updated_at"] < SNAPSHOT_SECONDS:
                    return cached
            except ValueError:
                pass
        current = _call(settings["url"], settings["api_key"], "/api/v3/movie")
        if current is None:
            if row and row["source_url"] == settings["url"]:
                try:
                    return json.loads(row["snapshot"])
                except ValueError:
                    pass
            return []
        # Never cache Radarr credentials, full file paths, or unnecessary fields.
        compact = []
        for film in current:
            if not isinstance(film, dict):
                continue
            images = film.get("images") or []
            art = next((im for im in images if
                        isinstance(im, dict) and im.get("coverType") == "poster"), {})
            backdrop = next((im for im in images if
                             isinstance(im, dict) and im.get("coverType") == "fanart"), {})
            compact.append({
                "title": film.get("title") or "",
                "original_title": film.get("originalTitle") or "",
                "year": film.get("year"),
                "overview": film.get("overview") or "",
                "runtime": film.get("runtime"),
                "genres": film.get("genres") if isinstance(film.get("genres"), list) else [],
                "imdb_id": film.get("imdbId"),
                "tmdb_id": film.get("tmdbId"),
                "ratings": {name: {"value": value.get("value"), "votes": value.get("votes")}
                            for name, value in (film.get("ratings") or {}).items()
                            if name in ("imdb", "tmdb", "rottenTomatoes", "metacritic")
                            and isinstance(value, dict)},
                "studio": film.get("studio") or "",
                "certification": film.get("certification") or "",
                "original_language": film.get("originalLanguage") or {},
                "poster_url": art.get("remoteUrl"),
                "poster_internal": art.get("url"),
                "backdrop_url": backdrop.get("remoteUrl"),
                "backdrop_internal": backdrop.get("url"),
            })
        with db() as conn:
            _snapshot_table(conn)
            conn.execute(
                "INSERT INTO radarr_snapshot(id,snapshot,updated_at,source_url) "
                "VALUES(1,?,?,?) ON CONFLICT(id) DO UPDATE SET "
                "snapshot=excluded.snapshot,updated_at=excluded.updated_at,"
                "source_url=excluded.source_url",
                (json.dumps(compact), int(time.time()), settings["url"]),
            )
        return compact


def _movie_match(title, year, snapshot):
    normalized = _simple(title)
    if not normalized:
        return {}
    candidates = [
        m for m in snapshot
        if normalized in (_simple(m.get("title")), _simple(m.get("original_title")))
    ]
    if year:
        candidates = [
            m for m in candidates
            if m.get("year") is not None and abs(int(m["year"]) - int(year)) <= 1
        ]
    if len(candidates) != 1:
        return {}
    return candidates[0]


def _movie_path(library_id, key):
    with db() as conn:
        lib = conn.execute(
            "SELECT id,kind,path FROM libraries WHERE id=?", (library_id,)
        ).fetchone()
        if not lib or lib["kind"] != "movies":
            raise HTTPException(404, "Movie library not found")
        rows = conn.execute(
            "SELECT path FROM media WHERE library_id=? ORDER BY path", (library_id,)
        ).fetchall()
    root = Path(lib["path"])
    for row in rows:
        try:
            parsed = movie_info(row["path"], root)
        except (ValueError, OSError):
            continue
        if parsed["key"] == key:
            return parsed, Path(row["path"]), root
    raise HTTPException(404, "Movie not found")


def _safe_sidecar(path, root, max_bytes=256_000):
    try:
        real = path.resolve(strict=True)
        if path.is_symlink() or not real.is_relative_to(root.resolve()):
            return None
        if not real.is_relative_to(MEDIA_ROOT) or real.stat().st_size > max_bytes:
            return None
        if not real.is_file():
            return None
        return real
    except (OSError, ValueError):
        return None


def _local_poster(video_path, root):
    candidates = [video_path.with_suffix(".jpg"), video_path.with_suffix(".png")]
    if video_path.parent != root:
        candidates += [video_path.parent / name for name in IMAGE_NAMES]
    for candidate in candidates:
        if _safe_sidecar(candidate, root, max_bytes=5 * 1024 * 1024):
            poster = register_local(candidate)
            if poster:
                return poster
    return None


def _local_nfo(video_path, root):
    candidates = [video_path.with_suffix(".nfo")]
    if video_path.parent != root:
        candidates.append(video_path.parent / "movie.nfo")
    for candidate in candidates:
        safe = _safe_sidecar(candidate, root)
        if not safe:
            continue
        try:
            element = ET.fromstring(safe.read_bytes())
            if element.tag != "movie":
                continue
            text = lambda k: (element.findtext(k) or "").strip()
            imdb_id = text("imdbid")
            return {
                "overview": text("plot"),
                "runtime": int(text("runtime")) if text("runtime").isdigit() else None,
                "imdb_id": imdb_id if IMDB_ID.fullmatch(imdb_id) else None,
                "genres": [x.text for x in element.findall("genre") if x.text],
            }
        except (ET.ParseError, OSError, ValueError):
            pass
    return {}


def _movie_extras(radarr):
    """Optional, cached TMDB cast and user reviews; never scrape review sites."""
    tmdb_id = radarr.get("tmdb_id")
    if not isinstance(tmdb_id, int) or tmdb_id <= 0:
        return {}
    from .metadata import token_status, _call, _cache_get, _cache_put, image_url, LOCK as META_LOCK
    if not token_status():
        return {}
    key = "movie-extras:" + str(tmdb_id)
    with META_LOCK:
        cached = _cache_get(key)
        if cached is not None:
            return cached
        details = _call("movie/" + str(tmdb_id),
                        query={"language": "en-US",
                               "append_to_response": "credits,reviews"})
        if details is None:
            return {}
        credits = details.get("credits") or {}
        reviews = details.get("reviews") or {}
        cast = []
        for person in (credits or {}).get("cast", [])[:15]:
            if not isinstance(person, dict):
                continue
            cast.append({"name": str(person.get("name") or "")[:90],
                         "character": str(person.get("character") or "")[:90],
                         "photo": register_remote(image_url(person.get("profile_path"), "w185"))})
        user_reviews = []
        for review in (reviews or {}).get("results", [])[:4]:
            if not isinstance(review, dict):
                continue
            user_reviews.append({
                "author": str(review.get("author") or "TMDB contributor")[:80],
                "excerpt": str(review.get("content") or "")[:850],
                "source": "TMDB",
            })
        extras = {
            "cast": cast, "reviews": user_reviews,
            "tagline": str((details or {}).get("tagline") or "")[:250],
            "release_date": (details or {}).get("release_date"),
            "budget": (details or {}).get("budget"),
            "revenue": (details or {}).get("revenue"),
            "production_companies": [
                str(studio.get("name") or "")[:100]
                for studio in (details or {}).get("production_companies", [])[:5]
                if isinstance(studio, dict)
            ],
            "tmdb_rating": (details or {}).get("vote_average"),
            "tmdb_votes": (details or {}).get("vote_count"),
        }
        _cache_put(key, extras)
        return extras


def _details(library_id, key, snapshot=None):
    parsed, video, root = _movie_path(library_id, key)
    radarr = _movie_match(parsed["title"], parsed["year"],
                           _snapshot() if snapshot is None else snapshot)
    nfo = _local_nfo(video, root)
    poster_url = (_local_poster(video, root) or register_remote(radarr.get("poster_url"))
                  or register_radarr(radarr.get("poster_internal")) )
    backdrop_url = (register_remote(radarr.get("backdrop_url"))
                    or register_radarr(radarr.get("backdrop_internal")) )
    imdb_id = nfo.get("imdb_id") or radarr.get("imdb_id")
    imdb_id = imdb_id if isinstance(imdb_id, str) and IMDB_ID.fullmatch(imdb_id) else None
    with db() as conn:
        entry = conn.execute(
            "SELECT m.id,p.position_seconds,p.duration_seconds,p.completed "
            "FROM media m LEFT JOIN playback_progress p ON p.media_id=m.id "
            "WHERE m.library_id=? AND m.path=? ORDER BY m.id LIMIT 1",
            (library_id, str(video)),
        ).fetchone()
    extras = _movie_extras(radarr)
    return {
        **extras,
        "ratings": radarr.get("ratings") or {},
        "studio": radarr.get("studio") or "",
        "certification": radarr.get("certification") or "",
        "library_id": library_id, "key": key, "title": parsed["title"],
        "media_id": entry["id"] if entry else None,
        "watched": bool(entry and entry["completed"]),
        "position_seconds": entry["position_seconds"] if entry and entry["position_seconds"] else 0,
        "duration_seconds": entry["duration_seconds"] if entry and entry["duration_seconds"] else 0,
        "year": parsed["year"], "poster_url": poster_url,
        "backdrop_url": backdrop_url,
        "overview": nfo.get("overview") or radarr.get("overview") or "",
        "runtime": nfo.get("runtime") or radarr.get("runtime"),
        "genres": nfo.get("genres") or radarr.get("genres") or [],
        "imdb_url": "https://www.imdb.com/title/" + imdb_id + "/" if imdb_id else None,
        "metadata_source": "Local movie files" if nfo else ("Radarr" if radarr else None),
    }


@router.get("/details")
def movie_details(
    library_id: int = Query(ge=1), key: str = Query(min_length=1, max_length=300)
):
    return _details(library_id, key)


@router.post("/posters")
def movie_posters(batch: PosterBatch):
    snapshot = _snapshot()
    entries = []
    for item in batch.items:
        try:
            data = _details(item.library_id, item.key, snapshot=snapshot)
            entries.append({
                "library_id": item.library_id,
                "key": item.key,
                "poster_url": data["poster_url"],
            })
        except HTTPException:
            continue
    return {"items": entries}


@router.get("/source")
def movie_source():
    settings = _settings()
    return {
        "connected": bool(settings), "source": "Radarr",
        "address": settings["url"] if settings else None,
        "managed": settings["managed"] if settings else None,
    }


@router.put("/source")
def save_radarr_source(settings: RadarrSettingsInput):
    url = _base_url(settings.url)
    key = settings.api_key.strip()
    if _call(url, key, "/api/v3/movie") is None:
        raise HTTPException(422, "Could not connect to Radarr using that address and API key")
    with LOCK:
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        fd, temp = tempfile.mkstemp(prefix=".radarr-", dir=SETTINGS_PATH.parent)
        try:
            with os.fdopen(fd, "w") as stream:
                json.dump({"url": url, "api_key": key}, stream)
            os.chmod(temp, 0o600)
            os.replace(temp, SETTINGS_PATH)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)
        with db() as conn:
            _snapshot_table(conn)
            conn.execute("DELETE FROM radarr_snapshot")
    return {"connected": True, "source": "Radarr"}


@router.delete("/source")
def remove_radarr_source():
    if os.environ.get("RADARR_URL") and os.environ.get("RADARR_API_KEY"):
        raise HTTPException(409, "Radarr connection is managed by the server environment")
    with LOCK:
        SETTINGS_PATH.unlink(missing_ok=True)
        with db() as conn:
            _snapshot_table(conn)
            conn.execute("DELETE FROM radarr_snapshot")
    return {"connected": False}
