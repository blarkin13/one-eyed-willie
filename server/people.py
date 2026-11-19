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
            "User-Agent": "YarrMedia/1.0 (personal media library; cast biographies)",
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


def same_person(left, right):
    return re.sub(r"[^a-z0-9]", "", str(left).casefold()) == re.sub(r"[^a-z0-9]", "", str(right).casefold())

def find_tmdb_id(name):
    data = tmdb_call("search/person", query={"query": name, "language": "en-US", "page": 1})
    if not isinstance(data, dict):
        return None
    candidates = [row for row in data.get("results", []) if isinstance(row, dict)
                  and same_person(row.get("name"), name) and isinstance(row.get("id"), int)]
    return candidates[0]["id"] if len(candidates) == 1 else None

def find_tvmaze_id(name):
    data = tvmaze_get("/search/people", {"q": name})
    if not isinstance(data, list):
        return None
    candidates = [row.get("person") for row in data if isinstance(row, dict)]
    candidates = [row for row in candidates if isinstance(row, dict)
                  and same_person(row.get("name"), name) and isinstance(row.get("id"), int)]
    return candidates[0]["id"] if len(candidates) == 1 else None

def wikipedia_portrait(name):
    query = urllib.parse.urlencode({
        "action": "query", "format": "json", "redirects": 1,
        "prop": "pageimages", "pithumbsize": 500, "titles": name
    })
    data = public_json("https://en.wikipedia.org/w/api.php?" + query)
    pages = ((data or {}).get("query") or {}).get("pages") or {}
    for page in pages.values():
        if not isinstance(page, dict) or not same_person(page.get("title"), name):
            continue
        url = ((page.get("thumbnail") or {}).get("source") or "")
        if url.startswith("https://upload.wikimedia.org/"):
            return url
    return None

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
        from .artwork import register_remote
        from .metadata import image_url
        titles.append({"title": title[:160], "year": year, "type": medium,
                       "character": str(credit.get("character") or "")[:100],
                       "tmdb_id": credit.get("id") if isinstance(credit.get("id"), int) and credit["id"] > 0 else None,
                       "poster_url": register_remote(image_url(credit.get("poster_path"), "w185"))})
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
        from .artwork import register_remote
        credits.append({"title": title[:160], "year": year, "type": "TV", "character": "",
                        "tvmaze_id": show.get("id") if isinstance(show.get("id"), int) and show["id"] > 0 else None,
                        "poster_url": register_remote(tvmaze_image(show.get("image")))})
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
    cache_key = "person-profile:v3:" + name.casefold() + ":" + str(tmdb_id or 0) + ":" + str(tvmaze_id or 0)
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached
    # Prefer verified IDs, then resolve older name-only cast entries by exact match.
    resolved_tmdb = tmdb_id or find_tmdb_id(name)
    resolved_tvmaze = tvmaze_id
    detail = tmdb_profile(resolved_tmdb) if resolved_tmdb else {}
    if detail.get("name") and not same_person(detail["name"], name):
        detail = {}
    if not detail.get("credits"):
        resolved_tvmaze = resolved_tvmaze or find_tvmaze_id(name)
        alternate = tvmaze_profile(resolved_tvmaze) if resolved_tvmaze else {}
        if alternate.get("name") and same_person(alternate["name"], name):
            if not detail:
                detail = alternate
            else:
                detail["credits"] = alternate.get("credits") or []
                detail["credit_source"] = alternate.get("credit_source") if detail["credits"] else detail.get("credit_source")
                detail["photo"] = detail.get("photo") or alternate.get("photo")
    wiki = wikipedia_summary(name)
    if wiki and not wiki.get("thumbnail") and not detail.get("photo"):
        wiki["thumbnail"] = wikipedia_portrait(name)
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

@router.get("/local-title")
def local_title(
    kind: str = Query(pattern="^(movie|tv)$"),
    title: str = Query(min_length=2, max_length=180),
    year: int = Query(default=0, ge=0, le=2100),
    tmdb_id: int = Query(default=0, ge=0),
):
    """Offer playback only when this credit matches a unique local library title.

    Never infer a local file from its TMDB ID alone. Movie manual-match IDs
    are authoritative; otherwise require a unique exact title/year match.
    """
    from .catalog import catalog
    from .metadata import _simple
    from .library import db
    target = "movies" if kind == "movie" else "tv"
    items = catalog(kind=target, search="", limit=100000).get("items", [])
    manual_keys = set()
    if target == "movies" and tmdb_id:
        try:
            with db() as conn:
                for row in conn.execute(
                    "SELECT library_id,movie_key FROM movie_manual_matches WHERE tmdb_id=?",
                    (tmdb_id,),
                ):
                    manual_keys.add((row["library_id"], row["movie_key"]))
        except Exception:
            pass  # Older databases may not have any manual matches.
    exact = [
        item for item in items
        if (item["library_id"], item["key"]) in manual_keys or (
            _simple(item["title"]) == _simple(title)
            and (not year or item.get("year") and abs(int(item["year"]) - year) <= 1)
        )
    ]
    if len(exact) != 1:
        return {"owned": False, "ambiguous": len(exact) > 1}
    item = exact[0]
    from urllib.parse import urlencode
    route = "/movie" if target == "movies" else "/tv/show"
    url = route + "?" + urlencode({"library_id": item["library_id"], "key": item["key"]})
    return {"owned": True, "href": url}
