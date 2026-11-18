"""Temporary Yarr Wi-Fi-to-home ICE transport diagnostic.

No movie access: only generated deterministic test bytes travel over DTLS.
The only entrypoint is an account-verified request forwarded by Yarr Worker,
authenticated with a domain-separated derivative of the private tunnel token.
"""
import asyncio
import hashlib
import hmac
import json
import time

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from . import yarr_pairing

try:
    from aiortc import RTCConfiguration, RTCIceServer, RTCPeerConnection, RTCSessionDescription
except ImportError:
    RTCConfiguration = RTCIceServer = RTCPeerConnection = RTCSessionDescription = None

router = APIRouter(prefix="/api/yarr/ice-probe", tags=["yarr-diagnostics"])
PEERS = set()
MAX_PEERS = 2
SAMPLE_BYTES = 256 * 1024
FRAME_BYTES = 16 * 1024
HIGH_WATER = 128 * 1024
MAX_SESSION_SECONDS = 90
DOMAIN = "yarr-ice-diagnostic-v1"


class Offer(BaseModel):
    type: str = Field(pattern=r"^offer$")
    sdp: str = Field(min_length=1, max_length=32768)


def derived_key():
    try:
        pairing = yarr_pairing._read()
        if pairing.get("status") != "paired":
            return None
        token = yarr_pairing.TUNNEL_TOKEN_FILE.read_text().strip()
    except (OSError, HTTPException):
        return None
    if len(token) < 80:
        return None
    return hashlib.sha256((DOMAIN + chr(0) + token).encode()).hexdigest()


def authenticate(secret):
    expected = derived_key()
    if not expected:
        raise HTTPException(404, "Diagnostic not available")
    if not secret or not hmac.compare_digest(secret, expected):
        raise HTTPException(403, "Not authorized")


def sample(offset, length):
    return bytes(i % 251 for i in range(offset, offset + length))


async def deliver(channel):
    channel.send(json.dumps({"type": "start", "length": SAMPLE_BYTES}))
    for offset in range(0, SAMPLE_BYTES, FRAME_BYTES):
        while channel.readyState == "open" and channel.bufferedAmount > HIGH_WATER:
            await asyncio.sleep(0.01)
        if channel.readyState != "open":
            return
        channel.send(sample(offset, min(FRAME_BYTES, SAMPLE_BYTES - offset)))
    if channel.readyState == "open":
        channel.send(json.dumps({"type": "done", "length": SAMPLE_BYTES}))
        deadline = asyncio.get_running_loop().time() + 3
        while channel.readyState == "open" and channel.bufferedAmount and asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(0.02)


@router.post("/offer")
async def offer(body: Offer, x_yarr_ice_key: str | None = Header(default=None)):
    authenticate(x_yarr_ice_key)
    if RTCPeerConnection is None:
        raise HTTPException(503, "WebRTC engine not available")
    if len(PEERS) >= MAX_PEERS:
        raise HTTPException(429, "Diagnostic is busy")
    connection = RTCPeerConnection(configuration=RTCConfiguration(
        iceServers=[RTCIceServer(urls="stun:stun.l.google.com:19302")]))
    PEERS.add(connection)
    tasks = set()

    async def cleanup():
        await connection.close()
        PEERS.discard(connection)

    async def expire():
        await asyncio.sleep(MAX_SESSION_SECONDS)
        await cleanup()

    @connection.on("connectionstatechange")
    async def connection_changed():
        if connection.connectionState in ("failed", "disconnected", "closed"):
            await cleanup()

    @connection.on("datachannel")
    def channel_open(channel):
        if channel.label != "yarr-network-probe-v1":
            channel.close()
            return
        used = False

        @channel.on("message")
        def message(value):
            nonlocal used
            if used or value != "test":
                channel.close()
                return
            used = True
            async def serve():
                try:
                    await deliver(channel)
                finally:
                    if channel.readyState == "open":
                        channel.close()
            task = asyncio.create_task(serve())
            tasks.add(task)
            task.add_done_callback(tasks.discard)

    try:
        await connection.setRemoteDescription(RTCSessionDescription(sdp=body.sdp, type="offer"))
        await connection.setLocalDescription(await connection.createAnswer())
        task = asyncio.create_task(expire())
        task.add_done_callback(lambda _: tasks.discard(task))
        tasks.add(task)
        return {"type": connection.localDescription.type, "sdp": connection.localDescription.sdp}
    except Exception:
        await cleanup()
        raise HTTPException(400, "ICE negotiation failed")
