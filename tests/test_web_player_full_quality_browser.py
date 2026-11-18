"""Full stack: a real MKV, the real server and transcoder, played in Chrome.

Browsers cannot play Matroska, so "Best available" must fall back to the
original video passed through HLS (stream copy). Checks that Chrome really plays
it, at the file's own resolution, and that switching quality works.
Skipped without Playwright, Chrome or FFmpeg.
"""
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path

from tests.test_hls_audio_tracks import pitch_hz

ROOT = Path(__file__).resolve().parents[1]

try:  # pragma: no cover - environment dependent
    from playwright.sync_api import sync_playwright
except Exception:  # pragma: no cover
    sync_playwright = None

CHROME = next((p for p in (
    os.environ.get("CHROME_BIN"), shutil.which("google-chrome"),
    shutil.which("google-chrome-stable"), shutil.which("chromium"),
    shutil.which("chromium-browser")) if p), None)
FFMPEG = "/usr/bin/ffmpeg"
READY = bool(sync_playwright and CHROME and os.path.isfile(FFMPEG) and os.path.isfile("/usr/bin/ffprobe"))


def call(url, method="GET", body=None):
    request = urllib.request.Request(
        url, method=method, data=json.dumps(body).encode() if body else None,
        headers={"content-type": "application/json"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read() or b"null")


@unittest.skipUnless(READY, "Playwright, Chrome and FFmpeg are required")
class FullQualityBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        base = Path(cls.tmp.name)
        folder = base / "media" / "Movies" / "Sample Film (2001)"
        folder.mkdir(parents=True)
        cls.make_movie(folder / "Sample.Film.2001.mkv")
        data = base / "data"
        data.mkdir()
        env = dict(
            os.environ, MEDIA_ROOT=str(base / "media"),
            DATABASE_PATH=str(data / "library.sqlite3"), HLS_CACHE_DIR=str(data / "hls"),
            ARTWORK_CACHE_DIR=str(data / "artwork"), SUBTITLE_CACHE_DIR=str(data / "subtitles"),
            MAINTENANCE_DIR=str(data / "maintenance"),
            SONARR_CONFIG_PATH=str(data / "sonarr-settings.json"),
            RADARR_CONFIG_PATH=str(data / "radarr-settings.json"),
            SABNZBD_SETTINGS_PATH=str(data / "sabnzbd-settings.json"),
            SERVER_IDENTITY_PATH=str(data / "server-identity.json"),
            METADATA_CONFIG_PATH=str(data / "metadata-settings.json"),
            PLEX_SETTINGS_PATH=str(data / "plex-settings.json"),
            REMOTE_SETTINGS_PATH=str(data / "remote-settings.json"),
            OPENSUBTITLES_CONFIG_PATH=str(data / "opensubtitles-settings.json"))
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        cls.log = base / "server.log"
        with open(cls.log, "wb") as log:
            cls.server = subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "server.main:app", "--port", str(port),
                 "--log-level", "warning"], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
        cls.origin = "http://127.0.0.1:%d" % port
        for _ in range(100):
            try:
                call(cls.origin + "/health")
                break
            except Exception:
                time.sleep(0.2)
        else:
            output = cls.log.read_text(errors="replace")[-3000:]
            cls.server.kill()
            raise RuntimeError("test server did not start:\n" + output)
        library = call(cls.origin + "/api/libraries", "POST", {
            "name": "Movies", "kind": "movies", "path": str(base / "media" / "Movies")})
        call("%s/api/libraries/%d/scan" % (cls.origin, library["id"]), "POST")
        with sqlite3.connect(data / "library.sqlite3") as conn:
            cls.media_id = conn.execute("SELECT id FROM media").fetchone()[0]
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(
            executable_path=CHROME, headless=True,
            args=["--no-sandbox", "--autoplay-policy=no-user-gesture-required"])

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        cls.server.terminate()
        cls.server.wait(timeout=10)
        cls.tmp.cleanup()

    @classmethod
    def make_movie(cls, path):
        # 640x360 h264 + two AC3 tracks in MKV: neither the container nor the audio plays in a browser.
        subprocess.run(
            [FFMPEG, "-v", "error", "-nostdin", "-y", "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=24",
             "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
             "-f", "lavfi", "-i", "sine=frequency=880:sample_rate=48000", "-t", "40",
             "-map", "0:v", "-map", "1:a", "-map", "2:a",
             "-c:v", "libx264", "-preset", "ultrafast", "-g", "48", "-pix_fmt", "yuv420p",
             "-c:a", "ac3", "-ac", "2",   # English (440 Hz) first, French (880 Hz) second
             "-metadata:s:a:0", "language=eng", "-metadata:s:a:1", "language=fre",
             str(path)], check=True)

    def open_player(self):
        context = self.browser.new_context(viewport={"width": 1280, "height": 720})
        self.addCleanup(context.close)
        page = context.new_page()

        def close_player():
            # Closing the player releases its transcoding session (the server
            # allows only two at once), which a bare browser close would not.
            try:
                page.evaluate("window.WilliePlayer && window.WilliePlayer.close()")
                page.wait_for_timeout(400)
            except Exception:
                pass

        self.addCleanup(close_player)
        page.goto("%s/watch/%d" % (self.origin, self.media_id), wait_until="load")
        page.click("#launch")
        return page

    def playing(self, page, width=None, engine=None, timeout=45000):
        page.wait_for_function(
            """([width, engine]) => {
              const surface = document.querySelector('.willie-player');
              const v = surface && surface.querySelector('video');
              return !!v && v.currentTime > 1.5 && !v.paused && v.readyState >= 3 &&
                (!width || v.videoWidth === width) && (!engine || surface.dataset.engine === engine);
            }""", arg=[width, engine], timeout=timeout)

    def test_choosing_the_second_audio_track_really_changes_the_sound(self):
        page = self.open_player()
        playlists = []
        page.on("request", lambda r: playlists.append(r.url) if r.url.endswith("/index.m3u8") else None)
        self.playing(page, width=640)
        page.click("button[aria-label='Data use and quality']")
        page.wait_for_selector(".willie-audio-row[data-audio='1']")
        self.assertIn("English", page.text_content(".willie-audio-row[data-audio='0']"))
        self.assertIn("French", page.text_content(".willie-audio-row[data-audio='1']"))
        first = len(playlists)
        page.click(".willie-audio-row[data-audio='1']")
        for _ in range(100):            # the old stream is replaced by a new one
            if len(playlists) > first:
                break
            page.wait_for_timeout(100)
        self.assertGreater(len(playlists), first)
        self.playing(page, width=640, engine="Original video (no re-encode)")
        # Decode what the server is streaming now: it is the French (880 Hz) track.
        self.assertAlmostEqual(pitch_hz(playlists[-1]), 880, delta=30)

    def test_best_available_plays_the_original_video_through_hls(self):
        page = self.open_player()
        self.playing(page, width=640, engine="Original video (no re-encode)")
        self.assertEqual(page.evaluate("document.querySelector('.willie-player video').videoHeight"), 360)
        page.click("button[aria-label='Data use and quality']")
        page.wait_for_selector("button.willie-data-row[data-quality='full']")
        self.assertEqual(page.get_attribute("button.willie-data-row[data-quality='full']", "aria-pressed"), "true")
        self.assertIn("Full quality", page.text_content("button.willie-data-row[data-quality='full']"))
        self.assertIsNone(page.query_selector("button.willie-data-row[data-quality='auto']"))

    def test_can_switch_to_a_cheaper_tier_and_back_to_full_quality(self):
        page = self.open_player()
        self.playing(page, width=640, engine="Original video (no re-encode)")
        page.click("button[aria-label='Data use and quality']")
        page.click("button.willie-data-row[data-quality='480p']")
        self.playing(page, width=854, engine="CPU")             # padded 16:9 transcode frame
        page.click("button[aria-label='Data use and quality']")
        page.click("button.willie-data-row[data-quality='full']")
        self.playing(page, width=640, engine="Original video (no re-encode)")
        self.assertEqual(page.evaluate("localStorage.getItem('willie:quality')"), "full")

    def test_seeking_in_full_quality_keeps_playing(self):
        page = self.open_player()
        self.playing(page, width=640, engine="Original video (no re-encode)")
        # Use the seek bar like a viewer: jump to 70% of the 40 s film (28 s), far
        # beyond what has been produced so far, which starts a new session there.
        # The bar reports the true position in the film, not the position within a
        # stream that began part-way through.
        page.evaluate(
            """() => { const bar = document.querySelector('.willie-timeline input');
                       bar.value = '700';
                       bar.dispatchEvent(new Event('input', {bubbles: true}));
                       bar.dispatchEvent(new Event('change', {bubbles: true})); }""")
        page.wait_for_function(
            """() => { const v = document.querySelector('.willie-player video');
                       const bar = document.querySelector('.willie-timeline input');
                       return v && Number(bar.value) > 715 && !v.paused && v.readyState >= 3; }""",
            timeout=45000)


if __name__ == "__main__":
    unittest.main()
