"""Yarr experimental direct data plane; disabled until a paired pilot has bootstrapped.

Control/signaling still uses the account Worker. After DTLS/ICE negotiation,
only allowlisted read-only media HTTP responses cross this RTCDataChannel.
No user-provided filesystem path or arbitrary reverse proxy is supported.
"""
import asyncio
import hashlib
import hmac
import json
import os
import re
import httpx
from urllib.parse import urlsplit

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from . import yarr_pairing

try:
    from aiortc import RTCConfiguration, RTCIceServer, RTCPeerConnection, RTCSessionDescription
except ImportError:
    RTCConfiguration = RTCIceServer = RTCPeerConnection = RTCSessionDescription = None

router = APIRouter(prefix="/api/yarr/direct")
ACTIVE = set()
MAX_PEERS = 1  # Dedicated UDP 3478; shared fixed socket cannot host concurrent sessions
MAX_CHANNELS = 8
CHUNK_BYTES = 16 * 1024
HIGH_WATER = 256 * 1024
PEER_LIFETIME = 60 * 60

# Only media responses use peer transport. JSON/control POSTs stay on the
# authenticated Yarr HTTPS origin; these media bytes bypass the Worker.
READ_ROUTES = (
    re.compile(r"^/api/watch/[1-9][0-9]*/stream$"),
    re.compile(r"^/api/watch/[1-9][0-9]*/transcode$"),
    re.compile(r"^/api/stream/hls/[a-f0-9]{32}/(?:index\.m3u8|init\.mp4|segment_[0-9]{6}\.(?:ts|m4s))$"),
    re.compile(r"^/api/stream/subtitles/[1-9][0-9]*/(?:external|embedded)-[0-9]{1,3}\.vtt$"),
    re.compile(r"^/api/maintenance/preview/[1-9][0-9]*/0(?:0[0-9]|1[0-9]|2[0-3])\.jpg$"),
)
HEADERS = {"content-type", "content-length", "content-range", "accept-ranges",
           "cache-control", "etag", "last-modified", "content-encoding",
           "x-content-type-options"}
REQUEST_HEADERS = {"range", "if-range", "if-none-match", "accept"}


class PeerOffer(BaseModel):
    type: str = Field(pattern=r"^offer$")
    sdp: str = Field(min_length=1, max_length=65536)


def shared_secret():
    """Domain-separated key from the already installed private pilot tunnel.

    Do not reuse the tunnel token itself as the peer authentication value.
    This is a single-server pilot; future deployments need per-server grants.
    """
    try:
        token = yarr_pairing.TUNNEL_TOKEN_FILE.read_text().strip()
        status = yarr_pairing._read()
    except (OSError, HTTPException):
        return None
    if len(token) < 40 or status.get("status") != "paired":
        return None
    return hashlib.sha256(("yarr-direct-offer-v1\x00" + token).encode()).hexdigest()


def authorized(credential):
    if (os.environ.get("YARR_DIRECT_PEER_ENABLED") != "1"
            or os.environ.get("YARR_ICE_PROBE_MODE") != "host"):
        raise HTTPException(404, "Direct peer mode disabled")
    expected = shared_secret()
    if not expected:
        raise HTTPException(503, "Private paired connection unavailable")
    if not credential or not hmac.compare_digest(expected, credential):
        raise HTTPException(403, "Not authorized")


def normalize_path(path):
    if not isinstance(path, str) or len(path) > 500 or any(x in path for x in ("\\", "#", "%", "\x00")):
        raise ValueError("Invalid path")
    parsed = urlsplit(path)
    if (parsed.scheme or parsed.netloc or parsed.fragment or
        not parsed.path.startswith("/") or parsed.path.startswith("//") or
        ".." in parsed.path or len(parsed.query) > 250):
        raise ValueError("Invalid path")
    if not any(p.fullmatch(parsed.path) for p in READ_ROUTES):
        raise ValueError("Not an authorized media route")
    return parsed


async def drain(channel):
    while channel.readyState == "open" and channel.bufferedAmount > HIGH_WATER:
        await asyncio.sleep(0.008)
    if channel.readyState != "open":
        raise ConnectionError("Peer channel closed")


async def serve_asgi_media(channel, path, req_headers=None):
    """Stream bounded chunks from the locally hosted primary media server.

    Runs only in the separate host-network sidecar. It never mounts media
    volumes or calls an arbitrary address: the only upstream is the existing
    Yarr server bound at loopback 127.0.0.1:8787. Strict media-path and
    request-header allowlists are applied before any upstream call.
    """
    parsed = normalize_path(path)
    req_headers = req_headers if isinstance(req_headers, dict) else {}
    headers = {}
    for key, value in req_headers.items():
        if (isinstance(key, str) and isinstance(value, str)
                and key.lower() in REQUEST_HEADERS and len(value) < 240):
            try:
                value.encode("latin-1")
            except UnicodeEncodeError:
                continue
            headers[key.lower()] = value

    async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=5.0),
                                 follow_redirects=False, trust_env=False) as client:
        url = "http://127.0.0.1:8787" + parsed.path
        if parsed.query:
            url += "?" + parsed.query
        async with client.stream("GET", url, headers=headers) as response:
            if response.status_code in (301, 302, 303, 307, 308):
                raise RuntimeError("Media redirects are not permitted")
            allowed = {k: v for k, v in response.headers.items()
                       if k.lower() in HEADERS}
            await drain(channel)
            channel.send(json.dumps({"type": "headers",
                                     "status": response.status_code,
                                     "headers": allowed}))
            async for body in response.aiter_raw(CHUNK_BYTES):
                await drain(channel)
                channel.send(body)
            await drain(channel)
            channel.send('{"type":"done"}')


@router.post("/offer")
async def offer(data: PeerOffer, x_yarr_direct_secret: str | None = Header(default=None)):
    authorized(x_yarr_direct_secret)
    if RTCPeerConnection is None:
        raise HTTPException(503, "WebRTC peer engine unavailable")
    if len(ACTIVE) >= MAX_PEERS:
        raise HTTPException(429, "Too many concurrent direct viewers")
    config = RTCConfiguration(iceServers=[RTCIceServer(urls="stun:stun.l.google.com:19302")])
    pc = RTCPeerConnection(configuration=config)
    ACTIVE.add(pc)
    opened = set()

    async def expire():
        try:
            await asyncio.sleep(PEER_LIFETIME)
            await pc.close()
        finally:
            ACTIVE.discard(pc)

    expiry = None

    @pc.on("connectionstatechange")
    async def changed():
        if pc.connectionState in ("failed", "closed", "disconnected"):
            await pc.close()
            ACTIVE.discard(pc)
            if expiry:
                expiry.cancel()

    @pc.on("datachannel")
    def on_channel(channel):
        if not channel.label.startswith("yarr-media-v1:") or len(opened) >= MAX_CHANNELS:
            channel.close()
            return
        opened.add(channel)
        requested = False

        @channel.on("close")
        def close():
            opened.discard(channel)

        @channel.on("message")
        def message(value):
            nonlocal requested
            if requested or not isinstance(value, str) or len(value) > 1400:
                channel.close()
                return
            requested = True
            try:
                item = json.loads(value)
                if item.get("type") != "get":
                    raise ValueError("Invalid command")
                normalize_path(item.get("path"))
            except (ValueError, TypeError):
                channel.send('{"type":"error","message":"Invalid media request"}')
                channel.close()
                return

            async def stream():
                try:
                    await serve_asgi_media(channel, item["path"], item.get("headers"))
                except Exception:
                    if channel.readyState == "open":
                        channel.send('{"type":"error","message":"Media request failed"}')
                finally:
                    # Allow queued SCTP chunks and the final DONE control frame
                    # to reach the browser before closing the channel.
                    deadline = asyncio.get_running_loop().time() + 5
                    while (channel.readyState == "open"
                           and channel.bufferedAmount > 0
                           and asyncio.get_running_loop().time() < deadline):
                        await asyncio.sleep(0.02)
                    if channel.readyState == "open":
                        await asyncio.sleep(0.05)
                        channel.close()
            asyncio.create_task(stream())

    try:
        await pc.setRemoteDescription(RTCSessionDescription(sdp=data.sdp, type="offer"))
        await pc.setLocalDescription(await pc.createAnswer())
        expiry = asyncio.create_task(expire())
        return {"type": pc.localDescription.type, "sdp": pc.localDescription.sdp}
    except Exception:
        await pc.close()
        ACTIVE.discard(pc)
        raise HTTPException(400, "Unable to establish peer transport")
