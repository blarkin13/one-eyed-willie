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
from threading import Lock, RLock

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
                if time.time() - row["updated_at"] < SNAPSHOT_SECONDS and all("youtube_trailer_id" in m for m in cached):
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
                "youtube_trailer_id": film.get("youTubeTrailerId") or "",
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


_PATH_INDEX = {}          # library_id -> (signature, {key: (info, file, root)})
_PATH_INDEX_LOCK = Lock()


def _movie_index(library_id):
    """Map every movie key in a library to its file with one pass over the media.

    Resolving a key used to re-parse every file in the library until it hit the
    match: ~55 ms per movie for 3,000 titles, so one 18-poster batch took ~1 s
    and each movie page paid the same. The index is rebuilt only when the
    library's media actually changes (the catalog revision moves on every scan
    that adds, changes or removes files; the row count and highest id also guard
    against changes that do not bump it, such as a deleted library).
    """
    with db() as conn:
        lib = conn.execute(
            "SELECT id,kind,path FROM libraries WHERE id=?", (library_id,)
        ).fetchone()
        if not lib or lib["kind"] != "movies":
            raise HTTPException(404, "Movie library not found")
        revision = conn.execute(
            "SELECT revision FROM catalog_state WHERE id=1").fetchone()[0]
        count, newest = conn.execute(
            "SELECT COUNT(*),COALESCE(MAX(id),0) FROM media WHERE library_id=?",
            (library_id,)).fetchone()
    signature = (revision, count, newest, lib["path"])
    cached = _PATH_INDEX.get(library_id)
    if cached and cached[0] == signature:
        return cached[1]
    with _PATH_INDEX_LOCK:
        cached = _PATH_INDEX.get(library_id)
        if cached and cached[0] == signature:
            return cached[1]
        with db() as conn:
            rows = conn.execute(
                "SELECT path,source_root FROM media WHERE library_id=? ORDER BY path",
                (library_id,)).fetchall()
        index = {}
        for row in rows:
            root = Path(row["source_root"] or lib["path"])
            try:
                parsed = movie_info(row["path"], root)
            except (ValueError, OSError):
                continue
            # The first file (by path) with a key wins, as the old scan did.
            index.setdefault(parsed["key"], (parsed, Path(row["path"]), root))
        _PATH_INDEX[library_id] = (signature, index)
        return index


def _movie_path(library_id, key):
    entry = _movie_index(library_id).get(key)
    if entry is None:
        raise HTTPException(404, "Movie not found")
    parsed, path, root = entry
    return dict(parsed), path, root


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


def _tmdb_id_for_title(title, year):
    """Exact title/year match when Radarr has no TMDB ID. Cached and opt-in."""
    from .metadata import token_status, _call, _cache_get, _cache_put, LOCK as META_LOCK
    if not token_status():
        return None
    key = "movie-match:v1:" + _simple(title) + ":" + str(year or "")
    with META_LOCK:
        cached = _cache_get(key)
        if cached is not None:
            return cached.get("id")
        result = _call("search/movie", query={
            "query": title, "year": year or "",
            "include_adult": "false", "language": "en-US",
        })
        if not isinstance(result, dict):
            return None
        matches = [
            m for m in result.get("results", [])
            if isinstance(m, dict) and (
                _simple(m.get("title")) == _simple(title)
                or _simple(m.get("original_title")) == _simple(title)
            ) and isinstance(m.get("id"), int) and m["id"] > 0
            and (not year or not m.get("release_date")
                 or (str(m["release_date"])[:4].isdigit() and
                     abs(int(str(m["release_date"])[:4]) - year) <= 1))
        ]
        found = matches[0]["id"] if len(matches) == 1 else None
        _cache_put(key, {"id": found} if found else {})
        return found


def _movie_extras(radarr):
    """Optional, cached TMDB cast and user reviews; never scrape review sites."""
    tmdb_id = radarr.get("tmdb_id")
    if not isinstance(tmdb_id, int) or tmdb_id <= 0:
        return {}
    from .metadata import token_status, _call, _cache_get, _cache_put, image_url, LOCK as META_LOCK
    if not token_status():
        return {}
    key = "movie-extras:v4:" + str(tmdb_id)
    with META_LOCK:
        cached = _cache_get(key)
        if cached is not None:
            return cached
        details = _call("movie/" + str(tmdb_id),
                        query={"language": "en-US",
                               "append_to_response": "credits,reviews,videos"})
        if details is None:
            return {}
        credits = details.get("credits") or {}
        reviews = details.get("reviews") or {}
        cast = []
        for person in (credits or {}).get("cast", [])[:15]:
            if not isinstance(person, dict):
                continue
            cast.append({"tmdb_id": person.get("id"), "name": str(person.get("name") or "")[:90],
                         "character": str(person.get("character") or "")[:90],
                         "photo": register_remote(image_url(person.get("profile_path"), "w185"))})
        user_reviews = []
        for review in (reviews or {}).get("results", [])[:12]:
            if not isinstance(review, dict):
                continue
            user_reviews.append({
                "author": str(review.get("author") or "TMDB contributor")[:80],
                "excerpt": str(review.get("content") or "")[:3500],
                "source": "TMDB",
            })
        videos = (details or {}).get("videos") or {}
        trailer = next((
            str(v.get("key")) for v in videos.get("results", [])
            if isinstance(v, dict) and v.get("site") == "YouTube"
            and v.get("type") == "Trailer"
            and re.fullmatch(r"[A-Za-z0-9_-]{11}", str(v.get("key") or ""))
        ), None)
        extras = {
            "trailer_key": trailer,
            "overview": str((details or {}).get("overview") or "")[:1200],
            "poster_url": register_remote(image_url(details.get("poster_path"), "w500")),
            "backdrop_url": register_remote(image_url(details.get("backdrop_path"), "w1280")),
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
            "runtime": (details or {}).get("runtime"),
            "genres": [g.get("name") for g in (details or {}).get("genres", [])
                       if isinstance(g, dict) and g.get("name")],
        }
        _cache_put(key, extras)
        return extras


def _manual_movie_match(library_id, key):
    with db() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS movie_manual_matches "
                     "(library_id INTEGER NOT NULL, movie_key TEXT NOT NULL, tmdb_id INTEGER NOT NULL, "
                     "PRIMARY KEY (library_id,movie_key))")
        row = conn.execute("SELECT tmdb_id FROM movie_manual_matches "
                           "WHERE library_id=? AND movie_key=?", (library_id, key)).fetchone()
    return row["tmdb_id"] if row else None


class MovieMatchRequest(BaseModel):
    tmdb_id: int = Field(gt=0)


@router.get("/match/search")
def movie_match_search(
    library_id: int = Query(ge=1), key: str = Query(min_length=1, max_length=300),
    query: str = Query(min_length=2, max_length=120),
):
    _movie_path(library_id, key)
    from .metadata import token_status, _call, image_url
    if not token_status():
        return {"results": [], "tmdb_connected": False}
    data = _call("search/movie", query={"query": query, "language": "en-US",
                                        "include_adult": "false"})
    results = []
    for item in (data or {}).get("results", [])[:20]:
        if not isinstance(item, dict) or not isinstance(item.get("id"), int):
            continue
        results.append({
            "tmdb_id": item["id"], "title": str(item.get("title") or "")[:120],
            "year": str(item.get("release_date") or "")[:4],
            "overview": str(item.get("overview") or "")[:300],
            "poster_url": image_url(item.get("poster_path"), "w185"),
        })
    return {"results": results, "tmdb_connected": True}


@router.put("/match")
def set_movie_match(
    library_id: int = Query(ge=1), key: str = Query(min_length=1, max_length=300),
    change: MovieMatchRequest = None,
):
    _movie_path(library_id, key)
    from .metadata import _call, token_status
    if not token_status():
        raise HTTPException(409, "Connect TMDB under Settings → Metadata to fix movie matches.")
    if change is None:
        raise HTTPException(422, "Select a movie to match")
    result = _call("movie/" + str(change.tmdb_id), query={"language": "en-US"})
    if not isinstance(result, dict) or result.get("id") != change.tmdb_id:
        raise HTTPException(422, "Selected movie could not be loaded from TMDB")
    with db() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS movie_manual_matches "
                     "(library_id INTEGER NOT NULL, movie_key TEXT NOT NULL, tmdb_id INTEGER NOT NULL, "
                     "PRIMARY KEY (library_id,movie_key))")
        conn.execute("INSERT INTO movie_manual_matches(library_id,movie_key,tmdb_id) VALUES(?,?,?) "
                     "ON CONFLICT(library_id,movie_key) DO UPDATE SET tmdb_id=excluded.tmdb_id",
                     (library_id, key, change.tmdb_id))
        conn.commit()
    from .poster_index import invalidate
    invalidate("movies", library_id, key)
    return {"matched": True, "title": result.get("title"), "tmdb_id": change.tmdb_id}


@router.delete("/match")
def clear_movie_match(
    library_id: int = Query(ge=1), key: str = Query(min_length=1, max_length=300),
):
    _movie_path(library_id, key)
    with db() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS movie_manual_matches "
                     "(library_id INTEGER NOT NULL, movie_key TEXT NOT NULL, tmdb_id INTEGER NOT NULL, "
                     "PRIMARY KEY (library_id,movie_key))")
        conn.execute("DELETE FROM movie_manual_matches WHERE library_id=? AND movie_key=?",
                     (library_id, key))
        conn.commit()
    from .poster_index import invalidate
    invalidate("movies", library_id, key)
    return {"matched": False}


def _details(library_id, key, snapshot=None, *, enrich=True, include_video_format=True):
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
    if enrich and not radarr.get("tmdb_id") and not _manual_movie_match(library_id, key):
        tmdb_id = _tmdb_id_for_title(parsed["title"], parsed["year"])
        if tmdb_id:
            radarr = {**radarr, "tmdb_id": tmdb_id}
    manual_id = _manual_movie_match(library_id, key)
    if manual_id:
        radarr = {**radarr, "tmdb_id": manual_id}
    extras = _movie_extras(radarr) if (enrich or manual_id) else {}
    result = {
        **extras,
        "ratings": radarr.get("ratings") or {},
        "studio": radarr.get("studio") or "",
        "certification": radarr.get("certification") or "",
        "trailer_key": (
            radarr.get("youtube_trailer_id")
            if re.fullmatch(r"[A-Za-z0-9_-]{11}",
                            str(radarr.get("youtube_trailer_id") or ""))
            else extras.get("trailer_key")
        ),
        "library_id": library_id, "key": key, "title": parsed["title"],
        "media_id": entry["id"] if entry else None,
        "watched": bool(entry and entry["completed"]),
        "position_seconds": entry["position_seconds"] if entry and entry["position_seconds"] else 0,
        "duration_seconds": entry["duration_seconds"] if entry and entry["duration_seconds"] else 0,
        "year": parsed["year"], "poster_url": (extras.get("poster_url") if manual_id else None) or poster_url or extras.get("poster_url"),
        "backdrop_url": (extras.get("backdrop_url") if manual_id else None) or backdrop_url or extras.get("backdrop_url"),
        "overview": (extras.get("overview") if manual_id else None) or nfo.get("overview") or radarr.get("overview") or "",
        "runtime": nfo.get("runtime") or radarr.get("runtime") or extras.get("runtime"),
        "genres": nfo.get("genres") or radarr.get("genres") or extras.get("genres") or [],
        "imdb_url": "https://www.imdb.com/title/" + imdb_id + "/" if imdb_id else None,
        "metadata_source": "TMDB (manual match)" if manual_id else ("Local movie files" if nfo else ("Radarr" if radarr else ("TMDB" if extras else None))),
        "manual_match": manual_id,
    }
    if enrich and include_video_format:
        from .video_info import video_format
        result["video_format"] = video_format(video)
    if enrich and isinstance(result.get("poster_url"), str):
        from .poster_index import remember
        remember("movies", library_id, key, result["poster_url"])
    return result


@router.get("/details")
def movie_details(
    library_id: int = Query(ge=1), key: str = Query(min_length=1, max_length=300)
):
    return _details(library_id, key)


@router.post("/posters")
def movie_posters(batch: PosterBatch):
    from .artwork import thumbnail_url
    snapshot = _snapshot()
    entries = []
    for item in batch.items:
        try:
            data = _details(item.library_id, item.key, snapshot=snapshot, enrich=False)
            entries.append({
                "library_id": item.library_id,
                "key": item.key,
                # Grid-sized thumbnail, like indexed posters. The full image
                # (a local or Radarr poster can be several MB) is only needed
                # on the detail page; the client falls back to it on error.
                "poster_url": thumbnail_url(data["poster_url"]),
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
