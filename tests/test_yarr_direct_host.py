"""Gated host-only WebRTC media bridge security and range-transfer tests."""
import json
import os
from unittest.mock import patch

import httpx
import pytest
from fastapi import HTTPException

from server import yarr_direct_peer as peer
from server import yarr_direct_gateway as gateway


class MemoryChannel:
    readyState = "open"
    bufferedAmount = 0

    def __init__(self):
        self.messages = []

    def send(self, value):
        self.messages.append(value)


def test_media_path_allowlist_rejects_ssrf_and_control_api():
    assert peer.normalize_path("/api/watch/42/stream?viewing=123").path == "/api/watch/42/stream"
    assert peer.normalize_path("/api/stream/hls/" + "a" * 32 + "/segment_000002.ts").path.endswith(".ts")
    for path in ("https://attacker.example/", "//evil.example/media", "/api/admin",
                 "/api/yarr/direct/offer", "/api/watch/42/../../etc/passwd",
                 "/api/watch/42/stream%2fsecret", "/api/watch/42/stream#x"):
        with pytest.raises(ValueError):
            peer.normalize_path(path)


def test_direct_transport_and_gateway_are_off_by_default():
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(HTTPException) as err:
            peer.authorized("secret")
        assert err.value.status_code == 404


@pytest.mark.asyncio
async def test_streams_real_http_206_bytes_through_media_channel():
    source = b"x" * 100000
    requests = []
    def respond(request):
        requests.append(request)
        assert request.url.host == "127.0.0.1"
        assert request.url.port == 8787
        assert request.url.path == "/api/watch/42/stream"
        assert request.url.query == b"viewing=123"
        assert request.headers["range"] == "bytes=200-100199"
        assert request.headers.get("x-untrusted-header") is None
        return httpx.Response(206, content=source, headers={
            "content-type": "video/mp4",
            "content-range": "bytes 200-100199/999999",
            "content-length": str(len(source)),
            "x-sensitive": "never-include"
        })
    transport = httpx.MockTransport(respond)
    constructor = httpx.AsyncClient
    def local_client(**kwargs):
        return constructor(transport=transport, **kwargs)
    channel = MemoryChannel()
    with patch.object(peer.httpx, "AsyncClient", side_effect=local_client):
        await peer.serve_asgi_media(
            channel, "/api/watch/42/stream?viewing=123",
            {"range": "bytes=200-100199", "x-untrusted-header": "secret"})
    first = json.loads(channel.messages[0])
    assert first["type"] == "headers" and first["status"] == 206
    assert first["headers"]["content-range"] == "bytes 200-100199/999999"
    assert "x-sensitive" not in first["headers"]
    assert b"".join(x for x in channel.messages if isinstance(x, bytes)) == source
    assert channel.messages[-1] == '{"type":"done"}'
    assert len(requests) == 1


@pytest.mark.asyncio
async def test_redirects_fail_closed_not_sent_to_remote_peer():
    constructor = httpx.AsyncClient
    def local_client(**kwargs):
        return constructor(
            transport=httpx.MockTransport(lambda _: httpx.Response(
                302, headers={"location": "https://attacker.example/media"})),
            **kwargs)
    with patch.object(peer.httpx, "AsyncClient", side_effect=local_client):
        with pytest.raises(RuntimeError, match="redirect"):
            await peer.serve_asgi_media(MemoryChannel(), "/api/watch/12/stream")


@pytest.mark.asyncio
async def test_gateway_refuses_unauthenticated_offer_and_disabled_mode():
    offer = gateway.PeerOffer(type="offer", sdp="dummy SDP")
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(HTTPException) as err:
            await gateway.offer(offer, x_yarr_direct_secret="abc")
        assert err.value.status_code == 404
    with (patch.dict(os.environ, {"YARR_DIRECT_PEER_ENABLED": "1"}),
          patch.object(gateway, "shared_secret", lambda: "known-secret")):
        with pytest.raises(HTTPException) as err:
            await gateway.offer(offer, x_yarr_direct_secret="incorrect")
        assert err.value.status_code == 403
