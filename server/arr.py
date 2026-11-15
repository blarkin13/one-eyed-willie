"""Radarr / Sonarr connections and explicit media-library discovery.

The browser never receives API keys. Only private LAN endpoints and fixed *arr
API routes are used. Adding titles changes the connected *arr library, not files
in One-Eyed Willie's read-only media mount.
"""
import json
import os
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from threading import RLock

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from . import movies
from .artwork import register_remote
from .metadata import _simple
from .library import db
import time

router = APIRouter(prefix="/api/arr")
SONARR_FILE = Path(os.environ.get("SONARR_CONFIG_PATH", "/data/sonarr-settings.json"))
LOCK = RLock()
MAX_BYTES = 6 * 1024 * 1024
SUPPORTED = ("radarr", "sonarr")


class ConnectInput(BaseModel):
    url: str = Field(min_length=12, max_length=180)
    api_key: str = Field(min_length=12, max_length=128)


class AddInput(BaseModel):
    external_id: int = Field(gt=0)
    root_folder: str = Field(min_length=1, max_length=1024)
    quality_profile_id: int = Field(gt=0)
    search_now: bool = False


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def _provider(name):
    if name not in SUPPORTED:
        raise HTTPException(404, "Unsupported media manager")
    return name


def _base_url(url):
    return movies._base_url(url)


def _sonarr_settings():
    url, key = os.environ.get("SONARR_URL", ""), os.environ.get("SONARR_API_KEY", "")
    if url and key:
        try:
            return {"url": _base_url(url), "api_key": key, "managed": "environment",
                    "api_version": os.environ.get("SONARR_API_VERSION", "v3")}
        except HTTPException:
            return None
    try:
        obj = json.loads(SONARR_FILE.read_text())
        return {"url": _base_url(obj["url"]), "api_key": str(obj["api_key"]),
                "managed": "settings", "api_version": obj.get("api_version", "v3")}
    except (OSError, ValueError, KeyError, TypeError, HTTPException):
        return None


def _settings(name):
    name = _provider(name)
    return movies._settings() if name == "radarr" else _sonarr_settings()


def _version(name, settings):
    return "v3" if name == "radarr" else settings.get("api_version", "v3")


def _request(name, settings, resource, *, method="GET", query=None, payload=None):
    """Private, server-built endpoint requests only; caller cannot supply a URL."""
    _provider(name)
    if method not in ("GET", "POST"):
        raise ValueError("Unsupported method")
    api = _version(name, settings)
    allowed = {
        "movie", "series", "movie/lookup", "series/lookup",
        "rootfolder", "qualityprofile",
    }
    if resource not in allowed:
        raise ValueError("Unsupported API resource")
    path = "/api/" + api + "/" + resource
    url = settings["url"] + path
    if query:
        url += "?" + urllib.parse.urlencode(query)
    headers = {"X-Api-Key": settings["api_key"], "Accept": "application/json",
               "User-Agent": "OneEyedWillie/0.9"}
    body = None
    if method == "POST":
        headers["Content-Type"] = "application/json"
        body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    opener = urllib.request.build_opener(NoRedirect())
    try:
        with opener.open(req, timeout=9) as resp:
            data = resp.read(MAX_BYTES + 1)
            if len(data) > MAX_BYTES:
                raise HTTPException(502, "Media manager returned too much data")
            return json.loads(data) if data else {}
    except urllib.error.HTTPError as exc:
        # Never pass potentially sensitive upstream response bodies or headers.
        if exc.code in (401, 403):
            raise HTTPException(502, "Media manager rejected the API key") from exc
        if exc.code == 400:
            raise HTTPException(422, "The media manager rejected this request or its profile settings") from exc
        if exc.code == 409:
            raise HTTPException(409, "This title is already managed") from exc
        raise HTTPException(502, "Media manager request failed") from exc
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        raise HTTPException(502, "Media manager is unreachable or returned an invalid response") from exc


def _get(name, resource, query=None):
    settings = _settings(name)
    if not settings:
        raise HTTPException(409, "Connect " + name.title() + " in Settings → Connections")
    return _request(name, settings, resource, query=query)


def _save_sonarr(data):
    SONARR_FILE.parent.mkdir(parents=True, exist_ok=True)
    fd, path = tempfile.mkstemp(prefix=".sonarr-", dir=SONARR_FILE.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(data, stream)
        os.chmod(path, 0o600)
        os.replace(path, SONARR_FILE)
    finally:
        if os.path.exists(path):
            os.unlink(path)


@router.get("/connections")
def connection_status():
    result = {}
    for name in SUPPORTED:
        setting = _settings(name)
        result[name] = {"connected": bool(setting), "address": setting["url"] if setting else None,
                        "managed": setting.get("managed") if setting else None}
    return result


@router.put("/connections/{name}")
def connect(name: str, data: ConnectInput):
    _provider(name)
    url = _base_url(data.url)
    value = {"url": url, "api_key": data.api_key.strip()}
    if name == "radarr":
        # Keep the established Radarr connection and artwork-cache integration.
        movies.save_radarr_source(movies.RadarrSettingsInput(**value))
    else:
        api = None
        for version in ("v3", "v5"):
            try:
                _request(name, {**value, "api_version": version}, "series")
                api = version
                break
            except HTTPException:
                continue
        if api is None:
            raise HTTPException(422, "Could not connect to Sonarr. Check the LAN address and API key.")
        with LOCK:
            _save_sonarr({**value, "api_version": api})
    return {"connected": True, "provider": name}


@router.delete("/connections/{name}")
def disconnect(name: str):
    _provider(name)
    if name == "radarr":
        return movies.remove_radarr_source()
    if os.environ.get("SONARR_URL") and os.environ.get("SONARR_API_KEY"):
        raise HTTPException(409, "Sonarr is configured in the server environment")
    with LOCK:
        SONARR_FILE.unlink(missing_ok=True)
    return {"connected": False}


def _id(name, record):
    value = record.get("tmdbId" if name == "radarr" else "tvdbId")
    return value if isinstance(value, int) and value > 0 else None


def _normalized_results(name, records, library_ids):
    seen, result = set(), []
    for item in records[:40]:
        if not isinstance(item, dict):
            continue
        external_id = _id(name, item)
        if not external_id or external_id in seen:
            continue
        seen.add(external_id)
        images = item.get("images") or []
        art = next((x for x in images if
                    isinstance(x, dict) and x.get("coverType") in ("poster", "banner")), {})
        poster = register_remote(art.get("remoteUrl"))
        title = str(item.get("title") or "")[:180]
        if not title:
            continue
        result.append({
            "id": external_id, "title": title, "year": item.get("year"),
            "overview": str(item.get("overview") or "")[:900],
            "poster_url": poster, "provider": name,
            "already_added": external_id in library_ids,
        })
        if len(result) >= 20:
            break
    return result


@router.get("/{name}/lookup")
def lookup(name: str, q: str = Query(min_length=2, max_length=100)):
    _provider(name)
    q = q.strip()
    records = _get(name, "movie/lookup" if name == "radarr" else "series/lookup",
                   {"term": q})
    if not isinstance(records, list):
        raise HTTPException(502, "Unexpected lookup response")
    owned = _get(name, "movie" if name == "radarr" else "series")
    ids = {_id(name, x) for x in owned if isinstance(x, dict)} if isinstance(owned, list) else set()
    return {"provider": name, "items": _normalized_results(name, records, ids)}


@router.get("/{name}/options")
def options(name: str):
    _provider(name)
    folders = _get(name, "rootfolder")
    profiles = _get(name, "qualityprofile")
    if not isinstance(folders, list) or not isinstance(profiles, list):
        raise HTTPException(502, "Could not retrieve folders and profiles")
    return {
        "folders": [{"path": x["path"], "label": x.get("name") or x["path"]}
                    for x in folders if isinstance(x, dict) and isinstance(x.get("path"), str)],
        "profiles": [{"id": x["id"], "name": x.get("name") or "Profile"}
                     for x in profiles if isinstance(x, dict) and isinstance(x.get("id"), int)],
    }


@router.post("/{name}/add")
def add(name: str, selection: AddInput):
    """Add an explicitly confirmed lookup result; never start searching by default."""
    _provider(name)
    setting = _settings(name)
    if not setting:
        raise HTTPException(409, "Connect " + name.title() + " first")
    opts = options(name)
    paths = {x["path"] for x in opts["folders"]}
    profiles = {x["id"] for x in opts["profiles"]}
    if selection.root_folder not in paths or selection.quality_profile_id not in profiles:
        raise HTTPException(422, "Select an existing root folder and quality profile")
    owned = _get(name, "movie" if name == "radarr" else "series")
    if any(_id(name, item) == selection.external_id for item in owned if isinstance(item, dict)):
        raise HTTPException(409, "This title is already in your " + name.title() + " library")
    prefix = "tmdb:" if name == "radarr" else "tvdb:"
    matches = _get(name, "movie/lookup" if name == "radarr" else "series/lookup",
                   {"term": prefix + str(selection.external_id)})
    exact = next((item for item in matches if isinstance(item, dict) and
                  _id(name, item) == selection.external_id), None) if isinstance(matches, list) else None
    if not exact:
        raise HTTPException(404, "This title is no longer available in the lookup")
    # Build from server-fetched data, never browser-provided metadata or paths.
    payload = {
        "title": exact.get("title"),
        "rootFolderPath": selection.root_folder,
        "qualityProfileId": selection.quality_profile_id,
        "monitored": True,
    }
    if name == "radarr":
        payload.update({"tmdbId": selection.external_id,
                        "minimumAvailability": "released",
                        "addOptions": {"searchForMovie": selection.search_now}})
        endpoint = "movie"
    else:
        payload.update({
            "tvdbId": selection.external_id,
            "seasonFolder": True,
            "seriesType": exact.get("seriesType") if exact.get("seriesType") in
                          ("standard", "daily", "anime") else "standard",
            "seasons": exact.get("seasons") or [],
            "addOptions": {"searchForMissingEpisodes": selection.search_now,
                           "monitor": "all"},
        })
        endpoint = "series"
    result = _request(name, setting, endpoint, method="POST", payload=payload)
    return {
        "added": True, "provider": name, "title": result.get("title") or payload["title"],
        "id": result.get("id"), "search_requested": selection.search_now,
        "note": "Added to the media manager. Files appear in One-Eyed Willie only after they're obtained and indexed.",
    }



def sonarr_metadata(title, year=None):
    """Use Sonarr's existing series catalog as another source for TV information.

    This read is cached server-side for six hours; it does not contact Sonarr for
    every show tile. Returns no passwords, LAN paths or private API URLs.
    """
    setting = _sonarr_settings()
    if not setting:
        return {}
    with LOCK:
        with db() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS sonarr_snapshot (
                id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL,
                fetched_at INTEGER NOT NULL, source_url TEXT NOT NULL
            )""")
            row = conn.execute(
                "SELECT payload,fetched_at,source_url FROM sonarr_snapshot WHERE id=1"
            ).fetchone()
        cached = None
        if row and row["source_url"] == setting["url"]:
            try:
                cached = json.loads(row["payload"])
            except (ValueError, TypeError):
                pass
        if cached is not None and time.time() - row["fetched_at"] < 6 * 60 * 60:
            series = cached
        else:
            try:
                current = _request("sonarr", setting, "series")
                if not isinstance(current, list):
                    current = None
            except HTTPException:
                current = None
            if current is None:
                series = cached or []
            else:
                series = []
                for item in current:
                    if not isinstance(item, dict):
                        continue
                    image = next((im for im in item.get("images", [])
                                  if isinstance(im, dict) and im.get("coverType") == "poster"), {})
                    series.append({
                        "title": item.get("title") or "",
                        "year": item.get("year"),
                        "overview": item.get("overview") or "",
                        "tvdb_id": item.get("tvdbId"),
                        "poster_url": image.get("remoteUrl"),
                        "seasons": [
                            {"number": s.get("seasonNumber"), "name": "Season " +
                             str(s.get("seasonNumber")), "overview": ""}
                            for s in item.get("seasons", []) if isinstance(s, dict) and
                            isinstance(s.get("seasonNumber"), int)
                        ],
                    })
                with db() as conn:
                    conn.execute(
                        "INSERT INTO sonarr_snapshot(id,payload,fetched_at,source_url) "
                        "VALUES(1,?,?,?) ON CONFLICT(id) DO UPDATE SET "
                        "payload=excluded.payload,fetched_at=excluded.fetched_at,"
                        "source_url=excluded.source_url",
                        (json.dumps(series), int(time.time()), setting["url"]),
                    )
        key = _simple(title)
        matches = [s for s in series if _simple(s.get("title")) == key]
        if year:
            matches = [s for s in matches if not s.get("year") or
                       abs(int(s["year"]) - int(year)) <= 1]
        if len(matches) != 1:
            return {}
        found = matches[0]
        return {
            "title": found["title"], "overview": found["overview"],
            "poster_url": found.get("poster_url"),
            "seasons": found.get("seasons") or [],
            "source": "Sonarr",
        }
