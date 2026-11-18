"""Yarr paired home/server WebRTC diagnostic: auth and local peer round trip."""
import asyncio
import hashlib
import os
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from server import yarr_ice_probe as probe


def test_authorization_rejects_unpaired_and_bad_keys():
    with patch.object(probe.yarr_pairing, "_read", lambda: {"status": "unpaired"}):
        assert probe.derived_key() is None
        with pytest.raises(HTTPException) as exc:
            probe.authenticate("wrong")
        assert exc.value.status_code == 404
    token = "test-nonproduction-tunnel-credential-" + "z" * 90
    with patch.object(probe.yarr_pairing, "_read", lambda: {"status": "paired"}), \
         patch.object(probe.yarr_pairing, "TUNNEL_TOKEN_FILE", SimpleNamespace(read_text=lambda: token)):
        key = hashlib.sha256((probe.DOMAIN + chr(0) + token).encode()).hexdigest()
        assert probe.derived_key() == key
        probe.authenticate(key)
        with pytest.raises(HTTPException) as exc:
            probe.authenticate(key + "wrong")
        assert exc.value.status_code == 403


def test_synthetic_data_is_deterministic_and_bounded():
    assert probe.sample(249, 4) == bytes([249, 250, 0, 1])
    assert len(probe.sample(1024, probe.FRAME_BYTES)) == probe.FRAME_BYTES


@pytest.mark.asyncio
async def test_real_local_dtls_channel_round_trip():
    """Connect a second Python WebRTC peer, request a 256-KiB test transfer."""
    from aiortc import RTCPeerConnection, RTCSessionDescription
    initiator = RTCPeerConnection()
    data_channel = initiator.createDataChannel("yarr-network-probe-v1")
    data_channel.binaryType = "binary"
    future = asyncio.get_running_loop().create_future()
    chunks = []
    starts = []

    @data_channel.on("open")
    def open_event():
        data_channel.send("test")

    @data_channel.on("message")
    def message(frame):
        if future.done():
            return
        if isinstance(frame, str):
            import json
            obj = json.loads(frame)
            if obj["type"] == "start":
                starts.append(obj["length"])
            if obj["type"] == "done":
                future.set_result(True)
        else:
            chunks.append(bytes(frame))

    try:
        await initiator.setLocalDescription(await initiator.createOffer())
        with patch.object(probe, "authenticate", lambda secret: None):
            answer = await probe.offer(probe.Offer(type="offer", sdp=initiator.localDescription.sdp),
                                       x_yarr_ice_key="test-only")
        await initiator.setRemoteDescription(
            RTCSessionDescription(sdp=answer["sdp"], type=answer["type"]))
        await asyncio.wait_for(future, timeout=35)
        assert starts == [probe.SAMPLE_BYTES]
        assert b"".join(chunks) == probe.sample(0, probe.SAMPLE_BYTES)
    finally:
        await initiator.close()
        for connection in tuple(probe.PEERS):
            await connection.close()
            probe.PEERS.discard(connection)
