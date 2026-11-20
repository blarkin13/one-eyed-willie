"""Scoped Radarr/Sonarr/Lidarr dashboard API. Credentials never leave this server."""
import json
import urllib.error
import urllib.parse
import urllib.request

from fastapi import APIRouter, HTTPException, Path
from pydantic import BaseModel, Field

from . import arr
from . import lidarr as lidarr_settings

router = APIRouter(prefix="/api/managers")

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect)
MAX_BYTES = 8 * 1024 * 1024

KINDS = {"radarr": "movie", "sonarr": "series", "lidarr": "artist"}
ID_KEYS = {"radarr": "movieId", "sonarr": "seriesId", "lidarr": "artistId"}

def _kind(name):
    return KINDS[name]

def _provider(name):
    if name not in KINDS:
        raise HTTPException(404, "Unknown media manager")
    setting = lidarr_settings._settings() if name == "lidarr" else arr._settings(name)
    if not setting:
        raise HTTPException(409, "Connect " + name.title() + " in Settings → Connections.")
    return setting

def _request(name, settings, resource, method="GET", payload=None, query=None):
    """Only internal fixed API routes and methods are accepted."""
    read_only = {
        "movie", "series", "queue", "history", "qualityprofile", "command",
        "calendar", "wanted/missing", "wanted/cutoff", "blocklist",
        "system/status", "health", "diskspace", "release", "episode",
        "episodefile", "indexer", "downloadclient", "rootfolder", "tag",
        "artist", "album",
    }
    parts = resource.split("/")
    indexed = len(parts) == 2 and parts[0] in (
        "movie", "series", "episode", "queue", "artist", "album"
    ) and parts[1].isdigit() and int(parts[1]) > 0
    read_allowed = resource in read_only or indexed or (name == "sonarr" and resource == "episode/monitor")
    if not read_allowed:
        raise ValueError("Resource not permitted")
    foreign = {
        "radarr": ("series", "episode", "episodefile", "artist", "album"),
        "sonarr": ("movie", "artist", "album"),
        "lidarr": ("movie", "series", "episode", "episodefile"),
    }
    if parts[0] in foreign[name]:
        raise ValueError("Resource not permitted")
    if method == "GET":
        if resource == "episode/monitor" or (indexed and parts[0] == "queue"):
            raise ValueError("Method not permitted")
    elif method == "PUT":
        if resource == "episode/monitor" and name == "sonarr":
            pass
        elif not indexed or parts[0] not in ("movie", "series", "episode", "artist"):
            raise ValueError("Method not permitted")
    elif method == "POST":
        if resource not in ("command", "release"):
            raise ValueError("Method not permitted")
    elif method == "DELETE":
        if not indexed or parts[0] not in ("movie", "series", "artist", "queue"):
            raise ValueError("Method not permitted")
    else:
        raise ValueError("Method not permitted")
    api_version = "v1" if name == "lidarr" else arr._version(name, settings)
    url = settings["url"] + "/api/" + api_version + "/" + resource
    if query:
        url += "?" + urllib.parse.urlencode(query)
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"X-Api-Key": settings["api_key"], "Accept": "application/json",
               "User-Agent": "OneEyedWillie/1.0"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with OPENER.open(request, timeout=12) as response:
            data = response.read(MAX_BYTES + 1)
            if len(data) > MAX_BYTES:
                raise HTTPException(502, "Media manager response exceeded the size limit.")
            return json.loads(data) if data else {}
    except urllib.error.HTTPError as error:
        if error.code in (401, 403):
            raise HTTPException(401, name.title() + " rejected its API key.") from None
        if error.code in (400, 422):
            raise HTTPException(422, name.title() + " rejected this change. Check its configuration.") from None
        if error.code == 404:
            raise HTTPException(404, "That title was not found in " + name.title() + ".") from None
        raise HTTPException(502, name.title() + " returned HTTP " + str(error.code) + ".") from None
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, TypeError):
        raise HTTPException(502, name.title() + " is unreachable or returned an invalid response.") from None

def _positive_int(value):
    try:
        n = int(value)
        return n if n > 0 else None
    except (TypeError, ValueError):
        return None

def _text(value, length=180):
    return str(value or "")[:length]

def _items(name, raw, profiles):
    rows = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        ident = _positive_int(item.get("id"))
        if ident is None:
            continue
        profile = _positive_int(item.get("qualityProfileId"))
        stats = item.get("statistics") if isinstance(item.get("statistics"), dict) else {}
        if name == "radarr":
            has_file = bool(item.get("hasFile"))
            subtitle = str(item.get("year") or "")
            missing = not has_file
        elif name == "lidarr":
            files = int(stats.get("trackFileCount") or 0)
            total = int(stats.get("totalTrackCount") or stats.get("trackCount") or 0)
            albums = int(stats.get("albumCount") or 0)
            has_file = files > 0
            missing = total > files
            subtitle = (str(albums) + " album" + ("" if albums == 1 else "s") + " · " +
                        str(files) + " / " + str(total) + " tracks")
        else:
            files = int(stats.get("episodeFileCount") or 0)
            total = int(stats.get("episodeCount") or 0)
            has_file = files > 0
            missing = total > files
            subtitle = str(files) + " / " + str(total) + " episodes"
        rows.append({
            "id": ident,
            "title": _text(item.get("title") or item.get("artistName")),
            "year": item.get("year"),
            "monitored": bool(item.get("monitored")),
            "profile_id": profile,
            "profile": profiles.get(profile, "Profile " + str(profile) if profile else "Unknown"),
            "has_file": has_file,
            "missing": missing,
            "subtitle": subtitle,
            "status": _text(item.get("status"), 65),
        })
    return sorted(rows, key=lambda x: x["title"].casefold())

def _events(raw, name):
    records = raw.get("records") if isinstance(raw, dict) else raw
    if not isinstance(records, list):
        return []
    results = []
    for item in records[:40]:
        if not isinstance(item, dict):
            continue
        series = item.get("series") or item.get("movie") or item.get("artist") or {}
        if not isinstance(series, dict):
            series = {}
        title = _text(item.get("title") or item.get("sourceTitle") or series.get("title") or
                      series.get("artistName") or "Download")
        results.append({
            "title": title,
            "status": _text(item.get("status") or item.get("eventType"), 65),
            "tracked": _text(item.get("trackedDownloadStatus"), 60),
            "size": item.get("size"),
            "sizeleft": item.get("sizeleft"),
            "timeleft": _text(item.get("timeleft"), 60),
            "date": _text(item.get("date"), 40),
            "message": _text(item.get("statusMessages", [{}])[0].get("title") if
                             isinstance(item.get("statusMessages"), list) and
                             item.get("statusMessages") and
                             isinstance(item["statusMessages"][0], dict) else "", 160),
        })
    return results

@router.get("/{name}/dashboard")
def dashboard(name: str):
    setting = _provider(name)
    kind = _kind(name)
    records = _request(name, setting, kind)
    if not isinstance(records, list):
        raise HTTPException(502, name.title() + " returned an invalid library.")
    quality = _request(name, setting, "qualityprofile")
    if not isinstance(quality, list):
        quality = []
    profiles = {_positive_int(p.get("id")): _text(p.get("name"), 90)
                for p in quality if isinstance(p, dict) and _positive_int(p.get("id"))}
    titles = _items(name, records, profiles)
    # Queue/history may be unavailable on older servers; keep library controls available.
    messages = []
    try:
        queue_data = _request(name, setting, "queue", query={
            "page": 1, "pageSize": 40, "sortKey": "timeleft", "sortDirection": "ascending",
            "includeUnknownMovieItems": "true", "includeUnknownSeriesItems": "true",
            "includeUnknownArtistItems": "true",
        })
        queue = _events(queue_data, name)
    except HTTPException:
        queue = []
        messages.append("Queue could not be read.")
    try:
        history_data = _request(name, setting, "history", query={
            "page": 1, "pageSize": 20, "sortKey": "date", "sortDirection": "descending",
        })
        history = _events(history_data, name)
    except HTTPException:
        history = []
        messages.append("History could not be read.")
    return {
        "provider": name, "address": setting["url"],
        "total": len(titles),
        "monitored": sum(1 for x in titles if x["monitored"]),
        "missing": sum(1 for x in titles if x["missing"]),
        "profiles": [{"id": key, "name": value} for key, value in profiles.items()],
        "items": titles,
        "queue": queue, "history": history,
        "warnings": messages,
    }

class ItemChange(BaseModel):
    monitored: bool | None = None
    quality_profile_id: int | None = Field(default=None, gt=0)

@router.put("/{name}/items/{item_id}")
def update_item(name: str, item_id: int = Path(gt=0), change: ItemChange = None):
    setting = _provider(name)
    if change is None or (change.monitored is None and change.quality_profile_id is None):
        raise HTTPException(422, "Choose a monitoring or quality profile change.")
    resource = _kind(name) + "/" + str(item_id)
    record = _request(name, setting, resource)
    if not isinstance(record, dict) or _positive_int(record.get("id")) != item_id:
        raise HTTPException(404, "Title not found.")
    if change.quality_profile_id is not None:
        options = _request(name, setting, "qualityprofile")
        if not isinstance(options, list) or not any(
            isinstance(p, dict) and _positive_int(p.get("id")) == change.quality_profile_id
            for p in options
        ):
            raise HTTPException(422, "That quality profile is not configured in " + name.title() + ".")
        record["qualityProfileId"] = change.quality_profile_id
    if change.monitored is not None:
        record["monitored"] = change.monitored
    updated = _request(name, setting, resource, method="PUT", payload=record)
    # Some manager versions return an empty 202; read back before confirming success.
    if not isinstance(updated, dict) or _positive_int(updated.get("id")) != item_id:
        updated = _request(name, setting, resource)
    if not isinstance(updated, dict) or _positive_int(updated.get("id")) != item_id:
        raise HTTPException(502, name.title() + " did not confirm the change.")
    return {"ok": True, "id": item_id, "monitored": bool(updated.get("monitored")),
            "quality_profile_id": _positive_int(updated.get("qualityProfileId"))}

class CommandInput(BaseModel):
    action: str
    item_id: int | None = Field(default=None, gt=0)

@router.post("/{name}/command")
def run_command(name: str, change: CommandInput):
    setting = _provider(name)
    if change.action == "rss":
        payload = {"name": "RssSync"}
    elif change.action in ("search", "refresh") and change.item_id:
        resource = _kind(name) + "/" + str(change.item_id)
        existing = _request(name, setting, resource)
        if not isinstance(existing, dict) or _positive_int(existing.get("id")) != change.item_id:
            raise HTTPException(404, "Title not found.")
        search, refresh_cmd = {
            "radarr": ({"name": "MoviesSearch", "movieIds": [change.item_id]},
                       {"name": "RefreshMovie", "movieId": change.item_id}),
            "sonarr": ({"name": "SeriesSearch", "seriesId": change.item_id},
                       {"name": "RefreshSeries", "seriesId": change.item_id}),
            "lidarr": ({"name": "ArtistSearch", "artistId": change.item_id},
                       {"name": "RefreshArtist", "artistId": change.item_id}),
        }[name]
        payload = search if change.action == "search" else refresh_cmd
    else:
        raise HTTPException(422, "Unsupported command or missing title.")
    result = _request(name, setting, "command", method="POST", payload=payload)
    if not isinstance(result, dict):
        raise HTTPException(502, name.title() + " did not confirm the requested command.")
    return {"queued": True, "name": _text(result.get("name") or payload["name"], 90),
            "command_id": _positive_int(result.get("id"))}
