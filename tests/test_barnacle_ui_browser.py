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


import base64
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")


@unittest.skipUnless(sync_playwright and CHROME, "Playwright and Chrome required")
class ServerSwitcherTest(base.MobileHomeLayoutTest):
    """The switch-server icon: only with more than one server; opens a list."""
    def test_phone_has_no_document_sideways_scroll_and_dock_is_visible(self): pass

    def app_page(self, count):
        context = self.browser.new_context(viewport={"width": 1280, "height": 800},
                                           user_agent="Mozilla/5.0 (Linux; Android 14) Chrome/131 OneEyedWillieTV/1")
        self.addCleanup(context.close)
        page = context.new_page()
        prompts = []
        def answer(dialog):
            prompts.append(dialog.message)
            dialog.accept(str(count) if dialog.message == "oewtv:servers:count" else "ACK")
        page.on("dialog", answer)
        page.route("**/api/home", lambda r: r.fulfill(json=DATA))
        page.goto(f"http://127.0.0.1:{self.port}/")
        page.wait_for_timeout(1000)
        return page, prompts

    def test_icon_only_with_more_than_one_server_in_the_apps(self):
        page, _ = self.app_page(1)
        self.assertFalse(page.query_selector('.side-nav a[data-nav-id="servers"]'))
        page, prompts = self.app_page(2)
        order = page.eval_on_selector_all(".side-nav a[data-nav-id]", "a=>a.map(x=>x.dataset.navId)")
        self.assertEqual(order[-2:], ["servers", "settings"])
        # On the TV the sidebar is off-screen until the remote moves focus into it.
        page.focus('.side-nav a[data-nav-id="servers"]')
        page.keyboard.press("Enter")
        page.wait_for_timeout(200)
        self.assertIn("oewtv:servers:pick", prompts)
        self.assertEqual(page.evaluate("location.hash"), "", "no navigation")

    def test_window_at_app_yarr_media(self):
        context = self.browser.new_context(viewport={"width": 1280, "height": 800})
        self.addCleanup(context.close)
        page = context.new_page()
        servers = {"current": "a", "servers": [
            {"id": "a", "name": "Basement", "role": "owner", "owner_name": "", "online": True, "icon_url": None},
            {"id": "b", "name": "Gazorpazorp", "role": "barnacle", "owner_name": "Brian", "online": False,
             "icon_url": "/__yarr/server-icons/b.png?v=1"}]}
        local = f"http://127.0.0.1:{self.port}"
        def proxy(route):
            url = route.request.url
            if "/__yarr/server-icons/" in url:
                return route.fulfill(body=PNG, content_type="image/png")
            if "/__yarr/servers" in url:
                return route.fulfill(json=servers)
            if "/__yarr/" in url:
                return route.fulfill(body="switched", content_type="text/plain")
            if url.rstrip("/").endswith("/api/home"):
                return route.fulfill(json=DATA)
            route.fulfill(response=route.fetch(url=url.replace("https://app.yarr.media", local)))
        page.route("https://app.yarr.media/**", proxy)
        page.goto("https://app.yarr.media/")
        page.wait_for_selector('.side-nav a[data-nav-id="servers"]', timeout=10000)
        page.click('.side-nav a[data-nav-id="servers"]')
        rows = page.eval_on_selector_all(".yarr-server-window button.server", "b=>b.map(x=>x.innerText.replace(/\\s+/g,' ').trim())")
        self.assertEqual(rows[0], "Basement Yours ✓")
        self.assertEqual(rows[1], "Gazorpazorp Shared by Brian · offline")
        self.assertEqual(page.get_attribute(".yarr-server-window button.server:nth-of-type(2) img", "src"), "/__yarr/server-icons/b.png?v=1")
        page.screenshot(path="/tmp/server-switcher.png")
        with page.expect_navigation():
            page.click(".yarr-server-window button.server:nth-of-type(2)")
        self.assertEqual(page.url, "https://app.yarr.media/__yarr/use?server=b")
