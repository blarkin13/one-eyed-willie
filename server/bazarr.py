"""Private Bazarr (subtitle manager) connection and scoped dashboard API.

The API key stays on this server. The browser can only reach the fixed,
read-mostly routes below; it never supplies a Bazarr URL or path.
"""
import ipaddress
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

router = APIRouter(prefix="/api/bazarr", tags=["bazarr"])
SETTINGS_FILE = Path(os.environ.get("BAZARR_CONFIG_PATH", "/data/bazarr-settings.json"))
LOCK = RLock()
MAX_BYTES = 4 * 1024 * 1024
PAGE = 50
# Bazarr scheduler jobs the dashboard may start.
TASKS = {
    "search_movies": "wanted_search_missing_subtitles_movies",
    "search_episodes": "wanted_search_missing_subtitles_series",
    "sync": None,  # expands to update_series + update_movies
    "upgrade": "upgrade_subtitles",
}


class BazarrInput(BaseModel):
    url: str = Field(min_length=12, max_length=180)
    api_key: str = Field(min_length=12, max_length=128)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())


def _base_url(raw):
    """Allow only explicit private LAN IPs or trusted Docker service hostnames."""
    try:
        parsed = urllib.parse.urlsplit(raw.strip())
        host = (parsed.hostname or "").lower()
        if parsed.scheme not in ("http", "https") or not host or not parsed.port:
            raise ValueError
        if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ("", "/"):
            raise ValueError
        if host not in ("bazarr", "host.docker.internal"):
            address = ipaddress.ip_address(host)
            if not isinstance(address, ipaddress.IPv4Address) or not address.is_private:
                raise ValueError
            if address.is_loopback or address.is_link_local or address.is_multicast or \
                    address.is_reserved or address.is_unspecified:
                raise ValueError
        return f"{parsed.scheme}://{host}:{parsed.port}"
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, "Use Bazarr's private LAN address, such as http://192.168.86.29:6767") from exc


def _settings():
    url = os.environ.get("BAZARR_URL", "")
    key = os.environ.get("BAZARR_API_KEY", "")
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


def _call(setting, path, method="GET", query=None):
    url = setting["url"] + "/api/" + path
    if query:
        url += "?" + urllib.parse.urlencode(query, doseq=True)
    request = urllib.request.Request(url, method=method, data=b"" if method != "GET" else None,
        headers={"X-API-KEY": setting["api_key"], "Accept": "application/json", "User-Agent": "Yarr/1"})
    try:
        with OPENER.open(request, timeout=12) as response:
            data = response.read(MAX_BYTES + 1)
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise HTTPException(401, "Bazarr rejected its API key.") from None
        if exc.code == 404:
            raise HTTPException(404, "Not found in Bazarr.") from None
        raise HTTPException(502, "Bazarr returned HTTP " + str(exc.code) + ".") from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise HTTPException(502, "Bazarr is unreachable.") from exc
    if len(data) > MAX_BYTES:
        raise HTTPException(502, "Bazarr response exceeded the size limit.")
    try:
        return json.loads(data) if data.strip() else {}
    except ValueError:
        raise HTTPException(502, "Bazarr returned an invalid response.") from None


def _require():
    setting = _settings()
    if not setting:
        raise HTTPException(409, "Connect Bazarr in Settings → Integrations.")
    return setting


def _text(value, length=200):
    return str(value or "")[:length]


def _int(value):
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None


def _languages(items):
    out = []
    for lang in items or []:
        if isinstance(lang, dict):
            name = _text(lang.get("name"), 40)
            if lang.get("forced"):
                name += " (forced)"
            elif lang.get("hi"):
                name += " (HI)"
            out.append(name)
    return out


# ---------------------------------------------------------------- connection

@router.get("/connection")
def connection_status():
    setting = _settings()
    return {"connected": bool(setting), "address": setting["url"] if setting else None,
            "managed": setting["managed"] if setting else None}


@router.put("/connection")
def connect(payload: BazarrInput):
    setting = {"url": _base_url(payload.url), "api_key": payload.api_key.strip()}
    status = _call(setting, "system/status")
    if not isinstance(status, dict) or not isinstance(status.get("data"), dict) or \
            not status["data"].get("bazarr_version"):
        raise HTTPException(502, "That address did not answer like Bazarr.")
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOCK:
        fd, filename = tempfile.mkstemp(prefix=".bazarr-", dir=SETTINGS_FILE.parent)
        try:
            with os.fdopen(fd, "w") as handle:
                json.dump(setting, handle)
            os.chmod(filename, 0o600)
            os.replace(filename, SETTINGS_FILE)
        finally:
            if os.path.exists(filename):
                os.unlink(filename)
    return {"connected": True, "provider": "bazarr"}


@router.delete("/connection")
def disconnect():
    if os.environ.get("BAZARR_URL") and os.environ.get("BAZARR_API_KEY"):
        raise HTTPException(409, "Bazarr is configured in the server environment")
    with LOCK:
        SETTINGS_FILE.unlink(missing_ok=True)
    return {"connected": False}


# ---------------------------------------------------------------- dashboard

@router.get("/dashboard")
def dashboard():
    setting = _require()
    status = _call(setting, "system/status").get("data") or {}
    badges = _call(setting, "badges")
    warnings = []
    try:
        health = [_text(h.get("issue") or h.get("message") or h, 250)
                  for h in _call(setting, "system/health").get("data") or [] if h]
    except HTTPException:
        health = []
        warnings.append("Health could not be read.")
    try:
        providers = [{"name": _text(p.get("name"), 60), "status": _text(p.get("status"), 120),
                      "retry": _text(p.get("retry"), 60)}
                     for p in _call(setting, "providers").get("data") or [] if isinstance(p, dict)]
    except HTTPException:
        providers = []
        warnings.append("Providers could not be read.")
    return {
        "address": setting["url"],
        "version": _text(status.get("bazarr_version"), 40),
        "sonarr_version": _text(status.get("sonarr_version"), 40),
        "radarr_version": _text(status.get("radarr_version"), 40),
        "missing_movies": badges.get("movies") if isinstance(badges.get("movies"), int) else 0,
        "missing_episodes": badges.get("episodes") if isinstance(badges.get("episodes"), int) else 0,
        "provider_issues": badges.get("providers") if isinstance(badges.get("providers"), int) else 0,
        "sonarr_live": badges.get("sonarr_signalr") == "LIVE",
        "radarr_live": badges.get("radarr_signalr") == "LIVE",
        "health": health,
        "providers": providers,
        "warnings": warnings,
    }


@router.get("/wanted/{kind}")
def wanted(kind: str, page: int = Query(1, ge=1, le=200)):
    setting = _require()
    if kind == "movies":
        raw = _call(setting, "movies/wanted", query={"start": (page - 1) * PAGE, "length": PAGE})
        items = [{"id": _int(m.get("radarrId")), "title": _text(m.get("title")),
                  "subtitle": "", "release": _text(m.get("sceneName"), 200),
                  "missing": _languages(m.get("missing_subtitles"))}
                 for m in raw.get("data") or [] if isinstance(m, dict)]
    elif kind == "episodes":
        raw = _call(setting, "episodes/wanted", query={"start": (page - 1) * PAGE, "length": PAGE})
        items = [{"id": _int(e.get("sonarrSeriesId")), "episode_id": _int(e.get("sonarrEpisodeId")),
                  "title": _text(e.get("seriesTitle")),
                  "subtitle": (_text(e.get("episode_number"), 20) + " · " + _text(e.get("episodeTitle"))).strip(" ·"),
                  "release": _text(e.get("sceneName"), 200),
                  "missing": _languages(e.get("missing_subtitles"))}
                 for e in raw.get("data") or [] if isinstance(e, dict)]
    else:
        raise HTTPException(404, "Unknown list")
    total = raw.get("total") if isinstance(raw.get("total"), int) else len(items)
    return {"items": items, "total": total, "page": page, "has_more": page * PAGE < total}


@router.get("/history/{kind}")
def history(kind: str, page: int = Query(1, ge=1, le=200)):
    setting = _require()
    if kind not in ("movies", "episodes"):
        raise HTTPException(404, "Unknown list")
    raw = _call(setting, kind + "/history", query={"start": (page - 1) * PAGE, "length": PAGE})
    items = []
    for h in raw.get("data") or []:
        if not isinstance(h, dict):
            continue
        language = h.get("language") if isinstance(h.get("language"), dict) else {}
        title = h.get("seriesTitle") if kind == "episodes" else h.get("title")
        sub = (_text(h.get("episode_number"), 20) + " · " + _text(h.get("episodeTitle"))).strip(" ·") \
            if kind == "episodes" else ""
        items.append({"title": _text(title), "subtitle": sub,
                      "action": _text(h.get("description") or h.get("action"), 200),
                      "language": _text(language.get("name"), 40),
                      "provider": _text(h.get("provider"), 60),
                      "score": _text(h.get("score"), 20),
                      "date": _text(h.get("parsed_timestamp") or h.get("timestamp"), 40)})
    total = raw.get("total") if isinstance(raw.get("total"), int) else len(items)
    return {"items": items, "total": total, "page": page, "has_more": page * PAGE < total}


class SearchInput(BaseModel):
    kind: str
    id: int = Field(gt=0)


@router.post("/search")
def search(item: SearchInput):
    """Ask Bazarr to search missing subtitles for one movie or one series."""
    setting = _require()
    if item.kind == "movie":
        _call(setting, "movies", method="PATCH", query={"radarrid": item.id, "action": "search-missing"})
    elif item.kind == "series":
        _call(setting, "series", method="PATCH", query={"seriesid": item.id, "action": "search-missing"})
    else:
        raise HTTPException(422, "Choose a movie or a series.")
    return {"queued": True}


class TaskInput(BaseModel):
    task: str


@router.post("/task")
def run_task(item: TaskInput):
    setting = _require()
    if item.task not in TASKS:
        raise HTTPException(422, "Unknown task.")
    for job in (["update_series", "update_movies"] if item.task == "sync" else [TASKS[item.task]]):
        _call(setting, "system/tasks", method="POST", query={"taskid": job})
    return {"queued": True}
