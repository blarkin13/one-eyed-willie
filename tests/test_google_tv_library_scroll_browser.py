"""Browser-level regression tests for Google TV library navigation.

These run the REAL server page (``/movies``) and the REAL remote-navigation
script extracted from ``MainActivity.kt`` inside headless Chrome, then drive it
exactly the way the native activity does: ``window.__willieTvMove(direction)``
about every 190 ms while a D-pad button is held.

They guard the root causes of the "library jumps back to the top while holding
Down" bug:

* the scroll animation took its clock from ``performance.now()`` inside the key
  handler, while ``requestAnimationFrame`` timestamps are frame-start times, so
  progress went negative and ``scrollTop`` was thrown backwards;
* every key press scanned all posters with getComputedStyle()/getBoundingClientRect(),
  turning each press into a long task on slow TV hardware;
* a background catalog refresh emptied the grid and only restored focus/scroll
  for the first 24 posters.

The tests skip automatically when Playwright or Chrome are unavailable.
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
ACTIVITY = (ROOT / "google-tv/app/src/main/java/studio/oneeyedwillie/tv/MainActivity.kt")

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
TITLES = ("Carry On,Clean,Companion,Cuckoo,Alien,Brave,Cars,Dune,Eagle,Fargo,"
          "Gladiator,Heat,Inception,Jaws,Kong,Logan,Matrix,Nope,Oldboy,Psycho").split(",")
MOVIES = 400  # 5 per row on a 960px TV viewport -> 80 rows
SHOWS = 120   # the TV Shows library must keep behaving as before


def tv_remote_script() -> str:
    source = ACTIVITY.read_text()
    match = re.search(r'private val TV_REMOTE_SCRIPT = """(.*?)"""\.trimIndent\(\)',
                      source, re.S)
    assert match, "TV_REMOTE_SCRIPT not found in MainActivity.kt"
    return match.group(1)


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def call(url, method="GET", body=None):
    request = urllib.request.Request(
        url, method=method, data=json.dumps(body).encode() if body else None,
        headers={"content-type": "application/json"})
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read() or b"null")


# Measures the whole held-button sequence inside the page: every animation
# frame's scrollTop and whether the selected tile intersects the viewport.
HOLD = """async ({directions, interval, skew}) => {
  const root = document.scrollingElement;
  const frames = [], steps = [];
  let running = true;
  const tileOf = () => document.activeElement?.closest?.('.tile');
  const coverOf = () => document.activeElement?.querySelector?.('.cover');
  const sample = () => {
    const tile = tileOf(), r = tile?.getBoundingClientRect();
    frames.push({
      y: root.scrollTop,
      visible: !!r && r.bottom > 0 && r.top < innerHeight,
      title: document.activeElement?.querySelector?.('h3')?.textContent || ''
    });
    if (running) requestAnimationFrame(sample);
  };
  requestAnimationFrame(sample);
  const originalNow = performance.now.bind(performance);
  for (const direction of directions) {
    // Emulate a main thread that was busy: timestamps taken inside the key
    // handler are later than the next frame's start time.
    if (skew) performance.now = () => originalNow() + skew;
    window.__willieTvMove(direction);
    performance.now = originalNow;
    steps.push({
      direction,
      title: document.activeElement?.querySelector?.('h3')?.textContent || '',
      row: Math.round(tileOf()?.offsetTop || 0)
    });
    await new Promise(r => setTimeout(r, interval));
  }
  await new Promise(r => setTimeout(r, 450));   // let the last glide settle
  running = false;
  const r = coverOf()?.getBoundingClientRect();
  return {frames, steps, finalY: root.scrollTop,
          // the poster itself must be completely on screen once settled
          finalVisible: !!r && r.top >= 0 && r.bottom <= innerHeight,
          maxY: root.scrollHeight - root.clientHeight};
}"""


@unittest.skipUnless(sync_playwright and CHROME, "Playwright and Chrome are required")
class LibraryScrollBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        base = Path(cls.tmp.name)
        for index in range(MOVIES):
            title = "%s %04d" % (TITLES[index % len(TITLES)], index)
            folder = base / "media" / "Movies" / ("%s (%d)" % (title, 1980 + index % 40))
            folder.mkdir(parents=True)
            (folder / ("%s.%d.mkv" % (title, 1980 + index % 40))).write_bytes(b"")
        for index in range(SHOWS):
            show = "Show %03d" % index
            folder = base / "media" / "TV" / show / "Season 01"
            folder.mkdir(parents=True)
            (folder / ("%s.S01E01.mkv" % show)).write_bytes(b"")
        cls.port = free_port()
        env = dict(os.environ, MEDIA_ROOT=str(base / "media"),
                   DATABASE_PATH=str(base / "data" / "library.sqlite3"))
        cls.server = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "server.main:app",
             "--port", str(cls.port), "--log-level", "warning"],
            cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cls.origin = "http://127.0.0.1:%d" % cls.port
        for _ in range(100):
            try:
                call(cls.origin + "/health")
                break
            except Exception:
                time.sleep(0.2)
        else:
            raise RuntimeError("test server did not start")
        library = call(cls.origin + "/api/libraries", "POST", {
            "name": "Movies", "kind": "movies", "path": str(base / "media" / "Movies")})
        call("%s/api/libraries/%d/scan" % (cls.origin, library["id"]), "POST")
        tv = call(cls.origin + "/api/libraries", "POST", {
            "name": "TV", "kind": "tv", "path": str(base / "media" / "TV")})
        call("%s/api/libraries/%d/scan" % (cls.origin, tv["id"]), "POST")
        cls.script = tv_remote_script()
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

    def open_library(self, cpu=1, section="movies", count=MOVIES):
        context = self.browser.new_context(
            viewport={"width": 960, "height": 540}, user_agent=TV_UA)
        self.addCleanup(context.close)
        page = context.new_page()
        if cpu != 1:
            cdp = context.new_cdp_session(page)
            cdp.send("Emulation.setCPUThrottlingRate", {"rate": cpu})
        page.goto(self.origin + "/" + section, wait_until="load")
        page.wait_for_function(
            "document.querySelectorAll('#items .tile-button').length >= %d" % count,
            timeout=30000)
        # The app injects this script from onPageFinished.
        page.evaluate(self.script)
        page.wait_for_function(
            "document.activeElement?.matches?.('#items .tile-button')", timeout=10000)
        page.wait_for_timeout(300)
        return page

    def hold(self, page, directions, interval=190, skew=0):
        return page.evaluate(HOLD, {"directions": directions,
                                    "interval": interval, "skew": skew})

    def assert_monotonic(self, result, direction):
        frames = result["frames"]
        sign = 1 if direction == "down" else -1
        worst = 0
        for before, after in zip(frames, frames[1:]):
            worst = max(worst, sign * (before["y"] - after["y"]))
        self.assertLessEqual(
            worst, 1, "viewport moved %.0fpx against the %s direction" % (worst, direction))

    def test_hold_down_through_twenty_rows_without_backward_jumps(self):
        for cpu in (1, 6):
            with self.subTest(cpu=cpu):
                page = self.open_library(cpu)
                result = self.hold(page, ["down"] * 24)
                rows = [step["row"] for step in result["steps"]]
                self.assertEqual(rows, sorted(rows))
                self.assertEqual(len(set(rows)), 24, "every press must reach a new row")
                self.assert_monotonic(result, "down")
                self.assertTrue(all(f["visible"] for f in result["frames"][5:]),
                                "selected poster left the viewport")
                self.assertTrue(result["finalVisible"])
                self.assertGreater(result["finalY"], 20 * 250)

    def test_late_animation_clock_cannot_throw_the_page_backwards(self):
        """Deterministic version of the original defect (see module docstring)."""
        page = self.open_library()
        self.hold(page, ["down"] * 6)                 # get well away from the top
        start = page.evaluate("document.scrollingElement.scrollTop")
        self.assertGreater(start, 1000)
        result = self.hold(page, ["down"] * 14, skew=400)
        self.assert_monotonic(result, "down")
        self.assertGreaterEqual(min(f["y"] for f in result["frames"]), start - 1)
        self.assertTrue(all(f["visible"] for f in result["frames"][3:]),
                        "selection left the viewport")
        self.assertTrue(result["finalVisible"])

    def test_hold_up_returns_in_order_and_ends_at_top(self):
        page = self.open_library(4)
        down = self.hold(page, ["down"] * 22)
        self.assertGreater(down["finalY"], 0)
        up = self.hold(page, ["up"] * 22)
        rows = [step["row"] for step in up["steps"]]
        self.assertEqual(rows, sorted(rows, reverse=True))
        self.assert_monotonic(up, "up")
        self.assertTrue(all(f["visible"] for f in up["frames"][5:]))
        self.assertLess(up["finalY"], 5)

    def test_rapid_direction_changes_and_interrupted_animations(self):
        page = self.open_library(4)
        pattern = (["down"] * 6 + ["up"] * 2 + ["down"] * 5 + ["up"] * 4 +
                   ["right", "down", "left", "down"] * 2 + ["down"] * 6)
        result = self.hold(page, pattern, interval=45)  # far faster than a glide
        self.assertTrue(result["finalVisible"], "selection ended off-screen")
        self.assertTrue(all(f["visible"] for f in result["frames"][5:]),
                        "selection left the viewport while animations were interrupted")
        self.assertGreaterEqual(result["finalY"], 0)
        self.assertLessEqual(result["finalY"], result["maxY"] + 1)

    def test_catalog_refresh_keeps_deep_selection_and_scroll(self):
        page = self.open_library()
        self.hold(page, ["down"] * 30)
        before = page.evaluate(
            "({y: document.scrollingElement.scrollTop,"
            " key: document.activeElement.dataset.hoverKey})")
        self.assertGreater(before["y"], 5000)
        # What the 15-second revision poll does once media changes.
        page.evaluate("load({preserveFocus:true}, true)")
        page.wait_for_function(
            "document.querySelectorAll('#items .tile-button').length >= %d" % MOVIES,
            timeout=30000)
        after = page.evaluate(
            "({y: document.scrollingElement.scrollTop,"
            " key: document.activeElement.dataset.hoverKey})")
        self.assertEqual(after["key"], before["key"], "selected poster was lost")
        self.assertLess(abs(after["y"] - before["y"]), 4)
        # Navigation keeps working afterwards and moves exactly one row.
        result = self.hold(page, ["down", "down"])
        self.assertEqual(len({s["row"] for s in result["steps"]}), 2)
        self.assertTrue(result["finalVisible"])

    def describe(self, page):
        return page.evaluate("""(() => {
          const a = document.activeElement;
          return {
            kind: a?.matches?.('#items .tile-button') ? 'poster'
                : a?.closest?.('#alpha-nav') ? 'alphabet'
                : a?.closest?.('#library-masthead') ? 'toolbar'
                : a?.closest?.('#app-nav') ? 'sidebar' : (a?.tagName || 'none'),
            title: a?.querySelector?.('h3')?.textContent || a?.textContent?.trim() || '',
            top: a?.closest?.('.tile')?.offsetTop ?? -1,
            left: a?.closest?.('.tile')?.offsetLeft ?? -1,
            scroll: document.scrollingElement.scrollTop };
        })()""")

    def press(self, page, direction):
        page.evaluate("window.__willieTvMove(%s)" % json.dumps(direction))
        page.wait_for_timeout(260)       # let the 190ms glide finish
        return self.describe(page)

    def test_row_alphabet_toolbar_and_sidebar_moves_still_work(self):
        page = self.open_library()
        first = self.describe(page)
        self.assertEqual((first["kind"], first["top"]), ("poster", 0))
        # Right walks the row left to right at one constant height...
        row = [first]
        for _ in range(4):
            row.append(self.press(page, "right"))
        self.assertEqual({r["top"] for r in row}, {0})
        lefts = [r["left"] for r in row]
        self.assertEqual(lefts, sorted(lefts))
        self.assertEqual(len(set(lefts)), 5)
        # ...and one more Right enters the A-Z rail, Left returns to that poster.
        self.assertEqual(self.press(page, "right")["kind"], "alphabet")
        back = self.press(page, "left")
        self.assertEqual((back["kind"], back["title"]), ("poster", row[-1]["title"]))
        # Down twice then Left reaches the sidebar from the first column.
        self.press(page, "left"); self.press(page, "left"); self.press(page, "left")
        self.press(page, "left")
        self.press(page, "down"); self.press(page, "down")
        self.assertEqual(self.press(page, "left")["kind"], "sidebar")
        self.assertEqual(self.press(page, "right")["kind"], "poster")
        # Up from row 3 retraces rows; Up from row 1 reaches the toolbar and
        # the full header is restored; Down returns to the first poster row.
        for _ in range(10):
            state = self.press(page, "up")
            if state["kind"] != "poster":
                break
        self.assertEqual(state["kind"], "toolbar")
        self.assertEqual(state["scroll"], 0)
        again = self.press(page, "down")
        self.assertEqual((again["kind"], again["top"]), ("poster", 0))

    def test_down_then_up_returns_to_the_same_poster(self):
        page = self.open_library()
        self.press(page, "right"); self.press(page, "right")
        start = self.describe(page)
        for _ in range(7):
            self.press(page, "down")
        for _ in range(7):
            end = self.press(page, "up")
        self.assertEqual((end["title"], end["scroll"]), (start["title"], 0))

    def test_tv_shows_library_hold_down_and_up_stays_smooth(self):
        for cpu in (1, 6):
            with self.subTest(cpu=cpu):
                page = self.open_library(cpu, section="tv", count=SHOWS)
                down = self.hold(page, ["down"] * 20)
                rows = [step["row"] for step in down["steps"]]
                self.assertEqual(rows, sorted(rows))
                self.assertEqual(len(set(rows)), 20)
                self.assert_monotonic(down, "down")
                self.assertTrue(all(f["visible"] for f in down["frames"] if f["title"]))
                self.assertTrue(down["finalVisible"])
                up = self.hold(page, ["up"] * 20)
                self.assert_monotonic(up, "up")
                self.assertEqual(up["finalY"], 0)


if __name__ == "__main__":
    unittest.main()
