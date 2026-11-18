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
