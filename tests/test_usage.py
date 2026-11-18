"""Measured data use: bytes the server sends for one viewing are counted."""
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from server import hls, playback, usage


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
        self.client = TestClient(app)
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
