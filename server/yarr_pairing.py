"""Opt-in Yarr account pairing. No media access or remote networking is enabled."""
import json
import os
import secrets
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request

from .connections import get_server_id

router = APIRouter(prefix="/api/yarr/pair")
FILE = Path(os.environ.get("YARR_PAIRING_PATH", "/data/yarr-account-pairing.json"))
ACCOUNT_URL = "https://yarr.larki-brian.workers.dev"
LOCK = threading.RLock()
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _read():
    try:
        obj = json.loads(FILE.read_text())
        if isinstance(obj, dict):
            return obj
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        raise HTTPException(500, "Saved Yarr pairing state cannot be read")
    return {}


def _save(data):
    FILE.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".yarr-pair-", dir=str(FILE.parent))
    try:
        with os.fdopen(fd, "w") as output:
            json.dump(data, output)
            output.write("\n")
        os.chmod(tmp, 0o600)
        os.replace(tmp, FILE)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _same_origin(request):
    # Reject cross-origin forms and fetches. Reverse proxies preserve Host.
    origin = request.headers.get("origin", "")
    site = request.headers.get("sec-fetch-site", "")
    host = request.headers.get("host", "").lower()
    try:
        parsed = urlsplit(origin)
        origin_host = parsed.netloc.lower()
    except ValueError:
        raise HTTPException(403, "Same-origin request required")
    if not origin or not host or origin_host != host or site == "cross-site":
        raise HTTPException(403, "Same-origin request required")


def _cloud(path, *, data=None, secret=None):
    headers = {"Accept": "application/json", "User-Agent": "YarrServerPairing/1"}
    if secret:
        headers["Authorization"] = "Bearer " + secret
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        ACCOUNT_URL + path,
        data=json.dumps(data).encode("utf-8") if data is not None else None,
        headers=headers,
        method="POST" if data is not None else "GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            return json.loads(response.read(4096))
    except urllib.error.HTTPError as e:
        if e.code == 409:
            raise HTTPException(409, "Server is already paired. Contact support to relink.")
        if e.code == 429:
            raise HTTPException(429, "Too many pairing requests. Try again later.")
        raise HTTPException(502, "Yarr pairing service rejected the request")
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        raise HTTPException(503, "Yarr account service is currently unreachable")


@router.post("/start")
def start_pairing(request: Request):
    _same_origin(request)
    with LOCK:
        previous = _read()
        if previous.get("status") == "paired" and previous.get("poll_secret"):
            raise HTTPException(409, "Server is already linked and its connection credential is active")
        code = "".join(secrets.choice(ALPHABET) for _ in range(16))
        secret = secrets.token_urlsafe(32)
        _cloud("/api/pairing/start", data={
            "server_id": get_server_id(), "code": code, "secret": secret
        })
        now = int(time.time())
        _save({"server_id": get_server_id(), "code": code,
               "poll_secret": secret, "status": "pending", "created_at": now,
               "expires_at": now + 600})
        return {"status": "pending",
                "code": "-".join(code[i:i + 4] for i in range(0, 16, 4)),
                "claim_url": ACCOUNT_URL + "/account", "expires_in": 600}


@router.get("/status")
def pairing_status():
    with LOCK:
        current = _read()
        if not current:
            return {"status": "not_started"}
        if current.get("status") == "paired":
            return {"status": "paired", "connection_ready": bool(current.get("poll_secret")),
                    "last_heartbeat": current.get("last_heartbeat") }
        if int(current.get("expires_at") or 0) <= time.time():
            _save({"server_id": get_server_id(), "status": "expired"})
            return {"status": "expired"}
        poll_secret = current.get("poll_secret", "")
        if not poll_secret:
            return {"status": "expired"}
        cloud = _cloud("/api/pairing/status", secret=poll_secret)
        if cloud.get("status") == "paired" and cloud.get("server_id"):
            _save({"server_id": get_server_id(), "status": "paired",
                   "account_server_id": cloud["server_id"],
                   "poll_secret": poll_secret,
                   "paired_at": int(time.time())})
            return {"status": "paired"}
        return {"status": "pending", "expires_in": max(0, int(current["expires_at"] - time.time()))}


def report_heartbeat():
    """Send only a signed-in server presence signal; never send media or LAN details."""
    with LOCK:
        record = _read()
        if record.get("status") != "paired" or not record.get("poll_secret"):
            return False
        secret = record["poll_secret"]
    _cloud("/api/connection/heartbeat", data={}, secret=secret)
    with LOCK:
        current = _read()
        if current.get("status") == "paired" and current.get("poll_secret") == secret:
            current["last_heartbeat"] = int(time.time())
            _save(current)
    return True


def heartbeat_loop(stop):
    # Each instance is optional: unpaired servers perform no cloud network requests.
    while not stop.is_set():
        try:
            report_heartbeat()
        except Exception:
            # Loss of connectivity must never affect local media playback.
            pass
        stop.wait(60)
