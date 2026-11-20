"""What a barnacle sees in the web interface: library links only, no owner tools."""
import unittest

import tests.test_mobile_home_browser as base
from tests.test_mobile_home_browser import CHROME, DATA, sync_playwright

BARNACLE = {"role": "barnacle", "name": "Friend", "libraries": [1]}


@unittest.skipUnless(sync_playwright and CHROME, "Playwright and Chrome required")
class BarnacleInterfaceTest(base.MobileHomeLayoutTest):
    def test_phone_has_no_document_sideways_scroll_and_dock_is_visible(self): pass

    def open(self, path, viewer, user_agent=None):
        context = self.browser.new_context(viewport={"width": 1280, "height": 800}, user_agent=user_agent)
        self.addCleanup(context.close)
        page = context.new_page()
        page.route("**/api/viewer", lambda r: r.fulfill(json=viewer))
        page.route("**/api/home", lambda r: r.fulfill(json=DATA))
        page.route("**/api/home/revision", lambda r: r.fulfill(json={"revision": 1}))
        page.goto(f"http://127.0.0.1:{self.port}{path}")
        page.wait_for_timeout(1200)
        return page

    def nav_ids(self, page):
        return page.evaluate("[...document.querySelectorAll('.side-nav a[data-nav-id]')].map(a=>a.dataset.navId)")

    def test_barnacle_menu_has_only_libraries(self):
        page = self.open("/", BARNACLE)
        ids = self.nav_ids(page)
        self.assertIn("home", ids)
        self.assertNotIn("settings", ids)
        self.assertNotIn("connections", ids)
        self.assertTrue(page.evaluate("document.documentElement.classList.contains('yarr-barnacle')"))
        owner = self.open("/", {"role": "owner", "name": "", "libraries": None})
        self.assertIn("settings", self.nav_ids(owner))
        self.assertIn("connections", self.nav_ids(owner))

    def test_barnacle_keeps_settings_in_the_apps_for_their_connection(self):
        tv = "Mozilla/5.0 (Linux; Android 14) Chrome/131 OneEyedWillieTV/1"
        phone = "Mozilla/5.0 (Linux; Android 15) Chrome/131 Mobile YarrMediaAndroid/1"
        for ua in (tv, phone):
            with self.subTest(ua=ua[-20:]):
                self.assertIn("settings", self.nav_ids(self.open("/", BARNACLE, ua)))
        hub = self.open("/settings", BARNACLE, phone)
        tiles = hub.evaluate("[...document.querySelectorAll('.settings-grid .settings-tile')].map(t=>t.textContent.trim())")
        self.assertEqual(len(tiles), 1)
        self.assertIn("Connection", tiles[0])
        browser_hub = self.open("/settings", BARNACLE)
        self.assertIn("owner of this server manages", browser_hub.content())
        tv_page = self.open("/settings", BARNACLE, tv)
        sections = tv_page.evaluate("document.querySelectorAll('.settings-section').length")
        self.assertEqual(sections, 1)
        self.assertTrue(tv_page.evaluate("!!document.getElementById('tv-server-connection')"))


if __name__ == "__main__":
    unittest.main()
