"""Measured data use: bytes the server sends for one viewing are counted."""
import asyncio
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit

from fastapi import FastAPI

from server import hls, playback, usage


class Response:
    def __init__(self, status, body):
        self.status_code, self.content = status, body

    def json(self):
        return json.loads(self.content)


class Client:
    """Minimal ASGI client (the real TestClient needs httpx, which CI lacks)."""

    def __init__(self, app):
        self.app = app

    def request(self, method, url, headers=None):
        parts = urlsplit(url)
        scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": method,
                 "scheme": "http", "path": parts.path, "raw_path": parts.path.encode(),
                 "query_string": parts.query.encode(), "root_path": "",
                 "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
                 "client": ("127.0.0.1", 1), "server": ("testserver", 80)}
        sent = []

        async def run():
            async def receive():
                return {"type": "http.request", "body": b"", "more_body": False}

            async def send(message):
                sent.append(message)
            await self.app(scope, receive, send)

        asyncio.run(run())
        status = next(m["status"] for m in sent if m["type"] == "http.response.start")
        body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
        return Response(status, body)

    def get(self, url, headers=None):
        return self.request("GET", url, headers)

    def head(self, url):
        return self.request("HEAD", url)


class UsageCountingTests(unittest.TestCase):
    def setUp(self):
        usage.reset()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.movie = self.root / "movie.mp4"
        self.movie.write_bytes(b"x" * 100_000)
        app = FastAPI()
        app.include_router(playback.router)
        app.include_router(hls.router)
        self.client = Client(app)
        patcher = patch.object(playback, "_item", return_value=({"id": 1}, self.movie))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_direct_play_bytes_are_counted_for_the_viewing(self):
        body = self.client.get("/api/watch/1/stream?viewing=abcdef123456").content
        self.assertEqual(len(body), 100_000)
        self.assertEqual(usage.total("abcdef123456"), 100_000)

    def test_a_range_request_counts_only_the_bytes_sent(self):
        res = self.client.get("/api/watch/1/stream?viewing=abcdef123456",
                              headers={"Range": "bytes=1000-1999"})
        self.assertEqual(res.status_code, 206)
        self.assertEqual(usage.total("abcdef123456"), 1000)

    def test_head_requests_and_unlabelled_requests_cost_nothing(self):
        self.client.head("/api/watch/1/stream?viewing=abcdef123456")
        self.client.get("/api/watch/1/stream")
        self.assertEqual(usage.total("abcdef123456"), 0)

    def test_viewings_are_counted_separately_and_add_up(self):
        for _ in range(2):
            self.client.get("/api/watch/1/stream?viewing=first-view-1")
        self.client.get("/api/watch/1/stream?viewing=second-view-2")
        self.assertEqual(usage.total("first-view-1"), 200_000)
        self.assertEqual(usage.total("second-view-2"), 100_000)

    def test_malformed_ids_are_ignored(self):
        for bad in ("short", "has space in it", "../../etc/passwd", "a" * 41):
            self.assertIsNone(usage.valid(bad))
        self.client.get("/api/watch/1/stream?viewing=short")
        self.assertEqual(usage.total("short"), 0)

    def test_usage_endpoint_reports_the_total(self):
        self.client.get("/api/watch/1/stream?viewing=abcdef123456")
        res = self.client.get("/api/stream/hls/usage/abcdef123456")
        self.assertEqual(res.json(), {"bytes": 100_000})
        self.assertEqual(self.client.get("/api/stream/hls/usage/bad").status_code, 404)

    def test_hls_segments_count_towards_the_session_viewing(self):
        directory = self.root / "tok"
        directory.mkdir()
        (directory / "index.m3u8").write_text("#EXTM3U\n")
        (directory / "segment_000000.ts").write_bytes(b"s" * 5000)
        token = "a" * 32
        now = time.monotonic()
        session = hls.Session(token, directory, None, now, now, 1, "CPU", 60.0, 0.0,
                              hls.DEFAULT_QUALITY, "abcdef123456")
        with patch.dict(hls.ACTIVE, {token: session}), \
                patch.object(hls, "_purge"):
            self.client.get(f"/api/stream/hls/{token}/segment_000000.ts")
            self.client.get(f"/api/stream/hls/{token}/index.m3u8")
        self.assertEqual(usage.total("abcdef123456"), 5000 + len("#EXTM3U\n"))

    def test_memory_is_bounded(self):
        for index in range(usage.MAX_VIEWINGS + 25):
            usage.add(f"viewing-{index:05d}", 1)
        self.assertLessEqual(len(usage._TOUCHED), usage.MAX_VIEWINGS)


if __name__ == "__main__":
    unittest.main()
