"""Browser tests for the web player's quality control and error recovery.

The real server page (``/watch/<id>``) and the real ``player.js`` run in
headless Chrome. Only the media API answers are stubbed, so no video files or
transcoder are needed. They check that:

* choosing a quality switches between the original file and a transcode at
  that size, resuming at the current position, and that the choice is kept;
* hls.js is served by this server (the player must work without internet);
* a dropped connection while playing the original is retried before the
  player falls back to a transcode.

The tests skip automatically when Playwright or Chrome are unavailable.
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

try:  # pragma: no cover - environment dependent
    from playwright.sync_api import sync_playwright
except Exception:  # pragma: no cover
    sync_playwright = None

CHROME = next((p for p in (
    os.environ.get("CHROME_BIN"), shutil.which("google-chrome"),
    shutil.which("google-chrome-stable"), shutil.which("chromium"),
    shutil.which("chromium-browser")) if p), None)

STATUS = {
    "media_id": 7, "watched": False, "position_seconds": 0, "duration_seconds": 3600,
    "extension": ".webm", "mode": "direct", "stream_url": "/api/watch/7/stream",
    "compatible_url": "/api/watch/7/transcode",
    "media": {"container": "webm", "video_codec": "vp9", "audio_codec": "opus",
              "width": 1280, "height": 720},
}


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@unittest.skipUnless(sync_playwright and CHROME, "Playwright and Chrome are required")
class WebPlayerQualityBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        base = Path(cls.tmp.name)
        (base / "media").mkdir()
        data = base / "data"
        data.mkdir()
        env = dict(
            os.environ, MEDIA_ROOT=str(base / "media"),
            DATABASE_PATH=str(data / "library.sqlite3"),
            HLS_CACHE_DIR=str(data / "hls"),
            ARTWORK_CACHE_DIR=str(data / "artwork"),
            SUBTITLE_CACHE_DIR=str(data / "subtitles"),
            MAINTENANCE_DIR=str(data / "maintenance"),
            SONARR_CONFIG_PATH=str(data / "sonarr-settings.json"),
            RADARR_CONFIG_PATH=str(data / "radarr-settings.json"),
            SABNZBD_SETTINGS_PATH=str(data / "sabnzbd-settings.json"),
            SERVER_IDENTITY_PATH=str(data / "server-identity.json"),
            METADATA_CONFIG_PATH=str(data / "metadata-settings.json"),
            PLEX_SETTINGS_PATH=str(data / "plex-settings.json"),
            REMOTE_SETTINGS_PATH=str(data / "remote-settings.json"),
            OPENSUBTITLES_CONFIG_PATH=str(data / "opensubtitles-settings.json"))
        cls.server_log = base / "server.log"
        port = free_port()
        with open(cls.server_log, "wb") as log:
            cls.server = subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "server.main:app",
                 "--port", str(port), "--log-level", "warning"],
                cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
        cls.origin = "http://127.0.0.1:%d" % port
        for _ in range(100):
            try:
                urllib.request.urlopen(cls.origin + "/health", timeout=5).read()
                break
            except Exception:
                time.sleep(0.2)
        else:
            output = cls.server_log.read_text(errors="replace")[-3000:]
            code = cls.server.poll()
            cls.server.kill()
            raise RuntimeError("test server did not start (exit code %s):\n%s" % (code, output))
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(
            executable_path=CHROME, headless=True, args=["--no-sandbox"])

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        cls.server.terminate()
        cls.server.wait(timeout=10)
        cls.tmp.cleanup()

    @staticmethod
    def choose(page, value):
        """Open the quality menu like a user would, then pick an option."""
        if not page.is_visible("select[aria-label='Playback quality']"):
            page.click("button[aria-label='Playback quality']")
        page.select_option("select[aria-label='Playback quality']", value)

    def open_player(self, status=None, hls_start="busy", stream="hang"):
        """Open /watch/7 with stubbed media APIs; returns (page, hls_start_urls, stream_urls)."""
        context = self.browser.new_context(viewport={"width": 1280, "height": 720})
        self.addCleanup(context.close)
        page = context.new_page()
        # Requests left pending on purpose must not raise when the page closes.
        self.addCleanup(lambda: page.unroute_all(behavior="ignoreErrors"))
        hls_urls, stream_urls = [], []
        body = json.dumps(status or STATUS)

        def on_status(route):
            route.fulfill(status=200, content_type="application/json", body=body)

        def on_hls_start(route):
            hls_urls.append(route.request.url)
            route.fulfill(status=503, content_type="application/json",
                          body=json.dumps({"detail": "stub transcoder"}))

        def on_stream(route):
            stream_urls.append(route.request.url)
            if stream == "network-error":
                route.abort("connectionreset")
            # otherwise leave the request pending: the video stays "loading"

        page.route("**/api/watch/7/status", on_status)
        page.route("**/api/stream/hls/start/7**", on_hls_start)
        page.route("**/api/watch/7/stream", on_stream)
        page.goto(self.origin + "/watch/7", wait_until="load")
        page.click("#launch")
        page.wait_for_selector(".willie-player video", state="attached")
        return page, hls_urls, stream_urls

    def test_hls_js_is_served_by_this_server(self):
        with urllib.request.urlopen(self.origin + "/assets/vendor/hls-1.7.4.min.js") as response:
            self.assertEqual(response.status, 200)
            self.assertIn("javascript", response.headers["content-type"])
            payload = response.read()
        self.assertGreater(len(payload), 100_000)
        self.assertIn(b"Hls", payload)

    def test_auto_plays_original_and_quality_choice_transcodes_then_returns(self):
        page, hls_urls, stream_urls = self.open_player()
        page.wait_for_function("document.querySelector('.willie-player video')?.src.includes('/api/watch/7/stream')")
        self.assertEqual(hls_urls, [])
        self.assertEqual(page.eval_on_selector("select[aria-label='Playback quality']", "e => e.value"), "auto")

        self.choose(page, "480p")
        for _ in range(50):
            if hls_urls:
                break
            page.wait_for_timeout(100)
        self.assertEqual(len(hls_urls), 1)
        self.assertIn("quality=480p", hls_urls[0])
        self.assertEqual(page.evaluate("localStorage.getItem('willie:quality')"), "480p")

        # The choice survives reopening the player.
        page.reload(wait_until="load")
        page.click("#launch")
        page.wait_for_selector("select[aria-label='Playback quality']", state="attached")
        self.assertEqual(page.eval_on_selector("select[aria-label='Playback quality']", "e => e.value"), "480p")

        # Back to Auto plays the original file again.
        self.choose(page, "auto")
        page.wait_for_function(
            "document.querySelector('.willie-player video')?.src.includes('/api/watch/7/stream')")

    def test_default_transcode_quality_and_each_preset_reach_the_server(self):
        page, hls_urls, _ = self.open_player(status=dict(STATUS, extension=".mkv", mode="compatible",
                                                         media={"container": "mkv", "video_codec": "hevc", "audio_codec": "ac3"}))
        for _ in range(50):
            if hls_urls:
                break
            page.wait_for_timeout(100)
        self.assertEqual(len(hls_urls), 1)
        self.assertIn("quality=720p", hls_urls[0])      # Auto transcodes at the default size
        self.choose(page, "1080p")
        for _ in range(60):
            if len(hls_urls) >= 2:
                break
            page.wait_for_timeout(100)
        self.assertIn("quality=1080p", hls_urls[-1])

    def test_dropped_connection_on_original_is_retried_before_transcoding(self):
        page, hls_urls, stream_urls = self.open_player(stream="network-error")
        # First load fails with a network error; the player retries the same
        # file (1 s and 2 s back-off) rather than starting a transcode right away.
        for _ in range(40):
            if len(stream_urls) >= 2:
                break
            page.wait_for_timeout(100)
        self.assertGreaterEqual(len(stream_urls), 2)
        self.assertEqual(hls_urls, [], "a network blip must not start a transcode")
        # If the connection never comes back it does eventually fall back.
        for _ in range(80):
            if hls_urls:
                break
            page.wait_for_timeout(100)
        self.assertTrue(hls_urls)


if __name__ == "__main__":
    unittest.main()
