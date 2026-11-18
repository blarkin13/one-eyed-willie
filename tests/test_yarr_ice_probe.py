"""Yarr paired server diagnostic: stdlib auth and real WebRTC round trip tests."""
import asyncio
import hashlib
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException

from server import yarr_ice_probe as probe


class DiagnosticSecurityTests(unittest.TestCase):
    def test_authorization_rejects_unpaired_and_bad_keys(self):
        with patch.object(probe.yarr_pairing, "_read", lambda: {"status": "unpaired"}):
            self.assertIsNone(probe.derived_key())
            with self.assertRaises(HTTPException) as caught:
                probe.authenticate("wrong")
            self.assertEqual(caught.exception.status_code, 404)
        token = "test-nonproduction-tunnel-credential-" + "z" * 90
        with patch.object(probe.yarr_pairing, "_read", lambda: {"status": "paired"}), \
             patch.object(probe.yarr_pairing, "TUNNEL_TOKEN_FILE", SimpleNamespace(read_text=lambda: token)):
            key = hashlib.sha256((probe.DOMAIN + chr(0) + token).encode()).hexdigest()
            self.assertEqual(probe.derived_key(), key)
            probe.authenticate(key)
            with self.assertRaises(HTTPException) as caught:
                probe.authenticate(key + "wrong")
            self.assertEqual(caught.exception.status_code, 403)

    def test_synthetic_data_is_deterministic_and_bounded(self):
        self.assertEqual(probe.sample(249, 4), bytes([249, 250, 0, 1]))
        self.assertEqual(len(probe.sample(1024, probe.FRAME_BYTES)), probe.FRAME_BYTES)


class DiagnosticRoundTripTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_local_dtls_channel_round_trip(self):
        from aiortc import RTCPeerConnection, RTCSessionDescription
        initiator = RTCPeerConnection()
        channel = initiator.createDataChannel("yarr-network-probe-v1")
        future = asyncio.get_running_loop().create_future()
        chunks, announced = [], []

        @channel.on("open")
        def on_open():
            channel.send("test")

        @channel.on("message")
        def on_message(frame):
            if future.done():
                return
            if isinstance(frame, str):
                message = json.loads(frame)
                if message["type"] == "start":
                    announced.append(message["length"])
                if message["type"] == "done":
                    future.set_result(True)
            else:
                chunks.append(bytes(frame))

        try:
            await initiator.setLocalDescription(await initiator.createOffer())
            with patch.object(probe, "authenticate", lambda secret: None):
                answer = await probe.offer(
                    probe.Offer(type="offer", sdp=initiator.localDescription.sdp),
                    x_yarr_ice_key="unit-test",
                )
            await initiator.setRemoteDescription(
                RTCSessionDescription(sdp=answer["sdp"], type=answer["type"]))
            await asyncio.wait_for(future, timeout=35)
            self.assertEqual(announced, [probe.SAMPLE_BYTES])
            self.assertEqual(b"".join(chunks), probe.sample(0, probe.SAMPLE_BYTES))
        finally:
            await initiator.close()
            for connection in tuple(probe.PEERS):
                await connection.close()
                probe.PEERS.discard(connection)


if __name__ == "__main__":
    unittest.main()
