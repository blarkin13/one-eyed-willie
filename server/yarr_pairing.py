"""Opt-in Yarr account pairing. No media access or remote networking is enabled."""
import json
import os
import secrets
import subprocess
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

# This is an opt-in connector: nothing runs before Google-account pairing succeeds.
TUNNEL_BIN = os.environ.get("YARR_CLOUDFLARED_BIN", "/usr/local/bin/cloudflared")
TUNNEL_TOKEN_FILE = Path(os.environ.get("YARR_TUNNEL_TOKEN_PATH", "/data/yarr-automatic-tunnel-token"))
TUNNEL_STATE_LOCK = threading.RLock()
_tunnel_process = None
_tunnel_message = "Not started"


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
        if e.code in (401, 403):
            raise HTTPException(401, "Paired server credential is no longer authorized")
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
                    "last_heartbeat": current.get("last_heartbeat"),
                    "private_connector": tunnel_state()}
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
            return {"status": "paired", "connection_ready": True,
                    "last_heartbeat": current.get("last_heartbeat"),
                    "private_connector": tunnel_state()}
        code = current.get("code", "")
        grouped_code = "-".join(code[i:i + 4] for i in range(0, len(code), 4)) if len(code) == 16 else None
        return {"status": "pending",
                "code": grouped_code,
                "claim_url": ACCOUNT_URL + "/account",
                "expires_in": max(0, int(current["expires_at"] - time.time()))}


def report_heartbeat():
    """Send only a signed-in server presence signal; never send media or LAN details."""
    with LOCK:
        record = _read()
        if record.get("status") != "paired" or not record.get("poll_secret"):
            return False
        secret = record["poll_secret"]
    reply = _cloud("/api/connection/heartbeat", data={}, secret=secret)
    with LOCK:
        current = _read()
        if current.get("status") == "paired" and current.get("poll_secret") == secret:
            current["last_heartbeat"] = int(time.time())
            # yarr.media reports the public IP this server checked in from; the
            # HTTPS front door uses it to know which address it may serve.
            ip = reply.get("public_ip") if isinstance(reply, dict) else None
            if isinstance(ip, str) and len(ip) <= 15:
                current["public_ip"] = ip
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


def tunnel_state():
    """Safe-to-display local connector status; never expose credentials."""
    with TUNNEL_STATE_LOCK:
        active = _tunnel_process is not None and _tunnel_process.poll() is None
        return {"status": "running" if active else "offline",
                "detail": _tunnel_message}


def _store_tunnel_token(token):
    # Atomic, private, and never sent to browser or application logs.
    if not isinstance(token, str) or not (80 <= len(token) <= 4096):
        raise RuntimeError("Invalid automatic tunnel credential")
    TUNNEL_TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix=".yarr-tunnel-", dir=str(TUNNEL_TOKEN_FILE.parent))
    try:
        with os.fdopen(fd, "w") as output:
            output.write(token + "\n")
        os.chmod(temp_path, 0o600)
        os.replace(temp_path, TUNNEL_TOKEN_FILE)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def _stop_tunnel():
    global _tunnel_process
    with TUNNEL_STATE_LOCK:
        proc = _tunnel_process
        _tunnel_process = None
    if proc is not None and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=3)


def automatic_tunnel_loop(stop):
    """Fetch tunnel provisioning only with paired-server credentials and run QUIC.
    Never depends on Docker socket, router settings, or user-provided URLs.
    """
    global _tunnel_process, _tunnel_message
    while not stop.is_set():
        try:
            with LOCK:
                pairing = _read()
                secret = pairing.get("poll_secret") if pairing.get("status") == "paired" else None
            if not secret:
                _stop_tunnel()
                with TUNNEL_STATE_LOCK:
                    _tunnel_message = "Connect this server to Yarr to enable automatic tunneling"
                stop.wait(20)
                continue
            if not os.path.isfile(TUNNEL_BIN) or not os.access(TUNNEL_BIN, os.X_OK):
                with TUNNEL_STATE_LOCK:
                    _tunnel_message = "Cloudflare connector not installed; rebuild the server image"
                stop.wait(60)
                continue
            result = _cloud("/api/connection/tunnel/bootstrap",
                            data={"server_id": get_server_id()}, secret=secret)
            token = result.get("tunnel_token")
            if result.get("status") != "ready" or not token:
                raise RuntimeError("Tunnel provisioning is unavailable")
            # Maintain the credential on private disk so the token isn't exposed via argv.
            current = None
            try:
                current = TUNNEL_TOKEN_FILE.read_text().strip()
            except FileNotFoundError:
                pass
            if current != token:
                _store_tunnel_token(token)
                _stop_tunnel()  # New tunnel credentials require a new connector process.
            with TUNNEL_STATE_LOCK:
                alive = _tunnel_process is not None and _tunnel_process.poll() is None
                if not alive:
                    _tunnel_process = subprocess.Popen(
                        [TUNNEL_BIN, "tunnel", "--no-autoupdate", "--protocol", "quic",
                         "run", "--token-file", str(TUNNEL_TOKEN_FILE)],
                        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL, close_fds=True,
                    )
                _tunnel_message = "Automatic private connector started"
        except HTTPException as error:
            with TUNNEL_STATE_LOCK:
                _tunnel_message = "Yarr provisioning: " + str(error.detail)[:110]
            # On explicit unauthorized credentials, stop the old connector.
            if error.status_code in (401, 403):
                _stop_tunnel()
        except Exception:
            with TUNNEL_STATE_LOCK:
                _tunnel_message = "Automatic private connector setup failed; retrying"
        stop.wait(45)
    _stop_tunnel()


def public_ip():
    """Public IPv4 last reported by yarr.media for this paired server, or None."""
    with LOCK:
        record = _read()
    if record.get("status") != "paired":
        return None
    return record.get("public_ip")
