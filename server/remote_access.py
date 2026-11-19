"""Remote access gate: requests that arrive from outside the home need a Yarr pass.

A pass is a short-lived token signed by the Yarr account service (Ed25519):
"account X, who owns server Y, may use it until T". The server checks it on its
own with the published public key, so remote playback never has to travel
through Cloudflare and no per-request call home is needed.

Which requests count as remote:
  * the reverse proxy that faces the internet sets ``X-Yarr-Remote: 1``
    (deploy/Caddyfile.remote does), or
  * the Host header is one of ``YARR_REMOTE_HOSTS`` (comma separated).
Everything else (the LAN, the TV app at home, the account Worker's private
tunnel) behaves exactly as before.

Browser flow: yarr.media/remote/open issues a pass and sends the browser to
``https://<server>/remote/start?pass=...&return=/path``. That sets an HttpOnly
cookie for the remaining life of the pass and redirects to ``return``. When the
cookie expires, page loads bounce through yarr.media again for a fresh pass.
Apps send ``Authorization: Yarr-Pass <pass>`` instead.
"""
import asyncio
import base64
import re
import json
import os
import threading
import time
import urllib.request
from pathlib import Path
from urllib.parse import parse_qs, quote, urlencode

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from fastapi import APIRouter, HTTPException

from .connections import get_server_id

ACCOUNT_SITE = os.environ.get("YARR_ACCOUNT_SITE", "https://yarr.media").rstrip("/")
ACCOUNTS_SITE = os.environ.get("YARR_ACCOUNTS_SITE", "https://accounts.yarr.media").rstrip("/")
KEYS_PATH = Path(os.environ.get("YARR_PASS_KEYS_PATH", "/data/yarr-pass-keys.json"))
COOKIE = "yarr_pass"
CLOCK_SKEW = 60
MAX_LIFETIME = 13 * 60 * 60  # browser passes last 12 hours
KEY_REFRESH_SECONDS = 6 * 60 * 60
KEY_RETRY_SECONDS = 60
OPEN_PATHS = {"/remote/start", "/health"}
# The yarr.media app runs in the browser at these origins and talks to this
# server directly (see the service worker in cloudflare/yarr/worker.js).
APP_ORIGINS = {o.strip().rstrip("/") for o in os.environ.get("YARR_APP_ORIGINS", "https://app.yarr.media").split(",") if o.strip()}
CORS_ALLOW_HEADERS = "authorization, content-type, range, if-range, if-none-match, if-modified-since, accept, accept-language, x-requested-with"
CORS_EXPOSE_HEADERS = "content-length, content-range, accept-ranges, etag, last-modified, content-disposition, location"


def _cors_headers(origin):
    return [("access-control-allow-origin", origin), ("vary", "Origin"),
            ("access-control-expose-headers", CORS_EXPOSE_HEADERS)]


class PassError(Exception):
    """The pass is missing, malformed, expired or not for this server."""


def _b64(part):
    return base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))


class KeyStore:
    """Public keys from yarr.media, cached on disk; refetched for unknown key ids."""

    def __init__(self, path=KEYS_PATH, url=ACCOUNT_SITE + "/api/passes/keys", fetch=None):
        self.path = Path(path)
        self.url = url
        self._fetch = fetch or self._download
        self._lock = threading.Lock()
        # One download at a time. A caller that needs a key while another
        # download is running waits for it instead of giving up.
        self._fetch_lock = threading.Lock()
        self._keys = {}
        self._loaded_at = 0.0
        self._last_attempt = 0.0
        self._load_disk()

    def _download(self):
        request = urllib.request.Request(self.url, headers={"Accept": "application/json",
                                                            "User-Agent": "YarrServerPasses/1"})
        with urllib.request.urlopen(request, timeout=8) as response:
            return json.loads(response.read(65536))

    @staticmethod
    def _parse(document):
        keys = {}
        for jwk in (document or {}).get("keys", []):
            try:
                if jwk.get("kty") == "OKP" and jwk.get("crv") == "Ed25519" and jwk.get("kid"):
                    raw = _b64(jwk["x"])
                    if len(raw) == 32:
                        keys[str(jwk["kid"])] = Ed25519PublicKey.from_public_bytes(raw)
            except (ValueError, TypeError, KeyError):
                continue
        return keys

    def _load_disk(self):
        try:
            document = json.loads(self.path.read_text())
            self._keys = self._parse(document)
            self._loaded_at = float(document.get("fetched_at", 0))
        except (OSError, ValueError):
            pass

    def refresh(self):
        with self._fetch_lock:
            return self._refresh_locked()

    def _refresh_locked(self):
        with self._lock:
            if time.time() - self._last_attempt < KEY_RETRY_SECONDS:
                return False
            self._last_attempt = time.time()
        try:
            document = self._fetch()
        except Exception:
            return False
        keys = self._parse(document)
        with self._lock:
            self._keys = keys
            self._loaded_at = time.time()
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"keys": document.get("keys", []), "fetched_at": self._loaded_at}))
            os.replace(tmp, self.path)
        except OSError:
            pass
        return True

    def get(self, kid):
        stale = time.time() - self._loaded_at > KEY_REFRESH_SECONDS
        key = self._keys.get(kid)
        if key is None or stale:
            self.refresh()
            key = self._keys.get(kid, key)
        return key


KEYS = KeyStore()


def verify_pass(token, *, keys=None, server_id=None, now=None):
    """Return the pass claims, or raise PassError."""
    keys = keys or KEYS
    if not isinstance(token, str) or len(token) > 2048 or token.count(".") != 2:
        raise PassError("malformed")
    head, body, sig = token.split(".")
    try:
        header = json.loads(_b64(head))
        claims = json.loads(_b64(body))
        signature = _b64(sig)
    except (ValueError, TypeError):
        raise PassError("malformed")
    if not isinstance(header, dict) or not isinstance(claims, dict):
        raise PassError("malformed")
    if header.get("alg") != "EdDSA" or header.get("typ") != "yarr-pass":
        raise PassError("wrong_type")
    key = keys.get(str(header.get("kid", "")))
    if key is None:
        raise PassError("unknown_key")
    try:
        key.verify(signature, (head + "." + body).encode("ascii"))
    except InvalidSignature:
        raise PassError("bad_signature")
    now = time.time() if now is None else now
    exp, iat = claims.get("exp"), claims.get("iat")
    if not isinstance(exp, (int, float)) or not isinstance(iat, (int, float)):
        raise PassError("malformed")
    if exp <= now:
        raise PassError("expired")
    if iat > now + CLOCK_SKEW or exp - iat > MAX_LIFETIME:
        raise PassError("bad_lifetime")
    if claims.get("v") != 1 or claims.get("iss") != ACCOUNT_SITE:
        raise PassError("wrong_issuer")
    if claims.get("aud") != (server_id or get_server_id()):
        raise PassError("wrong_server")
    if claims.get("role") != "owner":  # shared access will add roles here
        raise PassError("not_allowed")
    return claims


def _remote_hosts():
    return {h.strip().lower() for h in os.environ.get("YARR_REMOTE_HOSTS", "").split(",") if h.strip()}


def _safe_return(value):
    value = value or "/"
    if not value.startswith("/") or value.startswith("//") or "\\" in value or len(value) > 500:
        return "/"
    return value


async def _send(send, status, headers, body=b"", origin=None):
    if origin:
        headers = list(headers) + _cors_headers(origin)
    await send({"type": "http.response.start", "status": status,
                "headers": [(k.encode("latin-1"), v.encode("latin-1")) for k, v in headers]})
    await send({"type": "http.response.body", "body": body})


class RemotePassMiddleware:
    """Pure ASGI so streamed video responses pass through untouched."""

    def __init__(self, app, keys=None, server_id=None):
        self.app = app
        self.keys = keys
        self.server_id = server_id

    def _is_remote(self, headers):
        if headers.get("x-yarr-remote") == "1":
            return True
        host = headers.get("host", "").split(":")[0].lower()
        return bool(host) and host in _remote_hosts()

    def _server(self):
        if not self.server_id:
            self.server_id = get_server_id()
        return self.server_id

    async def _verify(self, token):
        keys = self.keys or KEYS
        if isinstance(keys, KeyStore) and time.time() - keys._loaded_at > KEY_REFRESH_SECONDS:
            # Periodic refresh in the background; requests keep using cached keys.
            asyncio.get_running_loop().run_in_executor(None, keys.refresh)
        try:
            return verify_pass(token, keys=_NonBlocking(keys), server_id=self._server())
        except PassError as error:
            if str(error) != "unknown_key":
                raise
        # Unknown key id: fetch the current keys off the event loop, then retry once.
        await asyncio.to_thread(keys.refresh)
        return verify_pass(token, keys=_NonBlocking(keys), server_id=self._server())

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        if not self._is_remote(headers):
            return await self.app(scope, receive, send)
        path = scope.get("path", "")
        query = parse_qs(scope.get("query_string", b"").decode("latin-1"))
        origin = headers.get("origin", "").rstrip("/")
        origin = origin if origin in APP_ORIGINS else None
        if origin and scope.get("method") == "OPTIONS":
            # CORS preflight carries no credentials; answer it without a pass.
            return await _send(send, 204, [
                ("access-control-allow-methods", "GET, HEAD, POST, PUT, PATCH, DELETE"),
                ("access-control-allow-headers", CORS_ALLOW_HEADERS),
                ("access-control-max-age", "7200"), ("cache-control", "no-store")], origin=origin)
        if path == "/remote/start":
            return await self._start(query, send)
        if path in OPEN_PATHS:
            return await self.app(scope, receive, self._with_cors(send, origin))
        token = None
        auth = headers.get("authorization", "")
        if auth.startswith("Yarr-Pass "):
            token = auth[len("Yarr-Pass "):].strip()
        else:
            for part in headers.get("cookie", "").split(";"):
                name, _, value = part.strip().partition("=")
                if name == COOKIE:
                    token = value
        try:
            if not token:
                raise PassError("missing")
            claims = await self._verify(token)
        except PassError as error:
            return await self._refuse(scope, headers, str(error), send, origin)
        scope = dict(scope)
        scope["yarr_pass"] = claims
        return await self.app(scope, receive, self._with_cors(send, origin))

    @staticmethod
    def _with_cors(send, origin):
        if not origin:
            return send

        async def wrapped(message):
            if message["type"] == "http.response.start":
                message = dict(message)
                kept = [(k, v) for k, v in message.get("headers", [])
                        if k.lower() not in (b"access-control-allow-origin", b"access-control-expose-headers")]
                message["headers"] = kept + [(k.encode("latin-1"), v.encode("latin-1")) for k, v in _cors_headers(origin)]
            await send(message)
        return wrapped

    async def _start(self, query, send):
        token = (query.get("pass") or [""])[0]
        back = _safe_return((query.get("return") or ["/"])[0])
        try:
            claims = await self._verify(token)
        except PassError as error:
            return await _send(send, 403, [("content-type", "text/plain; charset=utf-8"),
                                           ("cache-control", "no-store")],
                               ("Remote access was refused (" + str(error) + "). Open your server from yarr.media again.").encode())
        age = max(1, int(claims["exp"] - time.time()))
        cookie = f"{COOKIE}={token}; Path=/; Max-Age={age}; Secure; HttpOnly; SameSite=Lax"
        return await _send(send, 303, [("location", back), ("set-cookie", cookie),
                                       ("cache-control", "no-store"), ("referrer-policy", "no-referrer")])

    async def _refuse(self, scope, headers, reason, send, origin=None):
        wants_page = not origin and scope.get("method") == "GET" and "text/html" in headers.get("accept", "")
        if wants_page:
            back = scope.get("path", "/") + ("?" + scope["query_string"].decode("latin-1") if scope.get("query_string") else "")
            server = self._server()
            target = ACCOUNTS_SITE + "/remote/open?" + urlencode({"server": server, "return": _safe_return(back)}, quote_via=quote)
            return await _send(send, 303, [("location", target), ("cache-control", "no-store")])
        return await _send(send, 401, [("content-type", "application/json"), ("cache-control", "no-store"),
                                       ("www-authenticate", "Yarr-Pass")],
                           json.dumps({"error": "remote_pass_required", "reason": reason}).encode(), origin=origin)


class _NonBlocking:
    """Key lookups inside the event loop never hit the network."""

    def __init__(self, store):
        self.store = store

    def get(self, kid):
        return self.store._keys.get(kid) if isinstance(self.store, KeyStore) else self.store.get(kid)


# Caddy's on-demand TLS asks here before getting a certificate for a hostname
# (deploy/Caddyfile.installer). Only this server's own IP-based address is
# approved, so nobody can make it request certificates for other names.
tls_router = APIRouter()
SSLIP = re.compile(r"^(\d{1,3})-(\d{1,3})-(\d{1,3})-(\d{1,3})\.sslip\.io$")


@tls_router.get("/api/remote/tls-check")
def tls_check(domain: str = ""):
    from .yarr_pairing import public_ip
    match = SSLIP.match(domain.strip().lower())
    ip = public_ip()
    if not match or not ip or ".".join(match.groups()) != ip:
        raise HTTPException(404, "Not this server's address")
    return {"ok": True}
