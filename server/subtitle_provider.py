"""OpenSubtitles search and controlled download into private subtitle cache.

Requires OPENSUBTITLES_API_KEY. Optional OPENSUBTITLES_TOKEN (bearer token).
No third-party URL is requested unless it belongs to OpenSubtitles.
"""
import hashlib
import json
import os
import re
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from .playback import _item
from .subtitles import CACHE, LOCK

router = APIRouter(prefix="/api/stream/subtitles")
BASE = "https://api.opensubtitles.com/api/v1"
LANGUAGE = re.compile(r"^[a-z]{2,3}(?:-[a-z]{2})?$")
MAX_DOWNLOAD = 8 * 1024 * 1024

SETTINGS_PATH = Path(os.environ.get("OPENSUBTITLES_CONFIG_PATH", "/data/opensubtitles-settings.json"))
SETTINGS_LOCK = threading.RLock()


class SettingsRequest(BaseModel):
    api_key: str = Field(min_length=8, max_length=300)
    token: str = Field(default="", max_length=1500)


def _saved_settings():
    try:
        data = json.loads(SETTINGS_PATH.read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _credentials():
    # UI-managed credentials override old environment configuration.
    with SETTINGS_LOCK:
        saved = _saved_settings()
    return (
        str(saved.get("api_key") or os.environ.get("OPENSUBTITLES_API_KEY", "")).strip(),
        str(saved.get("token") or os.environ.get("OPENSUBTITLES_TOKEN", "")).strip(),
    )


def _auth_headers(key, token=""):
    headers = {"Api-Key": key, "User-Agent": "YarrMedia v0.14.2",
               "Accept": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    return headers


@router.get("/settings")
def settings_status():
    key, token = _credentials()
    with SETTINGS_LOCK:
        saved = _saved_settings()
    return {"configured": bool(key), "token_configured": bool(token),
            "source": "settings" if saved.get("api_key") else
                      "environment" if key else "none"}


@router.put("/settings")
def save_settings(data: SettingsRequest):
    key, token = data.api_key.strip(), data.token.strip()
    if not key or any(ch.isspace() for ch in key):
        raise HTTPException(422, "Enter a valid OpenSubtitles API key")
    # Verify credentials before replacing an existing working connection.
    _json(BASE + "/subtitles?query=The+Matrix&languages=en",
          _auth_headers(key, token))
    with SETTINGS_LOCK:
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".opensubtitles-", dir=SETTINGS_PATH.parent)
        try:
            with os.fdopen(fd, "w") as stream:
                json.dump({"api_key": key, "token": token}, stream)
            os.chmod(temporary, 0o600)
            os.replace(temporary, SETTINGS_PATH)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    return settings_status()


@router.delete("/settings")
def remove_settings():
    with SETTINGS_LOCK:
        SETTINGS_PATH.unlink(missing_ok=True)
    return settings_status()



class DownloadRequest(BaseModel):
    file_id: int = Field(gt=0)


def _headers():
    key, token = _credentials()
    if not key:
        raise HTTPException(503, "OpenSubtitles API key is not configured. Add it in Settings → Connections.")
    return _auth_headers(key, token)


class _SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        parsed = urllib.parse.urlsplit(newurl)
        host = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or not (host == "opensubtitles.com" or host.endswith(".opensubtitles.com")):
            raise HTTPException(502, "Subtitle provider redirected to an unapproved download host")
        return super().redirect_request(request, fp, code, msg, headers, newurl)


def _read(url, headers, payload=None, max_bytes=512 * 1024):
    parsed = urllib.parse.urlsplit(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not (host == "opensubtitles.com" or host.endswith(".opensubtitles.com")):
        raise HTTPException(502, "Unapproved subtitle download host")
    req = urllib.request.Request(url, data=payload, headers=headers,
                                 method="POST" if payload is not None else "GET")
    try:
        with urllib.request.build_opener(_SafeRedirect()).open(req, timeout=12) as response:
            raw = response.read(max_bytes + 1)
            if len(raw) > max_bytes:
                raise HTTPException(413, "Subtitle provider response exceeds size limit")
            return raw
    except HTTPException:
        raise
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise HTTPException(502, "OpenSubtitles credentials were rejected") from exc
        if exc.code == 429:
            raise HTTPException(429, "OpenSubtitles download or search limit reached") from exc
        raise HTTPException(502, "OpenSubtitles returned an error") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise HTTPException(502, "OpenSubtitles is currently unreachable") from exc


def _json(url, headers, payload=None):
    try:
        return json.loads(_read(url, headers, payload))
    except (ValueError, UnicodeError) as exc:
        raise HTTPException(502, "Invalid OpenSubtitles response") from exc


def _media_title(media):
    row, video = _item(media)
    title = str(row.get("title") or video.stem)
    title = re.sub(r"[._]+", " ", title)
    title = re.sub(r"\b(1080p|2160p|720p|WEB[- ]DL|BluRay|x264|x265|HEVC)\b.*", "", title, flags=re.I)
    return title.strip()[:120] or video.stem[:120]


def _cache_prefix(media_id, video):
    return hashlib.sha256(f"{media_id}:{video.resolve()}".encode()).hexdigest()[:24]


def _cached(media_id, video):
    prefix = _cache_prefix(media_id, video)
    root = CACHE / "opensubtitles"
    if not root.is_dir():
        return []
    items = []
    for file in sorted(root.glob(prefix + "-*.srt")):
        if file.is_symlink() or not file.is_file() or file.stat().st_size > MAX_DOWNLOAD:
            continue
        match = re.fullmatch(re.escape(prefix) + r"-(\d+)-([a-z]{2,3}(?:-[a-z]{2})?)\.srt", file.name)
        if match:
            items.append({"id": "downloaded-" + match.group(1) + "-" + match.group(2),
                          "label": "Downloaded · " + match.group(2), "kind": "downloaded"})
    return items[:60]


@router.get("/{media_id}/search")
def search_subtitles(media_id: int, language: str = Query("en", max_length=6)):
    if not LANGUAGE.fullmatch(language):
        raise HTTPException(422, "Invalid subtitle language")
    headers = _headers()
    query = urllib.parse.urlencode({"query": _media_title(media_id), "languages": language})
    result = _json(BASE + "/subtitles?" + query, headers)
    found = []
    for entry in result.get("data", [])[:35]:
        attr = entry.get("attributes") or {}
        files = attr.get("files") or []
        if not files or not isinstance(files[0].get("file_id"), int):
            continue
        found.append({"file_id": files[0]["file_id"],
                      "release": str(attr.get("release") or attr.get("feature_details", {}).get("title") or "Subtitle")[:130],
                      "language": str(attr.get("language") or language)[:10],
                      "downloads": int(attr.get("download_count") or 0),
                      "hearing_impaired": bool(attr.get("hearing_impaired"))})
    return {"results": found}


@router.post("/{media_id}/download")
def download_subtitle(media_id: int, request: DownloadRequest, language: str = Query("en", max_length=6)):
    if not LANGUAGE.fullmatch(language):
        raise HTTPException(422, "Invalid subtitle language")
    _, video = _item(media_id)
    headers = _headers()
    prefix = _cache_prefix(media_id, video)
    directory = CACHE / "opensubtitles"
    destination = directory / f"{prefix}-{request.file_id}-{language}.srt"
    with LOCK:
        if destination.is_file() and not destination.is_symlink():
            return {"track_id": f"downloaded-{request.file_id}-{language}"}
        body = json.dumps({"file_id": request.file_id, "sub_format": "srt"}).encode()
        link = _json(BASE + "/download", {**headers, "Content-Type": "application/json"}, body).get("link")
        if not isinstance(link, str):
            raise HTTPException(502, "OpenSubtitles did not return a download link")
        raw = _read(link, {"User-Agent": "YarrMedia v0.14.2"}, max_bytes=MAX_DOWNLOAD)
        if not raw or b"\x00" in raw[:1024] or raw[:2] == b"PK":
            raise HTTPException(422, "Unsupported subtitle download format")
        directory.mkdir(parents=True, exist_ok=True)
        fd, path = tempfile.mkstemp(prefix=".download-", suffix=".srt", dir=directory)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(raw)
            os.chmod(path, 0o600)
            os.replace(path, destination)
        finally:
            if os.path.exists(path):
                os.unlink(path)
    return {"track_id": f"downloaded-{request.file_id}-{language}"}
