"""Private Lidarr API connection (separate from Radarr/Sonarr discovery)."""
import ipaddress
import json
import os
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from threading import RLock

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/lidarr", tags=["lidarr"])
SETTINGS_FILE = Path(os.environ.get("LIDARR_CONFIG_PATH", "/data/lidarr-settings.json"))
LOCK = RLock()

class LidarrInput(BaseModel):
    url: str = Field(min_length=12, max_length=180)
    api_key: str = Field(min_length=12, max_length=128)

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

def _base_url(raw):
    """Allow only explicit local IPs or trusted Docker service hostnames."""
    try:
        parsed = urllib.parse.urlsplit(raw.strip())
        host = (parsed.hostname or "").lower()
        if parsed.scheme not in ("http", "https") or not host or not parsed.port:
            raise ValueError
        if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ("", "/"):
            raise ValueError
        if host not in ("lidarr", "host.docker.internal"):
            address = ipaddress.ip_address(host)
            if not isinstance(address, ipaddress.IPv4Address) or not address.is_private:
                raise ValueError
            if address.is_loopback or address.is_link_local or address.is_multicast or address.is_reserved or address.is_unspecified:
                raise ValueError
        return f"{parsed.scheme}://{host}:{parsed.port}"
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, "Use Lidarr's private LAN address, such as http://192.168.86.29:8686") from exc

def _settings():
    url = os.environ.get("LIDARR_URL", "")
    key = os.environ.get("LIDARR_API_KEY", "")
    if url and key:
        try:
            return {"url": _base_url(url), "api_key": key, "managed": "environment"}
        except HTTPException:
            return None
    try:
        data = json.loads(SETTINGS_FILE.read_text())
        return {"url": _base_url(data["url"]), "api_key": str(data["api_key"]), "managed": "settings"}
    except (OSError, ValueError, KeyError, TypeError, HTTPException):
        return None

def _probe(url, key):
    request = urllib.request.Request(
        url + "/api/v1/system/status",
        headers={"X-Api-Key":key, "Accept":"application/json", "User-Agent":"Yarr/1"},
        method="GET",
    )
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=9) as response:
            data = response.read(65537)
            if len(data) > 65536:
                raise HTTPException(502, "Lidarr returned an oversized response")
        status = json.loads(data)
        if not isinstance(status, dict) or not status.get("version"):
            raise HTTPException(502, "Unexpected Lidarr status response")
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise HTTPException(422, "Lidarr rejected the API key") from exc
        raise HTTPException(502, "Lidarr API request failed") from exc
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        raise HTTPException(502, "Lidarr is unreachable or returned an invalid response") from exc

@router.get("/connection")
def connection_status():
    setting = _settings()
    return {"connected": bool(setting), "address": setting["url"] if setting else None,
            "managed": setting["managed"] if setting else None}

@router.put("/connection")
def connect(payload: LidarrInput):
    address = _base_url(payload.url)
    key = payload.api_key.strip()
    _probe(address, key)
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOCK:
        fd, filename = tempfile.mkstemp(prefix=".lidarr-", dir=SETTINGS_FILE.parent)
        try:
            with os.fdopen(fd, "w") as handle:
                json.dump({"url": address, "api_key": key}, handle)
            os.chmod(filename, 0o600)
            os.replace(filename, SETTINGS_FILE)
        finally:
            if os.path.exists(filename):
                os.unlink(filename)
    return {"connected": True, "provider":"lidarr"}

@router.delete("/connection")
def disconnect():
    if os.environ.get("LIDARR_URL") and os.environ.get("LIDARR_API_KEY"):
        raise HTTPException(409, "Lidarr is configured in the server environment")
    with LOCK:
        SETTINGS_FILE.unlink(missing_ok=True)
    return {"connected":False}


# ---------------------------------------------------------------------------
# Artist details for the Music page: Lidarr metadata + artwork, and a short
# Wikipedia summary found through the artist's Wikidata link (no name guessing).

import re
import time
from fastapi import Query
from fastapi.responses import Response

WIKI_CACHE_FILE = SETTINGS_FILE.with_name("artist-wikipedia-cache.json")
WIKI_TTL = 30 * 24 * 3600
WIKI_FAIL_TTL = 24 * 3600
IMAGE_KINDS = ("poster", "fanart", "clearlogo", "banner")
LINK_NAMES = {"allmusic": "AllMusic", "discogs": "Discogs", "spotify": "Spotify",
              "imdb": "IMDb", "last": "Last.fm"}
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
_WEB = urllib.request.build_opener()
WIKI_LOCK = RLock()


def _lidarr_get(setting, resource, limit=8 * 1024 * 1024, raw=False):
    request = urllib.request.Request(setting["url"] + "/api/v1/" + resource,
        headers={"X-Api-Key": setting["api_key"], "User-Agent": "Yarr/1"})
    try:
        with _OPENER.open(request, timeout=10) as response:
            data = response.read(limit + 1)
            ctype = response.headers.get("Content-Type", "")
    except urllib.error.HTTPError as exc:
        raise HTTPException(404 if exc.code == 404 else 502, "Lidarr request failed") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise HTTPException(502, "Lidarr is unreachable") from exc
    if len(data) > limit:
        raise HTTPException(502, "Lidarr response too large")
    return (data, ctype) if raw else json.loads(data)


def _web_json(url):
    request = urllib.request.Request(url, headers={
        "User-Agent": "YarrMedia/1.0 (self-hosted media server)", "Accept": "application/json"})
    with _WEB.open(request, timeout=8) as response:
        data = response.read(2 * 1024 * 1024 + 1)
    if len(data) > 2 * 1024 * 1024:
        raise ValueError("response too large")
    return json.loads(data)


def _wiki_cache():
    try:
        data = json.loads(WIKI_CACHE_FILE.read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _wikipedia(qid):
    """Return {description, extract, url} for a Wikidata Q-id, cached on disk."""
    if not re.fullmatch(r"Q\d{1,12}", qid or ""):
        return None
    with WIKI_LOCK:
        cached = _wiki_cache().get(qid)
    if isinstance(cached, dict) and time.time() - cached.get("at", 0) < (
            WIKI_TTL if cached.get("data") else WIKI_FAIL_TTL):
        return cached.get("data")
    result = None
    try:
        entity = _web_json("https://www.wikidata.org/wiki/Special:EntityData/" + qid + ".json")
        title = entity["entities"][qid]["sitelinks"]["enwiki"]["title"]
        summary = _web_json("https://en.wikipedia.org/api/rest_v1/page/summary/" +
                            urllib.parse.quote(title.replace(" ", "_"), safe=""))
        page = (summary.get("content_urls") or {}).get("desktop", {}).get("page", "")
        if summary.get("extract"):
            result = {"description": str(summary.get("description") or "")[:200],
                      "extract": str(summary["extract"])[:2500],
                      "url": page if page.startswith("https://en.wikipedia.org/") else ""}
    except (OSError, ValueError, KeyError, TypeError, urllib.error.URLError):
        result = None
    with WIKI_LOCK:
        cache = _wiki_cache()
        cache[qid] = {"at": time.time(), "data": result}
        try:
            WIKI_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(prefix=".wiki-", dir=WIKI_CACHE_FILE.parent)
            with os.fdopen(fd, "w") as handle:
                json.dump(cache, handle)
            os.replace(tmp, WIKI_CACHE_FILE)
        except OSError:
            pass
    return result


@router.get("/artist-info")
def artist_info(name: str = Query(min_length=1, max_length=200)):
    """Metadata for a music-library artist name; empty result when unknown."""
    setting = _settings()
    if not setting:
        return {"found": False}
    try:
        artists = _lidarr_get(setting, "artist")
    except HTTPException:
        return {"found": False}
    wanted = name.strip().casefold()
    match = next((a for a in artists if isinstance(a, dict) and
                  str(a.get("artistName", "")).casefold() == wanted), None)
    if not match or not isinstance(match.get("id"), int):
        return {"found": False}
    links = match.get("links") if isinstance(match.get("links"), list) else []
    qid = None
    external = []
    for link in links:
        if not isinstance(link, dict):
            continue
        url, kind = str(link.get("url") or ""), str(link.get("name") or "")
        if kind == "wikidata":
            found = re.search(r"/(Q\d+)$", url)
            qid = found.group(1) if found else qid
        elif kind in LINK_NAMES and url.startswith("https://") and \
                not any(e["name"] == LINK_NAMES[kind] for e in external):
            external.append({"name": LINK_NAMES[kind], "url": url[:300]})
    kinds = {i.get("coverType") for i in match.get("images") or [] if isinstance(i, dict)}
    rating = match.get("ratings") if isinstance(match.get("ratings"), dict) else {}
    wiki = _wikipedia(qid) if qid else None
    if wiki and wiki.get("url"):
        external.insert(0, {"name": "Wikipedia", "url": wiki["url"]})
    return {
        "found": True, "id": match["id"],
        "name": str(match.get("artistName", ""))[:200],
        "type": str(match.get("artistType") or "")[:40],
        "disambiguation": str(match.get("disambiguation") or "")[:200],
        "status": str(match.get("status") or "")[:40],
        "genres": [str(g)[:40] for g in (match.get("genres") or [])[:8]],
        "rating": rating.get("value") if isinstance(rating.get("value"), (int, float)) else None,
        "images": [k for k in IMAGE_KINDS if k in kinds],
        "overview": str(match.get("overview") or "")[:2500],
        "wikipedia": wiki,
        "links": external[:6],
    }


@router.get("/artist/{artist_id}/image/{kind}")
def artist_image(artist_id: int, kind: str):
    if kind not in IMAGE_KINDS or artist_id <= 0:
        raise HTTPException(404, "Unknown image")
    setting = _settings()
    if not setting:
        raise HTTPException(404, "Lidarr is not connected")
    ext = "png" if kind == "clearlogo" else "jpg"
    data, ctype = _lidarr_get(setting, f"mediacover/artist/{artist_id}/{kind}.{ext}",
                              limit=15 * 1024 * 1024, raw=True)
    if not ctype.startswith(("image/jpeg", "image/png")):
        raise HTTPException(404, "No artwork")
    return Response(content=data, media_type=ctype.split(";")[0],
                    headers={"Cache-Control": "private, max-age=86400",
                             "X-Content-Type-Options": "nosniff"})
