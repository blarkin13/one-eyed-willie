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
APP_SCRIPT = """(function(){var css=%s;function add(){var r=document.documentElement;if(!r)return false;
 r.classList.add('yarr-app');var s=document.createElement('style');s.id='yarr-app-style';s.textContent=css;
 (document.head||r).appendChild(s);return true}
 if(!add())new MutationObserver(function(m,o){if(add())o.disconnect()}).observe(document,{childList:true,subtree:true});})();""" % (
    __import__("json").dumps(APP_CSS))

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
                self.assertIn("mandatory", data["snap"])
                self.assertEqual(data["select"], "none")
                page.screenshot(path=f"/tmp/app-shell-{width}.png")

    def test_shelf_settles_on_a_poster_edge(self):
        page = self.open_app(411)
        track = "#recent-movies .shelf-track"
        page.evaluate(f"document.querySelector('{track}').scrollLeft=70")
        page.wait_for_timeout(700)
        offset = page.evaluate(f"""() => {{
          const t=document.querySelector('{track}');const r=t.getBoundingClientRect();
          const tiles=[...t.querySelectorAll(':scope>.tile')].map(e=>e.getBoundingClientRect().left-r.left);
          return Math.min(...tiles.map(x=>Math.abs(x)));
        }}""")
        self.assertLess(offset, 6)

    def test_plain_mobile_website_is_unchanged(self):
        page = self.open_app(411, app=False)
        data = page.evaluate("""() => ({app:document.documentElement.classList.contains('yarr-app'),
          sidebar:getComputedStyle(document.querySelector('.sidebar')).display})""")
        self.assertFalse(data["app"])
        self.assertNotEqual(data["sidebar"], "none")
        page.screenshot(path="/tmp/web-411.png")


if __name__ == "__main__":
    unittest.main()
