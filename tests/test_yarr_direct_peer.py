"""Security and HTTP byte-stream tests for experimental Yarr peer transport."""
import asyncio
import hashlib
import os
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from server import yarr_direct_peer as peer


class FakeChannel:
    readyState = "open"
    bufferedAmount = 0

    def __init__(self):
        self.messages = []

    def send(self, data):
        self.messages.append(data)


def test_allowed_media_paths_and_query_strings():
    assert peer.normalize_path("/api/watch/42/stream?viewing=123").query == "viewing=123"
    assert peer.normalize_path("/api/stream/hls/" + "a" * 32 + "/index.m3u8").path.endswith("index.m3u8")
    assert peer.normalize_path("/api/stream/hls/" + "a" * 32 + "/segment_000002.ts").path.endswith(".ts")


@pytest.mark.parametrize("path", [
    "https://example.org/api/watch/1/stream", "//evil.com/api/watch/1/stream",
    "/admin", "/api/yarr/direct/offer", "/api/watch/1/../../etc/passwd",
    "/api/watch/1/stream%2F..", "/api/watch/1/stream#fragment",
    "/api/stream/hls/not-a-session/index.m3u8", "/api/watch/1/stream\\x",
    "/api/watch/01/stream", 12, None, "/api/watch/1/stream?" + "x" * 400
])
def test_path_rejection(path):
    with pytest.raises(ValueError):
        peer.normalize_path(path)


def test_feature_disabled_by_default():
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(HTTPException) as error:
            peer.authorized("anything")
    assert error.value.status_code == 404


def test_derived_key_is_scoped_to_paired_tunnel():
    token = "temporary-pilot-token-" + "x" * 60
    sample = SimpleNamespace(read_text=lambda: token)
    with patch.object(peer.yarr_pairing, "TUNNEL_TOKEN_FILE", sample), \
         patch.object(peer.yarr_pairing, "_read", lambda: {"status": "paired"}), \
         patch.dict(os.environ, {"YARR_DIRECT_PEER_ENABLED": "1"}):
        expected = hashlib.sha256(("yarr-direct-offer-v1\\x00" + token).encode()).hexdigest()
        assert peer.shared_secret() == expected
        peer.authorized(expected)
        with pytest.raises(HTTPException) as error:
            peer.authorized(expected + "x")
        assert error.value.status_code == 403


@pytest.mark.asyncio
async def test_asgi_stream_keeps_range_headers_and_bytes():
    channel = FakeChannel()
    sent = b"v" * 40000
    async def fake_asgi(scope, receive, send):
        assert scope["path"] == "/api/watch/42/stream"
        assert scope["headers"] == [(b"range", b"bytes=100-40099")]
        await send({"type": "http.response.start", "status": 206,
                    "headers": [(b"content-type", b"video/mp4"),
                                (b"content-range", b"bytes 100-40099/100000"),
                                (b"x-private-secret", b"never-forward")]})
        await send({"type": "http.response.body", "body": sent[:10000], "more_body": True})
        await send({"type": "http.response.body", "body": sent[10000:], "more_body": False})
    with patch.dict(sys.modules, {"server.main": SimpleNamespace(app=fake_asgi)}):
        await peer.serve_asgi_media(channel, "/api/watch/42/stream", {"range": "bytes=100-40099"})
    import json
    start = json.loads(channel.messages[0])
    assert start["status"] == 206
    assert start["headers"]["content-range"] == "bytes 100-40099/100000"
    assert "x-private-secret" not in start["headers"]
    assert b"".join(m for m in channel.messages if isinstance(m, bytes)) == sent
    assert channel.messages[-1] == '{"type":"done"}'
