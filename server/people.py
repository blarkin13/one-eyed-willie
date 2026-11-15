"""Read-only cast profiles assembled from credited metadata and Wikipedia summaries."""
import json
import re
import urllib.error
import urllib.parse
import urllib.request

from fastapi import APIRouter, Query
from .metadata import _call as tmdb_call, _cache_get, _cache_put
from .tvmaze import _get as tvmaze_get, image_url as tvmaze_image

router = APIRouter(prefix="/api/people")

def public_json(url):
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "OneEyedWillie/1.0 (personal media library; cast biographies)",
            "Accept": "application/json",
        })
        with urllib.request.urlopen(req, timeout=6) as response:
            return json.loads(response.read(1_000_000))
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError,
            ValueError, UnicodeError):
        return None

def wikipedia_summary(name):
    # Use exact page title only; a fuzzy search may identify a different person.
    slug = urllib.parse.quote(name.replace(" ", "_"), safe="")
    data = public_json("https://en.wikipedia.org/api/rest_v1/page/summary/" + slug)
    if not isinstance(data, dict) or data.get("type") == "disambiguation":
        return {}
    title = str(data.get("title") or "").strip()
    normalize = lambda value: re.sub(r"[^a-z0-9]", "", value.casefold())
    if normalize(title) != normalize(name):
        return {}
    if data.get("description") and not any(
        term in str(data["description"]).casefold()
        for term in ("actor", "actress", "performer", "comedian", "artist",
                     "filmmaker", "entertainer", "television", "film")
    ):
        return {}
    url = ((data.get("content_urls") or {}).get("desktop") or {}).get("page")
    return {
        "biography": str(data.get("extract") or "")[:1700],
        "wikipedia_url": url if isinstance(url, str) and url.startswith("https://en.wikipedia.org/wiki/") else None,
        "thumbnail": ((data.get("thumbnail") or {}).get("source")
                      if str((data.get("thumbnail") or {}).get("source") or "").startswith("https://upload.wikimedia.org/") else None),
    }

def tmdb_profile(person_id):
    if not person_id:
        return {}
    data = tmdb_call("person/" + str(person_id), query={
        "language": "en-US", "append_to_response": "combined_credits"
    })
    if not isinstance(data, dict):
        return {}
    credits = ((data.get("combined_credits") or {}).get("cast") or [])
    titles = []
    seen = set()
    for credit in sorted(credits, key=lambda c: (c.get("release_date") or c.get("first_air_date") or ""), reverse=True):
        title = str(credit.get("title") or credit.get("name") or "").strip()
        year = str(credit.get("release_date") or credit.get("first_air_date") or "")[:4]
        medium = "TV" if credit.get("media_type") == "tv" else "Movie"
        unique = (title, year, medium)
        if not title or unique in seen:
            continue
        seen.add(unique)
        titles.append({"title": title[:160], "year": year, "type": medium,
                       "character": str(credit.get("character") or "")[:100]})
        if len(titles) >= 75:
            break
    path = data.get("profile_path")
    photo = ("https://image.tmdb.org/t/p/w342" + path
             if isinstance(path, str) and re.fullmatch(r"/[A-Za-z0-9_-]+\.(jpg|png|webp)", path) else None)
    return {"name": str(data.get("name") or "")[:120],
            "biography": str(data.get("biography") or "")[:1700],
            "photo": photo, "credits": titles,
            "source_url": "https://www.themoviedb.org/person/" + str(person_id),
            "credit_source": "TMDB"}

def tvmaze_profile(person_id):
    if not person_id:
        return {}
    person = tvmaze_get("/people/" + str(person_id))
    if not isinstance(person, dict):
        return {}
    raw = tvmaze_get("/people/" + str(person_id) + "/castcredits", {"embed": "show"})
    credits = []
    seen = set()
    for entry in raw if isinstance(raw, list) else []:
        show = ((entry.get("_embedded") or {}).get("show") or {})
        title = str(show.get("name") or "").strip()
        year = str(show.get("premiered") or "")[:4]
        if not title or title in seen:
            continue
        seen.add(title)
        credits.append({"title": title[:160], "year": year, "type": "TV", "character": ""})
        if len(credits) >= 75:
            break
    return {"name": str(person.get("name") or "")[:120],
            "photo": tvmaze_image(person.get("image")),
            "credits": credits, "credit_source": "TVmaze",
            "source_url": person.get("url") if str(person.get("url") or "").startswith("https://www.tvmaze.com/") else None}

@router.get("/profile")
def profile(
    name: str = Query(min_length=2, max_length=120),
    tmdb_id: int | None = Query(default=None, ge=1),
    tvmaze_id: int | None = Query(default=None, ge=1),
):
    cache_key = "person-profile:v1:" + name.casefold() + ":" + str(tmdb_id or 0) + ":" + str(tvmaze_id or 0)
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached
    detail = (tmdb_profile(tmdb_id) if tmdb_id else
              tvmaze_profile(tvmaze_id) if tvmaze_id else {})
    # Do not silently show a profile for an unrelated person.
    if detail.get("name") and detail["name"].casefold() != name.casefold():
        detail = {}
    wiki = wikipedia_summary(name)
    result = {
        "name": name, "biography": wiki.get("biography") or detail.get("biography") or "",
        "biography_source": "Wikipedia" if wiki.get("biography") else ("TMDB" if detail.get("biography") else None),
        "wikipedia_url": wiki.get("wikipedia_url"),
        "photo": detail.get("photo") or wiki.get("thumbnail"),
        "credits": detail.get("credits") or [],
        "credit_source": detail.get("credit_source"),
        "source_url": detail.get("source_url"),
    }
    _cache_put(cache_key, result)
    return result
