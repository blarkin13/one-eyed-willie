"""Automatic, keyless TV metadata from the public TVmaze API.

TVmaze public data is CC BY-SA: show attribution to the originating TVmaze URL.
Local folders and episodes remain authoritative; the provider only adds display data.
"""
import html
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

from .metadata import _cache_get, _cache_put, LOCK, _simple

API_ROOT = "https://api.tvmaze.com"
IMAGE_ROOT = "https://static.tvmaze.com/uploads/images/"
TMDB_FALLBACK_NOTE = "No account or API key is required for TVmaze."

class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.fragments = []
        self.skip = 0
    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
        if tag in ("br", "p", "li") and not self.skip:
            self.fragments.append(" ")
    def handle_endtag(self, tag):
        if tag in ("script", "style") and self.skip:
            self.skip -= 1
        if tag in ("p", "li") and not self.skip:
            self.fragments.append(" ")
    def handle_data(self, data):
        if not self.skip:
            self.fragments.append(data)

def plain(value):
    if not value:
        return ""
    parser = _Text()
    parser.feed(str(value))
    return " ".join("".join(parser.fragments).split())

def image_url(images, size="medium"):
    if not isinstance(images, dict):
        return None
    url = images.get(size) or images.get("original")
    if not isinstance(url, str):
        return None
    return url if url.startswith(IMAGE_ROOT) else None

# A failed request (outage, rate limit, no route) used to be retried on every
# page open, each attempt waiting up to the 6 s timeout while holding the global
# metadata lock, so one bad minute made every show page crawl. Remember failures
# briefly, in memory only, and let successes be cached as before.
FAILURE_TTL_SECONDS = 120
_FAILED_UNTIL = {}


def _get(path, query=None):
    url = API_ROOT + path
    if query:
        url += "?" + urllib.parse.urlencode(query)
    blocked_until = _FAILED_UNTIL.get(url)
    if blocked_until is not None:
        if time.monotonic() < blocked_until:
            return None
        _FAILED_UNTIL.pop(url, None)
    request = urllib.request.Request(url, headers={
        "Accept": "application/json", "User-Agent": "OneEyedWillie/0.6 (personal TV metadata)"
    })
    try:
        with urllib.request.urlopen(request, timeout=6) as response:
            import json
            return json.loads(response.read(2_000_000))
    except (urllib.error.HTTPError, urllib.error.URLError, OSError, TimeoutError, ValueError):
        if len(_FAILED_UNTIL) > 2048:
            _FAILED_UNTIL.clear()
        _FAILED_UNTIL[url] = time.monotonic() + FAILURE_TTL_SECONDS
        return None

# Network requests must not run while holding the global metadata LOCK: it is
# shared by every provider and by the SQLite cache helpers, so one slow or
# timing-out TVmaze call used to stall every other metadata lookup. The LOCK now
# only guards the short cache reads/writes; a per-key lock stops two requests
# for the same show (the show page and its poster) from fetching it twice.
_KEY_LOCKS = {}
_KEY_LOCKS_GUARD = threading.Lock()
_MAX_KEY_LOCKS = 4096


def _key_lock(key):
    with _KEY_LOCKS_GUARD:
        if len(_KEY_LOCKS) > _MAX_KEY_LOCKS:
            _KEY_LOCKS.clear()      # holders keep their lock object; only reuse is lost
        return _KEY_LOCKS.setdefault(key, threading.Lock())


def _cached_fetch(key, fetch, empty):
    """Return the cached value, else run ``fetch() -> (value, cacheable)`` once."""
    with LOCK:
        cached = _cache_get(key)
    if cached is not None:
        return cached
    with _key_lock(key):
        with LOCK:
            cached = _cache_get(key)      # a concurrent request may have filled it
        if cached is not None:
            return cached
        value, cacheable = fetch()
        if cacheable:
            with LOCK:
                _cache_put(key, value)
        return value if value is not None else empty


def _valid_year(first_aired, target):
    if not target or not first_aired:
        return True
    try:
        return abs(int(first_aired[:4]) - int(target)) <= 1
    except (ValueError, TypeError):
        return False

def show_metadata(title, year=None):
    key = "tvmaze:show:v3:" + _simple(title) + ":" + str(year or "")

    def fetch():
        result = _get("/search/shows", {"q": title})
        if not isinstance(result, list):
            return {}, False              # provider unreachable: do not cache
        matches = [
            entry["show"] for entry in result
            if isinstance(entry, dict) and isinstance(entry.get("show"), dict)
            and _simple(entry["show"].get("name")) == _simple(title)
            and _valid_year(entry["show"].get("premiered"), year)
        ]
        if not matches:
            return {}, True               # a real "no match" is cached, as before
        show = matches[0]
        found, complete = _show_by_id(show.get("id"), show=show)
        # A show whose seasons request failed is returned for this request but
        # not cached, so it does not stay season-less until the cache expires.
        return found, bool(found) and complete

    return _cached_fetch(key, fetch, {})

def show_metadata_by_id(show_id, show=None):
    """Fetch an explicit TVmaze show without fuzzy matching (cached)."""
    if not isinstance(show_id, int) or show_id <= 0:
        return {}
    if show is not None:
        return _show_by_id(show_id, show=show)[0]
    return _cached_fetch("tvmaze:id:v1:" + str(show_id),
                         lambda: _lookup_show(show_id), {})


def _lookup_show(show_id):
    found, complete = _show_by_id(show_id)
    return found, bool(found) and complete


def _show_by_id(show_id, show=None):
    """Return ``(metadata, seasons_complete)`` for a TVmaze show id."""
    if not isinstance(show_id, int) or show_id <= 0:
        return {}, False
    if show is None:
        show = _get("/shows/" + str(show_id))
    if not isinstance(show, dict) or show.get("id") != show_id:
        return {}, False
    raw_seasons = _get("/shows/" + str(show_id) + "/seasons")
    seasons_complete = isinstance(raw_seasons, list)
    if not seasons_complete:
        raw_seasons = []
    seasons = [
        {
            "number": s.get("number"),
            "name": s.get("name") or "Season " + str(s.get("number")),
            "overview": plain(s.get("summary")),
            "poster_url": image_url(s.get("image")) or image_url(show.get("image")),
            "episode_count": s.get("episodeOrder") or 0,
        }
        for s in raw_seasons if isinstance(s, dict) and isinstance(s.get("number"), int)
    ]
    provider_url = show.get("url")
    imdb_id = (show.get("externals") or {}).get("imdb")
    if not isinstance(imdb_id, str) or not re.fullmatch(r"tt[0-9]{7,9}", imdb_id):
        imdb_id = None
    result = {
        "imdb_id": imdb_id,
        "tvmaze_id": show_id,
        "title": show.get("name") or str(show_id),
        "overview": plain(show.get("summary")),
        "poster_url": image_url(show.get("image")),
        "backdrop_url": None,
        "seasons": seasons,
        "source": "TVmaze",
        "rating": (show.get("rating") or {}).get("average"),
        "runtime": show.get("averageRuntime") or show.get("runtime"),
        "status": show.get("status"),
        "network": (show.get("network") or show.get("webChannel") or {}).get("name"),
        "genres": show.get("genres") or [],
        "source_url": provider_url if isinstance(provider_url, str) and provider_url.startswith("https://www.tvmaze.com/shows/") else "https://www.tvmaze.com/",
    }

    return result, seasons_complete


def season_metadata(show_id, number):
    if not isinstance(show_id, int) or not isinstance(number, int):
        return {}
    key = "tvmaze:season:" + str(show_id) + ":" + str(number)

    def fetch():
        episodes = _get("/shows/" + str(show_id) + "/episodes", {"specials": 1})
        if not isinstance(episodes, list):
            return {}, False
        metadata_episodes = {
            str(ep["number"]): {
                "title": ep.get("name") or "",
                "overview": plain(ep.get("summary")),
                "still_url": image_url(ep.get("image")),
                "air_date": ep.get("airdate") or "",
                "runtime": ep.get("runtime"),
            } for ep in episodes
            if isinstance(ep, dict) and ep.get("season") == number and isinstance(ep.get("number"), int)
        }
        return {"name": "Season " + str(number), "overview": "", "poster_url": None,
                "episodes": metadata_episodes}, True

    return _cached_fetch(key, fetch, {})

def show_cast(show_id):
    """Public keyless TVmaze cast endpoint, cached to avoid repeated lookups."""
    if not isinstance(show_id, int) or show_id <= 0:
        return []
    key = "tvmaze:cast:" + str(show_id)

    def fetch():
        raw = _get("/shows/" + str(show_id) + "/cast")
        if not isinstance(raw, list):
            return [], False
        cast = []
        for entry in raw[:18]:
            if not isinstance(entry, dict):
                continue
            person = entry.get("person") or {}
            character = entry.get("character") or {}
            if not isinstance(person, dict) or not isinstance(character, dict):
                continue
            name = str(person.get("name") or "")[:90]
            if not name:
                continue
            cast.append({"tvmaze_id": person.get("id"), "name": name,
                         "character": str(character.get("name") or "")[:90],
                         "photo_url": image_url(person.get("image"), "medium")})
        return cast, True

    return _cached_fetch(key, fetch, [])
