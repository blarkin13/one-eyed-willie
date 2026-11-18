"""Pure unit tests for the isolated, non-production WebRTC probe."""
import os
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from tools.direct_peer_probe import authorize, deterministic_bytes, MAX_BYTES


class ProbeSafetyTests(unittest.TestCase):
    def test_deterministic_range(self):
        self.assertEqual(deterministic_bytes(0, 5), bytes([0, 1, 2, 3, 4]))
        self.assertEqual(deterministic_bytes(249, 4), bytes([249, 250, 0, 1]))
        self.assertEqual(deterministic_bytes(1024, 3), bytes([1024 % 251, 1025 % 251, 1026 % 251]))
        self.assertEqual(len(deterministic_bytes(1024, MAX_BYTES)), MAX_BYTES)

    def test_disabled_without_token(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(HTTPException) as ex:
                authorize("x" * 40)
            self.assertEqual(ex.exception.status_code, 404)

    def test_short_secret_disables_probe(self):
        with patch.dict(os.environ, {"YARR_DIRECT_PROBE_TOKEN": "not-long-enough"}):
            with self.assertRaises(HTTPException) as ex:
                authorize("not-long-enough")
            self.assertEqual(ex.exception.status_code, 404)

    def test_token_is_required_and_compared(self):
        token = "this-is-a-test-only-secret-that-is-long"
        with patch.dict(os.environ, {"YARR_DIRECT_PROBE_TOKEN": token}):
            for supplied in (None, "", token + "x", "a" * len(token)):
                with self.assertRaises(HTTPException) as ex:
                    authorize(supplied)
                self.assertEqual(ex.exception.status_code, 403 if supplied else 404)
            authorize(token)


class WebRtcRoundTripTests(unittest.IsolatedAsyncioTestCase):
    async def test_one_megabyte_over_encrypted_data_channel(self):
        """Two local aiortc peers negotiate via the same offer API used by the browser."""
        import asyncio
        import json
        import httpx
        from aiortc import RTCPeerConnection
        from tools.direct_peer_probe import app, PEERS

        token = "local-integration-test-secret-at-least-32-chars"
        browser = RTCPeerConnection()
        channel = browser.createDataChannel("yarr-direct-probe-v1")
        loop = asyncio.get_running_loop()
        finished = loop.create_future()
        received = bytearray()
        announced = []

        @channel.on("open")
        def on_open():
            channel.send(json.dumps({"type": "read", "offset": 1024, "length": MAX_BYTES}))

        @channel.on("message")
        def on_message(message):
            if finished.done():
                return
            if isinstance(message, str):
                control = json.loads(message)
                if control["type"] == "start":
                    announced.append(control["length"])
                elif control["type"] == "error":
                    finished.set_exception(AssertionError(control["message"]))
                elif control["type"] == "done":
                    finished.set_result(True)
            else:
                received.extend(message)

        try:
            await browser.setLocalDescription(await browser.createOffer())
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                with patch.dict(os.environ, {"YARR_DIRECT_PROBE_TOKEN": token}):
                    response = await client.post("/offer", headers={"X-Probe-Token": token},
                                                 json={"type": browser.localDescription.type,
                                                       "sdp": browser.localDescription.sdp})
            self.assertEqual(response.status_code, 200, response.text)
            answer = response.json()
            await browser.setRemoteDescription(
                __import__("aiortc").RTCSessionDescription(sdp=answer["sdp"], type=answer["type"]))
            await asyncio.wait_for(finished, timeout=25)
            self.assertEqual(announced, [MAX_BYTES])
            self.assertEqual(bytes(received), deterministic_bytes(1024, MAX_BYTES))
        finally:
            await browser.close()
            for pc in tuple(PEERS):
                await pc.close()
                PEERS.discard(pc)


if __name__ == "__main__":
    unittest.main()
