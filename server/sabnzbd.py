"""Local-only SABnzbd connection and limited queue monitoring/control."""
import ipaddress
import json
import os
import re
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from threading import RLock

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/sabnzbd")
LOCK = RLock()
CONFIG = Path(os.environ.get("SABNZBD_SETTINGS_PATH", "/data/sabnzbd-settings.json"))

class ConnectionRequest(BaseModel):
    url: str = Field(min_length=10, max_length=200)
    api_key: str = Field(min_length=12, max_length=256)

class QueueAction(BaseModel):
    action: str

def normalize_url(value: str) -> str:
    try:
        parsed = urllib.parse.urlsplit(value.strip())
        host = (parsed.hostname or "").lower()
        port = parsed.port or 8080
        if parsed.scheme != "http" or parsed.username or parsed.password or not (1 <= port <= 65535):
            raise ValueError
        if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
            raise ValueError
        # Never proxy requests to public sites or arbitrary hostnames.
        if host not in ("localhost", "host.docker.internal", "sabnzbd"):
            addr = ipaddress.ip_address(host)
            if not isinstance(addr, ipaddress.IPv4Address) or not (addr.is_private or addr.is_loopback):
                raise ValueError
            if addr.is_link_local or addr.is_multicast or addr.is_unspecified or addr.is_reserved:
                raise ValueError
        return "http://" + host + ":" + str(port)
    except (ValueError, TypeError) as error:
        raise HTTPException(422, "Enter SABnzbd's local HTTP address, such as http://192.168.1.20:8080") from error

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect)

def request(url: str, api_key: str, mode: str, **params):
    if mode not in ("queue", "history", "pause", "resume"):
        raise HTTPException(422, "Unsupported SABnzbd operation")
    args = {"mode": mode, "output": "json", "apikey": api_key, **params}
    query = urllib.parse.urlencode(args)
    req = urllib.request.Request(url + "/api?" + query, headers={
        "Accept": "application/json", "User-Agent": "OneEyedWillie/1.0",
    })
    try:
        with OPENER.open(req, timeout=10) as response:
            result = json.loads(response.read(2_000_000))
    except urllib.error.HTTPError as error:
        if error.code in (401, 403):
            raise HTTPException(401, "SABnzbd rejected the API key or access from this server.") from None
        raise HTTPException(502, "SABnzbd returned HTTP " + str(error.code) + ". Check its address and API settings.") from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise HTTPException(502, "Yarr Media could not reach SABnzbd on your network.") from None
    except (ValueError, TypeError):
        raise HTTPException(502, "SABnzbd returned an unreadable response.") from None
    if not isinstance(result, dict):
        raise HTTPException(502, "Unexpected SABnzbd response.")
    if result.get("error"):
        message = str(result["error"]).lower()
        if "api key" in message or "apikey" in message or "not authorized" in message:
            raise HTTPException(401, "SABnzbd rejected the API key. Use the full API key from Config → General, not the NZB key.")
        raise HTTPException(502, "SABnzbd returned an API error. Check its server and permissions.")
    return result

def saved():
    with LOCK:
        try:
            data = json.loads(CONFIG.read_text())
            return {"url": normalize_url(data["url"]), "api_key": str(data["api_key"])}
        except FileNotFoundError:
            raise HTTPException(409, "Connect SABnzbd under Settings → Connections first.")
        except (ValueError, OSError, TypeError, KeyError) as error:
            raise HTTPException(500, "Saved SABnzbd configuration could not be read.") from error

@router.get("/settings")
def get_settings():
    try:
        setting = saved()
    except HTTPException as error:
        if error.status_code == 409:
            return {"connected": False, "address": ""}
        raise
    return {"connected": True, "address": setting["url"]}

@router.put("/settings")
def save_settings(data: ConnectionRequest):
    url = normalize_url(data.url)
    api_key = data.api_key.strip()
    result = request(url, api_key, "queue", limit=1)
    if not isinstance(result.get("queue"), dict):
        raise HTTPException(502, "SABnzbd did not return a valid queue. Check the full API key.")
    with LOCK:
        CONFIG.parent.mkdir(parents=True, exist_ok=True)
        fd, temp = tempfile.mkstemp(prefix=".sabnzbd-", dir=CONFIG.parent)
        try:
            with os.fdopen(fd, "w") as stream:
                json.dump({"url": url, "api_key": api_key}, stream)
                stream.write("\n")
            os.chmod(temp, 0o600)
            os.replace(temp, CONFIG)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)
    return {"connected": True, "address": url}

@router.delete("/settings")
def disconnect():
    with LOCK:
        CONFIG.unlink(missing_ok=True)
    return {"connected": False}

def _clip(value, maximum=160):
    return str(value if value is not None else "")[:maximum]

def _queue_view(data):
    slots = data.get("slots", [])
    if not isinstance(slots, list):
        slots = []
    return {
        "paused": data.get("paused") is True or str(data.get("paused")).lower() == "true",
        "speed": _clip(data.get("speed")),
        "timeleft": _clip(data.get("timeleft")),
        "remaining": _clip(data.get("mb")),
        "total": _clip(data.get("noofslots")),
        "items": [
            {
                "name": _clip(row.get("filename") or row.get("name"), 180),
                "id": _clip(row.get("nzo_id") or "", 110),
                "status": _clip(row.get("status"), 60),
                "percent": _clip(row.get("percentage")),
                "timeleft": _clip(row.get("timeleft")),
                "sizeleft": _clip(row.get("mbleft")),
                "category": _clip(row.get("cat"), 80),
            } for row in slots[:30] if isinstance(row, dict)
        ],
    }

@router.get("/status")
def status():
    setting = saved()
    data = request(setting["url"], setting["api_key"], "queue", limit=30)
    if not isinstance(data.get("queue"), dict):
        raise HTTPException(502, "Invalid SABnzbd queue response.")
    history = request(setting["url"], setting["api_key"], "history", limit=12)
    body = history.get("history") or {}
    slots = body.get("slots", []) if isinstance(body, dict) else []
    return {
        "queue": _queue_view(data["queue"]),
        "history": [
            {"name": _clip(item.get("name") or item.get("filename"), 180),
             "status": _clip(item.get("status"), 60),
             "category": _clip(item.get("category"), 80)}
            for item in (slots if isinstance(slots, list) else [])[:12]
            if isinstance(item, dict)
        ]
    }

@router.post("/queue")
def control_queue(payload: QueueAction):
    if payload.action not in ("pause", "resume"):
        raise HTTPException(422, "Only pause and resume are supported.")
    setting = saved()
    # Explicitly limited to the whole-queue action; no job deletion or download submission.
    result = request(setting["url"], setting["api_key"], payload.action)
    if not result.get("status", False):
        raise HTTPException(502, "SABnzbd could not update the queue.")
    return {"ok": True, "action": payload.action}

class JobAction(BaseModel):
    action: str

@router.post("/jobs/{job_id}/action")
def control_job(job_id: str, payload: JobAction):
    if payload.action not in ("pause", "resume"):
        raise HTTPException(422, "Only pause and resume are supported.")
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,110}", job_id):
        raise HTTPException(422, "Invalid SABnzbd job identifier.")
    setting = saved()
    # SABnzbd's documented per-job operation is mode=queue&name=pause|resume.
    result = request(setting["url"], setting["api_key"], "queue",
                     name=payload.action, value=job_id)
    if not result.get("status", False):
        raise HTTPException(502, "SABnzbd could not update this download.")
    return {"ok": True, "action": payload.action}
