"""Isolated WebRTC data-channel transport experiment for Yarr issue #184.

Not part of the production FastAPI app. No media files can be read.
Run explicitly with YARR_DIRECT_PROBE_TOKEN and an optional aiortc install.
"""
import asyncio
import hmac
import json
import os
from pathlib import Path
import secrets
import time

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

try:
    from aiortc import RTCPeerConnection, RTCSessionDescription
except ImportError:  # Keep normal production requirements unchanged.
    RTCPeerConnection = RTCSessionDescription = None

app = FastAPI(title="One-Eyed Willie direct peer transport probe")
PEERS = set()
MAX_BYTES = 1024 * 1024
CHUNK_BYTES = 16 * 1024
HIGH_WATER = 128 * 1024
SESSION_LIMIT = 4
STARTED = {}
TEST_PAGE = Path(__file__).with_name("direct_peer_probe.html")


class Offer(BaseModel):
    sdp: str = Field(min_length=1, max_length=32768)
    type: str = Field(pattern="^offer$")


def authorize(value: str | None):
    configured = os.environ.get("YARR_DIRECT_PROBE_TOKEN", "")
    # Disabled without an explicit, high-entropy secret.
    if len(configured) < 32 or not value:
        raise HTTPException(404, "Probe disabled")
    if not hmac.compare_digest(value, configured):
        raise HTTPException(403, "Invalid probe token")


@app.get("/probe")
async def page():
    if len(os.environ.get("YARR_DIRECT_PROBE_TOKEN", "")) < 32:
        raise HTTPException(404, "Probe disabled")
    return FileResponse(TEST_PAGE, media_type="text/html",
                        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


def deterministic_bytes(start: int, length: int):
    """Known bytes for integrity checking; never reads a real media file."""
    return bytes(i % 251 for i in range(start, start + length))


async def send_sample(channel, start: int, length: int):
    channel.send(json.dumps({"type": "start", "offset": start, "length": length}))
    for pos in range(start, start + length, CHUNK_BYTES):
        while channel.readyState == "open" and channel.bufferedAmount > HIGH_WATER:
            await asyncio.sleep(0.008)
        if channel.readyState != "open":
            return
        channel.send(deterministic_bytes(pos, min(CHUNK_BYTES, start + length - pos)))
    if channel.readyState == "open":
        channel.send(json.dumps({"type": "done", "length": length}))


@app.post("/offer")
async def offer(payload: Offer, x_probe_token: str | None = Header(default=None)):
    authorize(x_probe_token)
    if RTCPeerConnection is None:
        raise HTTPException(503, "Install optional aiortc dependencies")
    if len(PEERS) >= SESSION_LIMIT:
        raise HTTPException(429, "Too many probe connections")
    pc = RTCPeerConnection()
    PEERS.add(pc)
    STARTED[pc] = time.monotonic()

    @pc.on("connectionstatechange")
    async def connection_state_change():
        if pc.connectionState in ("failed", "closed", "disconnected"):
            await pc.close()
            PEERS.discard(pc)
            STARTED.pop(pc, None)

    @pc.on("datachannel")
    def datachannel(channel):
        if channel.label != "yarr-direct-probe-v1":
            channel.close()
            return

        @channel.on("message")
        def message(data):
            try:
                if not isinstance(data, str):
                    raise ValueError("Text control frame required")
                request = json.loads(data)
                if request.get("type") != "read":
                    raise ValueError("Unexpected request")
                start, length = request.get("offset"), request.get("length")
                if (type(start) is not int or type(length) is not int
                        or start < 0 or start > 4 * MAX_BYTES
                        or length < 1 or length > MAX_BYTES):
                    raise ValueError("Invalid range")
                # One bounded probe per peer; no arbitrary file paths or URLs.
                if getattr(pc, "_yarr_probe_started", False):
                    raise ValueError("Only one probe request allowed")
                pc._yarr_probe_started = True
                asyncio.create_task(send_sample(channel, start, length))
            except (ValueError, json.JSONDecodeError):
                if channel.readyState == "open":
                    channel.send(json.dumps({"type": "error", "message": "Invalid request"}))

    try:
        await pc.setRemoteDescription(RTCSessionDescription(sdp=payload.sdp, type="offer"))
        await pc.setLocalDescription(await pc.createAnswer())
        return {"type": pc.localDescription.type, "sdp": pc.localDescription.sdp,
                "session": secrets.token_hex(8)}
    except Exception:
        await pc.close()
        PEERS.discard(pc)
        STARTED.pop(pc, None)
        raise HTTPException(400, "WebRTC negotiation failed")


@app.on_event("shutdown")
async def shutdown():
    await asyncio.gather(*(pc.close() for pc in tuple(PEERS)), return_exceptions=True)
    PEERS.clear()
    STARTED.clear()
