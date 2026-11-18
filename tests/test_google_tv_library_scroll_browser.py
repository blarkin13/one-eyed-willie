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
        data = base / "data"
        data.mkdir()
        # Every writable path defaults to /data (the Docker volume). Point them
        # all into the temp folder: CI runners cannot create /data, and tests
        # must never touch a developer's real data directory.
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
        with open(cls.server_log, "wb") as log:
            cls.server = subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "server.main:app",
                 "--port", str(cls.port), "--log-level", "warning"],
                cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
        cls.origin = "http://127.0.0.1:%d" % cls.port
        for _ in range(100):
            try:
                call(cls.origin + "/health")
                break
            except Exception:
                time.sleep(0.2)
        else:
            # Say why: a silent "did not start" hid a CI-only failure for days.
            output = cls.server_log.read_text(errors="replace")[-3000:]
            code = cls.server.poll()
            cls.server.kill()
            raise RuntimeError("test server did not start (exit code %s):\n%s" % (code, output))
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

    def open_tv_settings(self):
        """Open TV-only Settings with the native subtitle bridge mocked."""
        context = self.browser.new_context(
            viewport={"width": 960, "height": 540}, user_agent=TV_UA)
        self.addCleanup(context.close)
        context.add_init_script("""window.prompt = (message, payload) => {
          if(message==='oewtv:subtitles:get')return JSON.stringify({
            enabled:false,language:'en',background:'none',
            size:'normal',color:'white',outline:true
          });
          if(message==='oewtv:subtitles:set'){
            window.__lastTvSubtitleSave=JSON.parse(payload);
            return 'ACK';
          }
          return null;
        };""")
        page = context.new_page()
        page.goto(self.origin + "/settings", wait_until="load")
        page.wait_for_function(
            "() => document.querySelector('.tv-playback-settings') !== null")
        page.evaluate(self.script)
        page.wait_for_function("typeof window.__willieTvMove==='function'")
        page.wait_for_function("sharedPlayback!==null", timeout=10000)
        return page

    def test_tv_settings_uses_linear_remote_focus_and_clear_focus_ring(self):
        page = self.open_tv_settings()
        page.wait_for_function(
            "document.activeElement?.id==='tv-subtitles-on'", timeout=10000)
        expected = [
            "tv-language-button",
            "tv-subtitle-background",
            "tv-subtitle-size",
            "tv-subtitle-color",
            "tv-subtitle-outline",
        ]
        for control in expected:
            page.evaluate("window.__willieTvMove('down')")
            self.assertEqual(page.evaluate("document.activeElement?.id"), control)
            style = page.evaluate("""() => {
              const node=document.activeElement,s=getComputedStyle(node);
              return {width:s.outlineWidth,style:s.outlineStyle,
                help:document.getElementById('tv-focused-control').textContent};
            }""")
            self.assertEqual(style["style"], "solid")
            self.assertGreaterEqual(float(style["width"].replace("px","")),2)
            self.assertTrue(style["help"])
        page.evaluate("window.__willieTvMove('up')")
        self.assertEqual(page.evaluate("document.activeElement?.id"),"tv-subtitle-color")

    def test_tv_settings_auto_saves_and_confirms_while_scrolled(self):
        page = self.open_tv_settings()
        # Native prompt/ACK bridge verifies on-device subtitles saved without
        # needing the old Save button at the bottom of the section.
        page.evaluate("document.getElementById('tv-subtitles-on').focus()")
        page.evaluate("window.__willieTvSelect()")
        self.assertTrue(page.evaluate("window.__lastTvSubtitleSave?.enabled"))
        self.assertTrue(page.evaluate(
            "document.getElementById('tv-subtitle-status').textContent.includes('saved')"))

        # Playback auto-save persists to the real isolated test server.
        before = call(self.origin+"/api/settings/playback")["auto_play_next"]
        page.evaluate("document.getElementById('tv-auto-next').focus()")
        page.evaluate("window.__willieTvSelect()")
        page.wait_for_function("""() =>
          document.getElementById('tv-playback-status').textContent.includes('saved')""")
        self.assertEqual(call(self.origin+"/api/settings/playback")["auto_play_next"],
                         not before)
        self.assertTrue(page.evaluate(
            "!document.getElementById('tv-save-toast').hidden"))
        self.assertEqual(page.evaluate("document.activeElement?.id"),"tv-auto-next")
        self.assertIn("OK to toggle",page.evaluate(
            "document.getElementById('tv-focused-control').textContent"))

        # Color choices also save without an extra trip to a separate button,
        # and a dialog keeps remote focus inside until the selection is made.
        page.evaluate("document.getElementById('tv-color-button').focus()")
        page.evaluate("window.__willieTvSelect()")
        self.assertTrue(page.evaluate(
            "document.getElementById('tv-color-dialog').open"))
        page.evaluate("window.__willieTvMove('down')")
        color = page.evaluate("document.activeElement?.dataset.color")
        page.evaluate("window.__willieTvSelect()")
        page.wait_for_function("""() =>
          document.getElementById('tv-color-status').textContent.includes('saved')""")
        self.assertEqual(call(self.origin+"/api/settings/tv-appearance")["selection_color"],
                         color)
        self.assertEqual(page.evaluate("document.activeElement?.id"),"tv-color-button")

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

    def test_sort_and_filter_choice_down_returns_to_posters(self):
        """A selected Sort/Filter option must not trap the viewer in toolbar."""
        page = self.open_library()
        for name in ("sort", "genre"):
            with self.subTest(menu=name):
                page.evaluate("""name => document.getElementById(name+'-toggle')
                    .focus({preventScroll:true})""", name)
                page.evaluate("window.__willieTvSelect()")
                self.assertTrue(page.evaluate(
                    "name => !document.getElementById(name+'-menu').hidden", name))
                self.assertTrue(page.evaluate(
                    "name => document.activeElement?.closest('#'+name+'-menu') != null",
                    name))
                if name == "sort":
                    # Choose another sort option inside the popup.
                    page.evaluate("window.__willieTvMove('down')")
                    self.assertEqual(page.evaluate(
                        "document.activeElement?.dataset?.menuValue"), "added")
                page.evaluate("window.__willieTvSelect()")
                self.assertTrue(page.evaluate(
                    "name => document.getElementById(name+'-menu').hidden", name))
                self.assertEqual(page.evaluate("document.activeElement?.id"),
                                 name+"-toggle")
                # This is the reported bug: DOWN after choosing should leave
                # Sort/Filter and select the first poster, not reopen a menu.
                page.evaluate("window.__willieTvMove('down')")
                # Sort/Filter fetch may finish *after* the first Down. Verify
                # the new grid preserves focus even after that asynchronous
                # rebuild has completed, not just before it.
                page.wait_for_function("!loading", timeout=30000)
                self.assertTrue(page.evaluate(
                    "document.activeElement?.matches?.('#items .tile-button')"))
                self.assertTrue(page.evaluate(
                    "name => document.getElementById(name+'-menu').hidden", name))

    def test_sort_same_count_rebuilds_cached_poster_grid_navigation(self):
        """Changing sort replaces posters without changing their count.

        The TV row cache must stop referencing the removed poster elements;
        this is why Filter (new count) worked while Sort (same count) did not.
        """
        page = self.open_library()
        page.evaluate("window.__willieTvMove('down')")  # prime row cache
        original_count = page.evaluate("document.querySelectorAll('#items .tile-button').length")
        for value in ("added", "length", "rating", "title"):
            with self.subTest(sort=value):
                page.evaluate("""value => {
                    document.getElementById('sort-toggle').focus({preventScroll:true});
                    document.getElementById('sort-toggle').click();
                    const option=[...document.querySelectorAll('#sort-menu .catalog-tool-option')]
                      .find(x => x.dataset.menuValue === value);
                    if(!option)throw Error('Missing sort '+value);
                    option.focus({preventScroll:true});
                    window.__willieTvSelect();
                }""", value)
                page.wait_for_function("!loading", timeout=30000)
                page.wait_for_function(
                    "document.querySelectorAll('#items .tile-button').length >= %d"
                    % original_count, timeout=30000)
                self.assertEqual(page.evaluate("document.querySelectorAll('#items .tile-button').length"),
                                 original_count)
                self.assertEqual(page.evaluate("document.activeElement?.id"), "sort-toggle")
                page.evaluate("window.__willieTvMove('down')")
                self.assertTrue(page.evaluate(
                    "document.activeElement?.matches?.('#items .tile-button')"),
                    "Down after sorting %s should focus a real poster" % value)
                self.assertTrue(page.evaluate("document.activeElement?.isConnected"))
                # Prime the row cache again so the next same-count replacement
                # must invalidate it, rather than using an unpopulated cache.
                page.evaluate("window.__willieTvMove('down')")

    def test_filter_last_option_down_exits_to_posters(self):
        page = self.open_library()
        page.evaluate("""() => {
          const select=document.getElementById('genre');
          for(let i=0;i<25;i++)select.add(new Option('Genre '+i, 'genre-'+i));
          document.getElementById('genre-toggle').focus({preventScroll:true});
        }""")
        page.evaluate("window.__willieTvSelect()")
        self.assertTrue(page.evaluate("!document.getElementById('genre-menu').hidden"))
        page.evaluate("() => {for(let i=0;i<25;i++)window.__willieTvMove('down')}")
        state=page.evaluate("""() => {
          const menu=document.getElementById('genre-menu'),item=document.activeElement;
          const r=item.getBoundingClientRect(),bounds=menu.getBoundingClientRect();
          return {value:item.dataset.menuValue, scroll:menu.scrollTop,
            visible:r.top>=bounds.top-2&&r.bottom<=bounds.bottom+2};
        }""")
        self.assertEqual(state["value"], "genre-24")
        self.assertGreater(state["scroll"], 0)
        self.assertTrue(state["visible"])
        page.evaluate("window.__willieTvMove('down')")
        self.assertTrue(page.evaluate("document.getElementById('genre-menu').hidden"))
        self.assertTrue(page.evaluate(
            "document.activeElement?.matches?.('#items .tile-button')"))

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

    def refresh_with(self, page, change):
        """Run the 15s live-refresh path against an altered catalog response."""
        def handler(route):
            response = route.fetch()
            data = response.json()
            change(data)
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps(data))
        page.route("**/api/catalog/all*", handler)
        try:
            return page.evaluate("""async () => {
              const tiles = [...document.querySelectorAll('#items .tile')];
              tiles.forEach((tile, index) => { tile.__kept = index; });
              const focus = document.activeElement;
              const y = document.scrollingElement.scrollTop;
              const started = performance.now();
              await load({preserveFocus: true}, true);
              const after = [...document.querySelectorAll('#items .tile')];
              return {
                elapsed: performance.now() - started,
                count: after.length,
                before: tiles.length,
                sameNodes: after.filter((tile, i) => tile.__kept === i).length,
                sameFocus: document.activeElement === focus,
                key: document.activeElement?.dataset?.hoverKey,
                dy: Math.abs(document.scrollingElement.scrollTop - y),
                badge: !!after[7]?.querySelector('.watched-badge'),
                meta: after[8]?.querySelector('.tile-meta')?.textContent,
                poster: !!after[9]?.querySelector('.poster-image'),
              };
            }""")
        finally:
            page.unroute("**/api/catalog/all*")

    def test_unchanged_order_refresh_patches_cards_without_rebuilding(self):
        page = self.open_library()
        self.hold(page, ["down"] * 30)

        def change(data):
            data["items"][7]["watched"] = True
            data["items"][8]["rating"] = 9.1
            data["items"][9]["poster_url"] = "/api/artwork/thumb/" + "a" * 64

        result = self.refresh_with(page, change)
        self.assertEqual(result["count"], MOVIES)
        self.assertEqual(result["sameNodes"], MOVIES, "cards were rebuilt")
        self.assertTrue(result["sameFocus"])
        self.assertEqual(result["dy"], 0)
        self.assertTrue(result["badge"], "watched badge was not applied")
        self.assertIn("9.1", result["meta"])
        self.assertTrue(result["poster"], "newly resolved poster was not applied")
        # Navigation still works from the untouched selection.
        moved = self.hold(page, ["down", "down"])
        self.assertEqual(len({s["row"] for s in moved["steps"]}), 2)

    def test_changed_list_still_rebuilds_and_keeps_deep_selection(self):
        page = self.open_library()
        self.hold(page, ["down"] * 30)

        def change(data):
            del data["items"][3]       # a title disappeared: order differs
            data["total"] -= 1

        result = self.refresh_with(page, change)
        # A rebuild is progressive: everything up to the selection exists when
        # load() returns and the remainder is appended afterwards.
        self.assertGreater(result["count"], 30)
        self.assertEqual(result["sameNodes"], 0, "list changed; must rebuild")
        self.assertIsNotNone(result["key"], "selected poster was lost")
        page.wait_for_function(
            "document.querySelectorAll('#items .tile-button').length >= %d"
            % (MOVIES - 1), timeout=30000)
        self.assertLess(page.evaluate(
            "document.scrollingElement.scrollTop"), 10 ** 6)


if __name__ == "__main__":
    unittest.main()
