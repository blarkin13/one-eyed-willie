"""Regression checks for the touch-sized Yarr Media home layout."""
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
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

CHROME = next((p for p in (
    os.environ.get("CHROME_BIN"), shutil.which("google-chrome"),
    shutil.which("google-chrome-stable"), shutil.which("chromium"),
    shutil.which("chromium-browser")) if p), None)

def make_item(n):
    return dict(library_id=1, key=f"mobile-{n}", kind="movies",
                title=f"Mobile Movie {n}", year=2026,
                subtitle=f"Episode with a very long subtitle {n}",
                media_id=100+n, play_state=None, poster_url=None, watched=False)

DATA = dict(continue_watching=[],
            recent_movies=[make_item(i) for i in range(8)],
            recent_tv=[], configured_library_kinds=["movies"],
            revision=1, progress_revision=[])

@unittest.skipUnless(sync_playwright and CHROME, "Playwright and Chrome required")
class MobileHomeLayoutTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        base = Path(cls.tmp.name)
        (base / "media").mkdir()
        (base / "data").mkdir()
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            cls.port = sock.getsockname()[1]
        env = dict(os.environ, MEDIA_ROOT=str(base / "media"),
                   DATABASE_PATH=str(base / "data/library.sqlite3"),
                   HLS_CACHE_DIR=str(base / "data/hls"),
                   ARTWORK_CACHE_DIR=str(base / "data/artwork"),
                   SUBTITLE_CACHE_DIR=str(base / "data/subtitles"),
                   MAINTENANCE_DIR=str(base / "data/maintenance"))
        for key in list(env):
            if key.lower().endswith("proxy"):
                env.pop(key)
        cls.server = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "server.main:app", "--port", str(cls.port),
             "--log-level", "warning"], cwd=ROOT, env=env)
        for _ in range(120):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{cls.port}/health", timeout=1)
                break
            except Exception:
                time.sleep(.2)
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.server.terminate()
        cls.server.wait(timeout=10)
        cls.tmp.cleanup()

    def open_phone(self, width):
        context = self.browser.new_context(viewport={"width": width, "height": 760},
                                           is_mobile=True, has_touch=True,
                                           device_scale_factor=1)
        self.addCleanup(context.close)
        page = context.new_page()
        page.route("**/api/home", lambda route: route.fulfill(json=DATA))
        page.route("**/api/home/revision", lambda route: route.fulfill(json={"revision": 1}))
        page.route("**/api/movies/details*", lambda route: route.fulfill(json={
            "year": 2026, "network": "Extremely long metadata",
            "overview": "A brief description suitable for a phone home screen."}))
        page.goto(f"http://127.0.0.1:{self.port}/")
        page.wait_for_selector("#recent-movies .shelf-track .tile-button", timeout=20000)
        return page

    def test_phone_has_no_document_sideways_scroll_and_dock_is_visible(self):
        for width in (320, 390, 430):
            with self.subTest(width=width):
                page = self.open_phone(width)
                data = page.evaluate("""() => {
                  const dock=document.querySelector('.sidebar .side-nav');
                  const track=document.querySelector('#recent-movies .shelf-track');
                  const m=document.querySelector('#recent-movies').closest('.shelf').querySelector('.home-feature-meta');
                  const r=dock.getBoundingClientRect();
                  return {width:document.documentElement.scrollWidth,
                          dockBottom:r.bottom, dockHeight:r.height,
                          trackScroll:track.scrollWidth>track.clientWidth,
                          scrollbar:getComputedStyle(track).scrollbarWidth,
                          metaWrap:getComputedStyle(m).flexWrap};
                }""")
                self.assertLessEqual(data["width"], width + 2)
                self.assertAlmostEqual(data["dockBottom"], 760, delta=2)
                self.assertLessEqual(data["dockHeight"], 85)
                self.assertTrue(data["trackScroll"])
                self.assertEqual(data["scrollbar"], "none")
                self.assertEqual(data["metaWrap"], "wrap")

    def test_swiping_posters_updates_feature_selection(self):
        page = self.open_phone(390)
        page.evaluate("""() => {
          const track=document.querySelector('#recent-movies .shelf-track');
          const posters=[...track.querySelectorAll('.tile')];
          track.scrollLeft=posters[2].offsetLeft-posters[0].offsetLeft;
        }""")
        page.wait_for_function("""() => document.querySelector('#recent-movies').closest('.shelf').querySelector('.home-feature-title')
                                     ?.textContent.includes('Mobile Movie 2')""", timeout=5000)


if __name__ == "__main__":
    unittest.main()
