"""TV Home: the first row of posters must be fully on screen.

Regression: Home posters were made ~40% larger while the "Up next" banner above
them kept a fixed height, so on a 960x540 TV viewport the bottoms of the posters
fell below the screen edge. The banner now shrinks (and clamps its text) to
leave room, and the poster row keeps enough bottom padding for the focus ring.

Runs the REAL server pages in headless Chrome with the TV user agent. Skipped
when Playwright or Chrome are unavailable.
"""
import json
import os
import re
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
ACTIVITY = ROOT / "google-tv/app/src/main/java/studio/oneeyedwillie/tv/MainActivity.kt"
try:  # pragma: no cover - environment dependent
    from playwright.sync_api import sync_playwright
except Exception:  # pragma: no cover
    sync_playwright = None
CHROME = next((p for p in (
    os.environ.get("CHROME_BIN"), shutil.which("google-chrome"),
    shutil.which("google-chrome-stable"), shutil.which("chromium"),
    shutil.which("chromium-browser")) if p), None)
TV_UA = ("Mozilla/5.0 (Linux; Android 12; TV) AppleWebKit/537.36 "
         "Chrome/120.0 Safari/537.36 OneEyedWillieTV/1")
LONG = "The Extraordinarily Long Title of Movie Number %d: Director's Cut Extended Edition"
LONG_EPISODE = "S02E0%d · An Extremely Long Episode Title That Keeps Going And Going For Many Words"
SUMMARY = ("A very long description that keeps going and going so that it would take many "
           "lines if nothing limited it, mentioning every cast member, the plot, the "
           "production history and several other details nobody needs on a TV home screen. ") * 3


def tv_remote_script():
    source = ACTIVITY.read_text()
    match = re.search(r'private val TV_REMOTE_SCRIPT = """(.*?)"""\.trimIndent\(\)', source, re.S)
    assert match, "TV_REMOTE_SCRIPT not found in MainActivity.kt"
    return match.group(1)


def item(i, kind, long=False, watching=False):
    return dict(library_id=1, key="k%d" % i, kind=kind, title=(LONG % i) if long else "Movie %d" % i,
                year=2001, subtitle=(LONG_EPISODE % (i % 9)) if long else "", media_id=100 + i,
                play_state="next" if watching else None, season_number=2, poster_url=None,
                watched=False)


HOME = dict(
    continue_watching=[item(i, "tv", long=i % 2 == 0, watching=True) for i in range(8)],
    recent_movies=[item(20 + i, "movies", long=i % 3 == 0) for i in range(10)],
    recent_tv=[item(40 + i, "tv") for i in range(10)],
    # Recent shelves only show for library kinds that are set up.
    configured_library_kinds=["movies", "tv"],
    revision=1, progress_revision=[])
DETAILS = dict(title=LONG % 0, summary=SUMMARY, overview=SUMMARY, plot=SUMMARY,
               genres=["Drama", "Thriller", "Crime"], cast=["A. Actor", "B. Actress"],
               content_rating="TV-MA", network="Some Network", rating=8.1, year=2001)

MEASURE = """() => {
  const track = document.querySelector('#continue-watching .shelf-track');
  const feature = document.querySelector('.shelf > .home-feature');
  const copy = feature.querySelector('.home-feature-copy');
  const tiles = [...track.querySelectorAll('.tile')];
  const t = track.getBoundingClientRect();
  const lowestText = Math.max(...tiles.map(x => x.getBoundingClientRect().bottom));
  const cover = document.activeElement.querySelector('.cover');
  const c = cover.getBoundingClientRect();           // includes the 1.07 focus scale
  const cs = getComputedStyle(track);
  return {
    innerHeight, scrollY,
    trackBottom: t.bottom, lowestText, coverBottom: c.bottom,
    ringBottom: c.bottom + 2,                         // 2px ring
    clipBottom: t.bottom - parseFloat(cs.paddingBottom) + parseFloat(cs.paddingBottom),
    trackPaddingBottom: parseFloat(cs.paddingBottom),
    featureHeight: feature.getBoundingClientRect().height,
    copyOverflow: copy.scrollHeight - copy.clientHeight,
    featureOverflow: feature.scrollHeight - feature.clientHeight,
    copyBottom: copy.getBoundingClientRect().bottom, featureBottom: feature.getBoundingClientRect().bottom,
    summaryLines: Math.round(feature.querySelector('.home-feature-summary').getBoundingClientRect().height /
      parseFloat(getComputedStyle(feature.querySelector('.home-feature-summary')).lineHeight)),
    genresShown: getComputedStyle(feature.querySelector('.home-feature-genres')).display !== 'none'
  };
}"""


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@unittest.skipUnless(sync_playwright and CHROME, "Playwright and Chrome are required")
class TvHomeFitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        base = Path(cls.tmp.name)
        (base / "media").mkdir()
        data = base / "data"
        data.mkdir()
        cls.port = free_port()
        env = dict(
            os.environ, MEDIA_ROOT=str(base / "media"),
            DATABASE_PATH=str(data / "library.sqlite3"), HLS_CACHE_DIR=str(data / "hls"),
            ARTWORK_CACHE_DIR=str(data / "artwork"), SUBTITLE_CACHE_DIR=str(data / "subtitles"),
            MAINTENANCE_DIR=str(data / "maintenance"),
            SONARR_CONFIG_PATH=str(data / "sonarr-settings.json"),
            RADARR_CONFIG_PATH=str(data / "radarr-settings.json"),
            SABNZBD_SETTINGS_PATH=str(data / "sabnzbd-settings.json"))
        for key in [k for k in env if k.lower().endswith("proxy")]:
            env.pop(key)
        cls.server = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "server.main:app", "--port", str(cls.port),
             "--log-level", "warning"], cwd=ROOT, env=env)
        for _ in range(150):
            try:
                urllib.request.urlopen("http://127.0.0.1:%d/health" % cls.port, timeout=1)
                break
            except Exception:
                time.sleep(0.2)
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.server.terminate()
        cls.server.wait(10)
        cls.tmp.cleanup()

    def measure(self, width, height, home=HOME):
        context = self.browser.new_context(user_agent=TV_UA, viewport={"width": width, "height": height})
        self.addCleanup(context.close)
        page = context.new_page()
        page.route("**/api/home", lambda r: r.fulfill(json=home))
        page.route("**/api/home/revision", lambda r: r.fulfill(json={"revision": 1}))
        page.route("**/api/movies/details*", lambda r: r.fulfill(json=DETAILS))
        page.route("**/api/tv/show*", lambda r: r.fulfill(json=DETAILS))
        page.goto("http://127.0.0.1:%d/" % self.port)
        page.wait_for_selector("#continue-watching .shelf-track .tile", timeout=20000)
        page.wait_for_function("document.querySelector('.home-feature-title')?.textContent")
        # The app injects its own CSS and remote navigation from onPageFinished;
        # test the page exactly as the TV sees it, including that CSS.
        page.evaluate(tv_remote_script())
        page.wait_for_function("typeof window.__willieTvMove==='function'")
        page.wait_for_timeout(600)
        page.evaluate("document.querySelector('#continue-watching .tile-button').focus()")
        page.wait_for_timeout(300)
        return page.evaluate(MEASURE), page

    def test_first_selected_poster_is_not_clipped_at_left_edge(self):
        # In Android TV, injected focus styling must not override the inward
        # origin. The same protection is needed on ordinary browser Home.
        _, tv_page = self.measure(960, 540)
        desktop_context = self.browser.new_context(viewport={"width": 1440, "height": 900})
        self.addCleanup(desktop_context.close)
        browser_page = desktop_context.new_page()
        browser_page.route("**/api/home", lambda r: r.fulfill(json=HOME))
        browser_page.route("**/api/home/revision",
                           lambda r: r.fulfill(json={"revision": 1}))
        browser_page.route("**/api/movies/details*", lambda r: r.fulfill(json=DETAILS))
        browser_page.route("**/api/tv/show*", lambda r: r.fulfill(json=DETAILS))
        browser_page.goto("http://127.0.0.1:%d/" % self.port)
        browser_page.wait_for_selector("#continue-watching .shelf-track .tile-button")
        browser_page.locator("#continue-watching .shelf-track .tile-button").first.focus()
        browser_page.wait_for_timeout(300)

        for label, page in (("Android TV", tv_page), ("browser", browser_page)):
            with self.subTest(client=label):
                bounds = page.evaluate("""() => {
                  const track = document.querySelector('#continue-watching .shelf-track');
                  const cover = track.querySelector('.tile:first-child .tile-button .cover');
                  return {
                    railLeft: track.getBoundingClientRect().left,
                    artworkLeft: cover.getBoundingClientRect().left,
                    originX: parseFloat(getComputedStyle(cover).transformOrigin),
                    focus: cover.closest('.tile-button') === document.activeElement
                  };
                }""")
                self.assertTrue(bounds["focus"], bounds)
                self.assertAlmostEqual(bounds["originX"], 0, delta=1, msg=str(bounds))
                self.assertGreaterEqual(bounds["artworkLeft"] - 2,
                                        bounds["railLeft"], bounds)

    def test_tv_poster_grid_columns_do_not_overlap(self):
        for width, height in ((960, 540), (1280, 720), (1920, 1080)):
            with self.subTest(viewport=(width, height)):
                m, page = self.measure(width, height)
                boxes = page.evaluate("""() => [...document.querySelectorAll(
                    '#continue-watching .shelf-track .tile')]
                    .slice(0, 6).map(tile => {
                        const b = tile.getBoundingClientRect();
                        return {left:b.left,right:b.right,width:b.width};
                    })""")
                self.assertEqual(len(boxes), 6)
                for left, right in zip(boxes, boxes[1:]):
                    self.assertLessEqual(left["right"], right["left"] + 1,
                                         (width, height, boxes))
                self.assertGreater(min(x["width"] for x in boxes), 30)

    def test_first_row_of_posters_is_fully_on_screen(self):
        for width, height in ((960, 540), (1280, 720), (1920, 1080), (1024, 576), (1366, 768)):
            with self.subTest(viewport="%dx%d" % (width, height)):
                m, _ = self.measure(width, height)
                self.assertEqual(m["scrollY"], 0)
                # Posters and their titles end above the bottom of the screen.
                self.assertLessEqual(m["lowestText"], m["innerHeight"], m)
                self.assertLessEqual(m["trackBottom"], m["innerHeight"], m)
                # The focused (scaled) poster and its ring fit inside the row's
                # bottom padding instead of being clipped by it.
                self.assertLessEqual(m["ringBottom"], m["trackBottom"], m)

    def test_the_next_shelf_never_peeks_in_below_the_active_one(self):
        peek = """() => {
          const shelves = [...document.querySelectorAll('.content > .shelf')]
            .filter(s => s.querySelector('.shelf-track .tile-button'));
          const active = document.activeElement.closest('.shelf');
          const i = shelves.indexOf(active);
          const next = shelves[i + 1];
          return {index: i, count: shelves.length, innerHeight,
                  nextTop: next ? next.getBoundingClientRect().top : null,
                  activeTop: active.getBoundingClientRect().top,
                  activeBottom: active.getBoundingClientRect().bottom};
        }"""
        for width, height in ((960, 540), (1280, 720), (1920, 1080)):
            with self.subTest(viewport="%dx%d" % (width, height)):
                _, page = self.measure(width, height)
                for step in range(3):
                    seen = page.evaluate(peek)
                    if seen["nextTop"] is not None:
                        self.assertGreaterEqual(seen["nextTop"], seen["innerHeight"], seen)
                    page.evaluate("window.__willieTvMove('down')")
                    page.wait_for_timeout(750)
                # The last shelf scrolls to the top like the others.
                last = page.evaluate(peek)
                self.assertEqual(last["index"], last["count"] - 1, last)
                self.assertLessEqual(last["activeTop"], 12, last)

    def test_hero_text_is_clamped_and_never_overflows(self):
        for width, height in ((960, 540), (1280, 720), (1920, 1080)):
            with self.subTest(viewport="%dx%d" % (width, height)):
                m, _ = self.measure(width, height)
                self.assertLessEqual(m["copyOverflow"], 1, m)
                self.assertLessEqual(m["copyBottom"], m["featureBottom"] + 1, m)
                self.assertLessEqual(m["summaryLines"], 2, m)
                self.assertFalse(m["genresShown"])
                # The hero now uses the available screen height instead of
                # stopping at 350px and leaving a blank strip underneath.
                self.assertLessEqual(m["featureHeight"], m["innerHeight"], m)
                self.assertGreaterEqual(m["trackBottom"], m["innerHeight"] - 55, m)

    def test_hero_gives_up_height_only_as_needed(self):
        small, _ = self.measure(960, 540)
        big, _ = self.measure(1920, 1080)
        self.assertGreater(big["featureHeight"], small["featureHeight"])
        self.assertGreater(big["featureHeight"], 350)  # fill the larger viewport

    def test_the_fit_survives_a_resize(self):
        m, page = self.measure(1920, 1080)
        page.set_viewport_size({"width": 960, "height": 540})
        page.wait_for_timeout(400)
        after = page.evaluate(MEASURE)
        self.assertLessEqual(after["lowestText"], after["innerHeight"], after)

    def test_desktop_home_has_fullscreen_shelves_and_aligned_posters(self):
        context = self.browser.new_context(viewport={"width": 1440, "height": 900})
        self.addCleanup(context.close)
        page = context.new_page()
        page.route("**/api/home", lambda r: r.fulfill(json=HOME))
        page.route("**/api/home/revision", lambda r: r.fulfill(json={"revision": 1}))
        page.route("**/api/movies/details*", lambda r: r.fulfill(json=DETAILS))
        page.route("**/api/tv/show*", lambda r: r.fulfill(json=DETAILS))
        page.goto("http://127.0.0.1:%d/" % self.port)
        page.wait_for_selector("#continue-watching .shelf-track .tile")
        rects = page.evaluate("""() => [...document.querySelectorAll('#continue-watching .shelf-track .tile')]
            .slice(0, 5).map(tile => {
                const r = tile.getBoundingClientRect();
                return {top:r.top,width:r.width};
            })""")
        self.assertEqual(len(rects), 5)
        self.assertLess(max(r["top"] for r in rects)-min(r["top"] for r in rects), 2, rects)
        self.assertTrue(all(130 <= r["width"] <= 170 for r in rects), rects)
        # Each section is its own screen, in order; the following shelf stays
        # below the viewport until the viewer scrolls vertically.
        shelves = page.evaluate("""() => [...document.querySelectorAll('.content > .shelf')]
            .map(node => ({top:node.getBoundingClientRect().top + scrollY,
                           height:node.getBoundingClientRect().height}))""")
        self.assertEqual(len(shelves), 3)
        self.assertTrue(all(row["height"] >= 899 for row in shelves), shelves)
        self.assertGreaterEqual(shelves[1]["top"], shelves[0]["top"] + shelves[0]["height"] - 2)
        self.assertGreaterEqual(shelves[2]["top"], shelves[1]["top"] + shelves[1]["height"] - 2)
        # Every shelf gets its own steady-size details header from first paint.
        self.assertEqual(page.locator(".shelf > .home-feature").count(), 3)
        page.locator("#recent-movies .tile-button").first.hover()
        self.assertEqual(page.locator(".shelf > .home-feature").count(), 3)
        # The rail extends to the right side of the screen, rather than
        # terminating before the viewport's edge.
        right = page.evaluate("""() => {
            const b = document.querySelector('#continue-watching .shelf-track').getBoundingClientRect();
            return b.right;
        }""")
        self.assertGreaterEqual(right, 1438)
        # Browser must not force TV remote focus on a poster on initial load.
        self.assertFalse(page.evaluate("document.activeElement?.matches?.('.shelf-track .tile-button') || false"))

    def test_desktop_browsers_keep_their_normal_hero(self):
        context = self.browser.new_context(viewport={"width": 1440, "height": 900})
        self.addCleanup(context.close)
        page = context.new_page()
        page.route("**/api/home", lambda r: r.fulfill(json=HOME))
        page.route("**/api/home/revision", lambda r: r.fulfill(json={"revision": 1}))
        page.route("**/api/movies/details*", lambda r: r.fulfill(json=DETAILS))
        page.route("**/api/tv/show*", lambda r: r.fulfill(json=DETAILS))
        page.goto("http://127.0.0.1:%d/" % self.port)
        page.wait_for_selector(".shelf > .home-feature", timeout=20000)
        page.wait_for_timeout(500)
        inline = page.evaluate("document.querySelector('.shelf > .home-feature').style.height")
        self.assertEqual(inline, "")   # the TV-only fitting never touches other browsers


if __name__ == "__main__":
    unittest.main()
