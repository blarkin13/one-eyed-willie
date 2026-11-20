"""The music player can be stopped and closed, and never hides the end of the page."""
import unittest

from tests import test_mobile_home_browser as base
from tests.test_android_app_shell_browser import APP_SCRIPT


@unittest.skipUnless(base.sync_playwright and base.CHROME, "Playwright and Chrome required")
class MusicPlayerCloseTest(base.MobileHomeLayoutTest):
    def test_phone_has_no_document_sideways_scroll_and_dock_is_visible(self): pass

    def open_music(self, app):
        context = self.browser.new_context(viewport={"width": 412, "height": 860}, is_mobile=True, has_touch=True)
        self.addCleanup(context.close)
        if app:
            context.add_init_script(APP_SCRIPT)
        page = context.new_page()
        # The test server has no music library; serve the page itself.
        html = (base.Path(__file__).resolve().parents[1] / "server/music.html").read_text()
        page.route(f"http://127.0.0.1:{self.port}/music", lambda r: r.fulfill(body=html, content_type="text/html"))
        page.route("**/api/music/catalog", lambda r: r.fulfill(json={"tracks": []}))
        page.route("**/api/music/tracks/**", lambda r: r.fulfill(status=404, body=""))
        page.goto(f"http://127.0.0.1:{self.port}/music")
        page.wait_for_function("typeof playList === 'function'")
        page.evaluate("playList([{id: 1, title: 'The Home Fire', artist: 'Louis Armstrong', album: 'What a Wonderful World'}], 0)")
        page.wait_for_selector("#player:not([hidden])")
        page.wait_for_timeout(300)
        return page

    def test_close_stops_and_hides_the_player(self):
        for app in (False, True):
            with self.subTest(app=app):
                page = self.open_music(app)
                player_h = page.eval_on_selector("#player", "p => p.offsetHeight")
                pad = page.eval_on_selector(".workspace>.content", "c => parseFloat(getComputedStyle(c).paddingBottom)")
                self.assertGreaterEqual(pad, player_h, "the end of the page can scroll above the player")
                page.tap("#close-player")
                self.assertTrue(page.eval_on_selector("#player", "p => p.hidden"))
                self.assertTrue(page.evaluate("document.getElementById('audio').paused"))
                self.assertFalse(page.evaluate("document.getElementById('audio').getAttribute('src')"))
                page.wait_for_timeout(200)
                self.assertEqual(page.evaluate("document.body.style.getPropertyValue('--player-space')"), "0px")
                # Playing something again brings it back.
                page.evaluate("playList([{id: 2, title: 'Again', artist: 'A', album: 'B'}], 0)")
                self.assertFalse(page.eval_on_selector("#player", "p => p.hidden"))


if __name__ == "__main__":
    unittest.main()
