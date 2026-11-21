"""The phone app's styling on the real Home page (what AppShell.kt injects).

Loads Home in a phone-sized browser with the exact document-start script
from google-tv/phone/.../AppShell.kt and checks the app look: no web
navigation or floating logo, compact captions, shelves that start at a
poster edge, no sideways page scroll. The plain mobile website is untouched.
"""
import re
import unittest
from pathlib import Path

import tests.test_mobile_home_browser as base
from tests.test_mobile_home_browser import CHROME, DATA, sync_playwright, make_item

ROOT = Path(__file__).resolve().parents[1]
SHELL = (ROOT / "google-tv/phone/src/main/java/studio/oneeyedwillie/tv/AppShell.kt").read_text()
APP_CSS = re.search(r'APP_CSS = """\n(.*?)""".trimIndent\(\)', SHELL, re.S).group(1).replace("\n", "")
APP_JS = re.search(r'APP_JS = """\n(.*?)"""', SHELL, re.S).group(1)
APP_SCRIPT = """(function(){var css=%s;function add(){var r=document.documentElement;if(!r)return false;
 r.classList.add('yarr-app');var s=document.createElement('style');s.id='yarr-app-style';s.textContent=css;
 (document.head||r).appendChild(s);return true}
 if(!add())new MutationObserver(function(m,o){if(add())o.disconnect()}).observe(document,{childList:true,subtree:true});})();""" % (
    __import__("json").dumps(APP_CSS)) + APP_JS

DATA_TV = dict(DATA, continue_watching=[dict(make_item(i), title=f"Continue Show {i}") for i in range(6)])


@unittest.skipUnless(sync_playwright and CHROME, "Playwright and Chrome required")
class AppShellStylingTest(base.MobileHomeLayoutTest):
    def open_app(self, width, app=True):
        context = self.browser.new_context(viewport={"width": width, "height": 800},
                                           is_mobile=True, has_touch=True, device_scale_factor=2)
        self.addCleanup(context.close)
        if app:
            context.add_init_script(APP_SCRIPT)
        page = context.new_page()
        page.route("**/api/home", lambda route: route.fulfill(json=DATA_TV))
        page.route("**/api/home/revision", lambda route: route.fulfill(json={"revision": 1}))
        page.route("**/api/movies/details*", lambda route: route.fulfill(json={
            "year": 2026, "network": "Network", "overview": "A brief description."}))
        page.goto(f"http://127.0.0.1:{self.port}/")
        page.wait_for_selector("#recent-movies .shelf-track .tile-button", timeout=20000)
        page.wait_for_timeout(400)
        return page

    # The inherited website tests run once in the parent class; skip them here.
    def test_phone_has_no_document_sideways_scroll_and_dock_is_visible(self): pass

    def test_app_hides_the_web_navigation_and_keeps_layout(self):
        for width in (360, 411):
            with self.subTest(width=width):
                page = self.open_app(width)
                data = page.evaluate("""() => {
                  const sidebar=document.querySelector('.sidebar');
                  const title=document.querySelector('#recent-movies .shelf-track .tile h3');
                  const meta=document.querySelector('#recent-movies .shelf-track .tile-meta');
                  return {app:document.documentElement.classList.contains('yarr-app'),
                    sidebar:getComputedStyle(sidebar).display,
                    width:document.documentElement.scrollWidth,
                    titleMin:getComputedStyle(title).minHeight, metaMin:getComputedStyle(meta).minHeight,
                    snap:getComputedStyle(document.querySelector('#recent-movies .shelf-track')).scrollSnapType,
                    select:getComputedStyle(document.body).userSelect};
                }""")
                self.assertTrue(data["app"])
                self.assertEqual(data["sidebar"], "none")
                self.assertLessEqual(data["width"], width)
                self.assertEqual(data["titleMin"], "0px")
                self.assertEqual(data["metaMin"], "0px")
                self.assertEqual(data["snap"], "none")
                self.assertEqual(data["select"], "none")
                page.screenshot(path=f"/tmp/app-shell-{width}.png")

    def test_shelf_scrolls_freely_without_snapping(self):
        # Snapping made swipes feel sticky on the phone; rows scroll freely, like Plex.
        page = self.open_app(411)
        track = "#recent-movies .shelf-track"
        self.assertEqual(page.eval_on_selector(track, "t => getComputedStyle(t).scrollSnapType"), "none")
        page.evaluate(f"document.querySelector('{track}').scrollLeft=70")
        page.wait_for_timeout(700)
        self.assertEqual(page.eval_on_selector(track, "t => Math.round(t.scrollLeft)"), 70)

    def test_swiping_rows_does_no_hidden_feature_work_in_the_app(self):
        # The feature panel is hidden in the app, so neither loading nor swiping fills it in.
        for app in (True, False):
            with self.subTest(app=app):
                page = self.open_app(411, app=app)
                for x in (120, 260, 420):
                    page.evaluate(f"document.querySelector('#recent-movies .shelf-track').scrollLeft={x}")
                    page.wait_for_timeout(150)
                page.dispatch_event("#recent-movies .shelf-track .tile-button >> nth=2", "pointerover")
                page.wait_for_timeout(400)
                filled = page.evaluate("[...document.querySelectorAll('.home-feature-kicker')].some(e => e.textContent.trim())")
                self.assertEqual(filled, not app)

    def test_home_is_poster_rows_like_plex(self):
        page = self.open_app(411)
        data = page.evaluate("""() => ({
          features:[...document.querySelectorAll('.home-feature')].filter(e=>getComputedStyle(e).display!=='none').length,
          backdrop:[...document.querySelectorAll('.willie-hover-backdrop')].filter(e=>getComputedStyle(e).display!=='none').length,
          bar:document.querySelector('.yarr-app-bar strong')?.textContent,
          link:document.querySelector('#movies-heading').closest('a')?.getAttribute('href'),
          chevron:!!document.querySelector('#movies-heading').closest('a')?.querySelector('svg'),
          watermark:getComputedStyle(document.querySelector('.shelf-track'),'::before').display,
          perRow:(() => {const t=document.querySelector('#recent-movies .shelf-track .tile');return 411/t.getBoundingClientRect().width;})()
        })""")
        self.assertEqual(data["features"], 0)
        self.assertEqual(data["backdrop"], 0)
        self.assertEqual(data["bar"], "Yarr Media")
        self.assertEqual(data["link"], "/movies")
        self.assertTrue(data["chevron"])
        self.assertEqual(data["watermark"], "none")
        self.assertGreater(data["perRow"], 3.0)
        self.assertLess(data["perRow"], 3.6)

    def test_plain_mobile_website_is_unchanged(self):
        page = self.open_app(411, app=False)
        data = page.evaluate("""() => ({app:document.documentElement.classList.contains('yarr-app'),
          sidebar:getComputedStyle(document.querySelector('.sidebar')).display})""")
        self.assertFalse(data["app"])
        self.assertNotEqual(data["sidebar"], "none")
        page.screenshot(path="/tmp/web-411.png")


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(sync_playwright and CHROME, "Playwright and Chrome required")
class AppShellLibraryTest(base.MobileHomeLayoutTest):
    """Libraries in the app: a plain three-column poster grid, no decorative header."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        import sqlite3, urllib.request
        urllib.request.urlopen(f"http://127.0.0.1:{cls.port}/api/libraries", timeout=10).read()
        db = sqlite3.connect(Path(cls.tmp.name) / "data/library.sqlite3")
        (Path(cls.tmp.name) / "media/Movies").mkdir()
        db.execute("INSERT INTO libraries(id,name,kind,path) VALUES(1,'Movies','movies',?)", (str(Path(cls.tmp.name) / "media/Movies"),))
        db.commit(); db.close()

    def test_phone_has_no_document_sideways_scroll_and_dock_is_visible(self): pass

    def test_library_is_a_three_column_grid(self):
        context = self.browser.new_context(viewport={"width": 411, "height": 800}, is_mobile=True, has_touch=True)
        self.addCleanup(context.close)
        context.add_init_script(APP_SCRIPT)
        page = context.new_page()
        items = [dict(make_item(i), title=f"Movie {i}") for i in range(9)]
        page.route("**/api/catalog/all*", lambda r: r.fulfill(json=dict(total=9, items=items, genres=[], revision=1)))
        page.route("**/api/movies/posters", lambda r: r.fulfill(json={}))
        page.route("**/api/movies/details*", lambda r: r.fulfill(json={}))
        page.route("https://opentdb.com/**", lambda r: r.fulfill(json={"results": []}))
        page.goto(f"http://127.0.0.1:{self.port}/movies")
        page.wait_for_selector("#items .tile", timeout=20000)
        data = page.evaluate("""() => {
          const tiles=[...document.querySelectorAll('#items .tile')].slice(0,4).map(t=>t.getBoundingClientRect());
          const hidden=s=>{const e=document.querySelector(s);return !e||getComputedStyle(e).display==='none'};
          return {rowTops:tiles.map(r=>Math.round(r.top)), lefts:tiles.map(r=>Math.round(r.left)),
            right:Math.round(tiles[2].right), width:document.documentElement.scrollWidth,
            title:document.querySelector('#page-title').textContent,
            art:hidden('.library-header-art-frame'), trivia:hidden('.library-trivia'),
            alpha:hidden('.alpha-nav'), refresh:hidden('#refresh-metadata')};
        }""")
        self.assertEqual(len(set(data["rowTops"][:3])), 1, "three posters on the first row")
        self.assertGreater(data["rowTops"][3], data["rowTops"][0])
        self.assertEqual(data["lefts"][0], 16)
        self.assertGreaterEqual(data["right"], 411 - 17)
        self.assertLessEqual(data["width"], 411)
        self.assertEqual(data["title"], "Movies")
        for key in ("art", "trivia", "alpha", "refresh"):
            self.assertTrue(data[key], key)
