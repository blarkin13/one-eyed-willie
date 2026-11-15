"""Automatic, keyless TV metadata from the public TVmaze API.

TVmaze public data is CC BY-SA: show attribution to the originating TVmaze URL.
Local folders and episodes remain authoritative; the provider only adds display data.
"""
import html
import re
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

def _get(path, query=None):
    url = API_ROOT + path
    if query:
        url += "?" + urllib.parse.urlencode(query)
    request = urllib.request.Request(url, headers={
        "Accept": "application/json", "User-Agent": "OneEyedWillie/0.6 (personal TV metadata)"
    })
    try:
        with urllib.request.urlopen(request, timeout=6) as response:
            import json
            return json.loads(response.read(2_000_000))
    except (urllib.error.HTTPError, urllib.error.URLError, OSError, TimeoutError, ValueError):
        return None

def _valid_year(first_aired, target):
    if not target or not first_aired:
        return True
    try:
        return abs(int(first_aired[:4]) - int(target)) <= 1
    except (ValueError, TypeError):
        return False

def show_metadata(title, year=None):
    key = "tvmaze:show:v2:" + _simple(title) + ":" + str(year or "")
    with LOCK:
        cached = _cache_get(key)
        if cached is not None:
            return cached
        result = _get("/search/shows", {"q": title})
        if not isinstance(result, list):
            return {}
        matches = [
            entry["show"] for entry in result
            if isinstance(entry, dict) and isinstance(entry.get("show"), dict)
            and _simple(entry["show"].get("name")) == _simple(title)
            and _valid_year(entry["show"].get("premiered"), year)
        ]
        if not matches:
            _cache_put(key, {})
            return {}
        show = matches[0]
        show_id = show.get("id")
        if not isinstance(show_id, int):
            return {}
        raw_seasons = _get("/shows/" + str(show_id) + "/seasons")
        if not isinstance(raw_seasons, list):
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
        result = {
            "tvmaze_id": show_id,
            "title": show.get("name") or title,
            "overview": plain(show.get("summary")),
            "poster_url": image_url(show.get("image")),
            "backdrop_url": None,
            "seasons": seasons,
            "source": "TVmaze",
            "rating": (show.get("rating") or {}).get("average"),
            "status": show.get("status"),
            "network": (show.get("network") or show.get("webChannel") or {}).get("name"),
            "genres": show.get("genres") or [],
            "source_url": provider_url if isinstance(provider_url, str) and provider_url.startswith("https://www.tvmaze.com/shows/") else "https://www.tvmaze.com/",
        }
        _cache_put(key, result)
        return result

def season_metadata(show_id, number):
    if not isinstance(show_id, int) or not isinstance(number, int):
        return {}
    key = "tvmaze:season:" + str(show_id) + ":" + str(number)
    with LOCK:
        cached = _cache_get(key)
        if cached is not None:
            return cached
        episodes = _get("/shows/" + str(show_id) + "/episodes", {"specials": 1})
        if not isinstance(episodes, list):
            return {}
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
        data = {"name": "Season " + str(number), "overview": "", "poster_url": None,
                "episodes": metadata_episodes}
        _cache_put(key, data)
        return data

def show_cast(show_id):
    """Public keyless TVmaze cast endpoint, cached to avoid repeated lookups."""
    if not isinstance(show_id, int) or show_id <= 0:
        return []
    key = "tvmaze:cast:" + str(show_id)
    with LOCK:
        cached = _cache_get(key)
        if cached is not None:
            return cached
        raw = _get("/shows/" + str(show_id) + "/cast")
        if not isinstance(raw, list):
            return []
        cast = []
        for entry in raw[:18]:
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
        _cache_put(key, cast)
        return cast
