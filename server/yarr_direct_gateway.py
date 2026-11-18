"""Authenticated signaling-only bridge from Yarr to host-network media peer.

No media passes through this endpoint or Cloudflare. Feature disabled by
default; only the single installed paired-server key can request a media peer.
"""
import asyncio
import hmac
import os

import httpx
from fastapi import APIRouter, Header, HTTPException

from .yarr_direct_peer import PeerOffer, shared_secret

router = APIRouter(prefix="/api/yarr/direct", tags=["yarr-direct-pilot"])
HOST_OFFER = "http://host.docker.internal:18799/api/yarr/direct/offer"


@router.post("/offer")
async def offer(data: PeerOffer, x_yarr_direct_secret: str | None = Header(default=None)):
    if (os.environ.get("YARR_DIRECT_PEER_ENABLED") != "1"
            and os.environ.get("YARR_DIRECT_TEST_ENABLED") != "1"):
        raise HTTPException(404, "Direct media disabled")
    expected = shared_secret()
    if not expected:
        raise HTTPException(503, "Paired connection unavailable")
    if not x_yarr_direct_secret or not hmac.compare_digest(
            expected, x_yarr_direct_secret):
        raise HTTPException(403, "Not authorized")

    try:
        async with httpx.AsyncClient(timeout=40.0, follow_redirects=False,
                                     trust_env=False) as client:
            result = await client.post(
                HOST_OFFER, json=data.model_dump(),
                headers={"X-Yarr-Direct-Secret": x_yarr_direct_secret})
            if result.status_code != 200:
                raise HTTPException(503, "Direct host peer unavailable")
            answer = result.json()
            if (not isinstance(answer, dict) or answer.get("type") != "answer"
                    or not isinstance(answer.get("sdp"), str)
                    or len(answer["sdp"]) > 65536):
                raise ValueError("Invalid peer answer")
            return {"type": "answer", "sdp": answer["sdp"]}
    except (httpx.HTTPError, ValueError):
        raise HTTPException(503, "Direct host peer unavailable")
