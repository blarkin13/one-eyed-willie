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


# One hour, 4 GB original. Costs are chosen so each data limit has one clear answer.
ESTIMATES = {
    "duration_seconds": 3600, "default": "720p",
    "original": {"bytes": 4_000_000_000, "kbps": 8900},
    "qualities": [
        {"id": "1080p", "kbps": 8128, "kind": "up_to", "bytes": 3_600_000_000},
        {"id": "720p", "kbps": 3328, "kind": "up_to", "bytes": 1_500_000_000},
        {"id": "480p", "kbps": 1096, "kind": "about", "bytes": 500_000_000},
        {"id": "360p", "kbps": 696, "kind": "about", "bytes": 300_000_000},
        {"id": "240p", "kbps": 364, "kind": "about", "bytes": 170_000_000},
    ],
}
CELLULAR = ("Object.defineProperty(navigator,'connection',"
            "{value:{type:'cellular',saveData:false},configurable:true});")


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
        """Open the data/quality panel like a user would, then pick a row."""
        row = "button.willie-data-row[data-quality='%s']" % value
        if not page.is_visible(row):
            page.click("button[aria-label='Data use and quality']")
        page.click(row)

    def open_player(self, status=None, hls_start="busy", stream="hang", metered=False,
                    estimates=ESTIMATES, viewport=None, setup=None):
        """Open /watch/7 with stubbed media APIs; returns (page, hls_start_urls, stream_urls)."""
        context = self.browser.new_context(viewport=viewport or {"width": 1280, "height": 720})
        self.addCleanup(context.close)
        page = context.new_page()
        if metered:
            page.add_init_script(CELLULAR)
        # Requests left pending on purpose must not raise when the page closes.
        hanging = []

        def release():
            for held in hanging:
                try:
                    held.abort()
                except Exception:
                    pass
            page.unroute_all(behavior="ignoreErrors")

        self.addCleanup(release)
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
            else:
                hanging.append(route)   # left pending: the video stays "loading"

        page.route("**/api/stream/hls/estimates/7", lambda route: route.fulfill(
            status=200, content_type="application/json", body=json.dumps(estimates))
            if estimates else route.fulfill(status=404, content_type="application/json", body="{}"))
        page.route("**/api/watch/7/status", on_status)
        page.route("**/api/stream/hls/start/7**", on_hls_start)
        page.route("**/api/watch/7/stream*", on_stream)
        if setup:
            setup(page)
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
        page.click("button[aria-label='Data use and quality']")
        self.assertEqual(page.get_attribute("button.willie-data-row[data-quality='auto']", "aria-pressed"), "true")

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
        page.click("button[aria-label='Data use and quality']")
        self.assertEqual(page.get_attribute("button.willie-data-row[data-quality='480p']", "aria-pressed"), "true")

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

    def test_leaving_while_a_stream_is_starting_releases_it(self):
        """Closing the player mid-start must not leave a transcoder holding a server slot."""
        held, deleted = [], []

        def setup(page):
            page.route("**/api/stream/hls/start/7**", lambda route: held.append(route))
            page.route("**/api/stream/hls/%s" % ("c" * 32), lambda route: (
                deleted.append(route.request.method), route.fulfill(status=200, content_type="application/json",
                                                                   body='{"stopped": true}')))

        page, _, _ = self.open_player(status=dict(STATUS, extension=".mkv", mode="compatible",
                                                  media={"container": "mkv", "video_codec": "hevc", "audio_codec": "ac3"}),
                                      setup=setup)
        for _ in range(50):
            if held:
                break
            page.wait_for_timeout(100)
        self.assertTrue(held, "the stream start never went out")
        page.evaluate("WilliePlayer.close()")                    # the viewer backs out
        held[0].fulfill(status=200, content_type="application/json", body=json.dumps(
            {"session": "c" * 32, "playlist": "/x.m3u8", "engine": "CPU", "quality": "720p",
             "duration": 3600, "start": 0}))
        for _ in range(50):
            if deleted:
                break
            page.wait_for_timeout(100)
        self.assertEqual(deleted, ["DELETE"])


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

    def rows(self, page):
        return {r["id"]: r["text"] for r in page.eval_on_selector_all(
            "button.willie-data-row", "els => els.map(e => ({id: e.dataset.quality, text: e.textContent}))")}

    def test_panel_shows_what_each_choice_costs_for_the_rest_of_the_video(self):
        page, _, _ = self.open_player()
        page.click("button[aria-label='Data use and quality']")
        page.wait_for_selector("button.willie-data-row[data-quality='480p']")
        rows = self.rows(page)
        self.assertEqual(list(rows), ["auto", "1080p", "720p", "480p", "360p", "240p"])
        self.assertIn("4.0 GB", rows["auto"])                 # the original file: exact size
        self.assertNotIn("about", rows["auto"])
        self.assertIn("up to 3.6 GB", rows["1080p"])
        self.assertIn("up to 1.5 GB", rows["720p"])
        self.assertIn("about 500 MB", rows["480p"])
        self.assertIn("about 170 MB", rows["240p"])
        self.assertIn("1h 00m", page.text_content(".willie-data-heading"))

    def test_data_limit_picks_the_best_quality_that_fits(self):
        for limit, expected in (("1000000000", "480p"), ("250000000", "240p"), ("2000000000", "720p"),
                                ("5000000000", "auto")):
            with self.subTest(limit=limit):
                page, hls_urls, _ = self.open_player()
                page.click("button[aria-label='Data use and quality']")
                page.select_option("select[aria-label='Fit to a data limit']", limit)
                page.wait_for_function(
                    "localStorage.getItem('willie:quality') === %s" % json.dumps(expected))
                if expected != "auto":
                    for _ in range(50):
                        if hls_urls:
                            break
                        page.wait_for_timeout(100)
                    self.assertIn("quality=" + expected, hls_urls[-1])

    def test_a_limit_nothing_fits_says_so_and_chooses_the_cheapest(self):
        page, _, _ = self.open_player()
        page.click("button[aria-label='Data use and quality']")
        page.select_option("select[aria-label='Fit to a data limit']", "250000000")
        # 250 MB fits 240p (170 MB); a tiny budget would not. Use a smaller estimate set.
        page2, _, _ = self.open_player(estimates=dict(ESTIMATES, qualities=[
            dict(q, bytes=q["bytes"] * 3) for q in ESTIMATES["qualities"]]))
        page2.click("button[aria-label='Data use and quality']")
        page2.select_option("select[aria-label='Fit to a data limit']", "250000000")
        self.assertIn("Even 240p needs about 510 MB", page2.text_content(".willie-data-note"))
        page2.wait_for_function("localStorage.getItem('willie:quality') === '240p'")

    def test_rows_work_without_estimates(self):
        page, _, _ = self.open_player(estimates=None)
        page.click("button[aria-label='Data use and quality']")
        rows = self.rows(page)
        self.assertEqual(list(rows), ["auto", "1080p", "720p", "480p", "360p", "240p"])
        self.assertFalse(page.is_visible("select[aria-label='Fit to a data limit']"))
        self.choose(page, "360p")
        page.wait_for_function("localStorage.getItem('willie:quality') === '360p'")

    def test_on_mobile_data_nothing_plays_until_a_choice_is_made(self):
        page, hls_urls, stream_urls = self.open_player(metered=True)
        page.wait_for_selector("button.willie-data-row[data-quality='480p']")
        self.assertIn("mobile data", page.text_content(".willie-data-heading"))
        page.wait_for_timeout(1200)
        self.assertEqual((hls_urls, stream_urls), ([], []), "no media may be requested before the choice")
        # The panel cannot be dismissed without choosing.
        page.click("button[aria-label='Data use and quality']")
        self.assertTrue(page.is_visible("button.willie-data-row[data-quality='480p']"))
        page.click("button.willie-data-row[data-quality='480p']")
        for _ in range(50):
            if hls_urls:
                break
            page.wait_for_timeout(100)
        self.assertIn("quality=480p", hls_urls[0])
        # Once chosen, later plays start straight away.
        page.reload(wait_until="load")
        page.click("#launch")
        page.wait_for_timeout(1200)
        self.assertGreaterEqual(len(hls_urls), 2)

    def test_on_mobile_data_choosing_the_original_streams_the_file(self):
        page, hls_urls, stream_urls = self.open_player(metered=True)
        page.wait_for_selector("button.willie-data-row[data-quality='auto']")
        page.click("button.willie-data-row[data-quality='auto']")
        page.wait_for_function(
            "document.querySelector('.willie-player video')?.src.includes('/api/watch/7/stream')")
        self.assertEqual(hls_urls, [])


if __name__ == "__main__":
    unittest.main()
