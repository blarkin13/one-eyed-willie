"""The music player can be stopped and closed, and never hides the end of the page."""
import io
import json
import unittest

from PIL import Image

from tests import test_mobile_home_browser as base
from tests.test_android_app_shell_browser import APP_SCRIPT


@unittest.skipUnless(base.sync_playwright and base.CHROME, "Playwright and Chrome required")
class MusicPlayerCloseTest(base.MobileHomeLayoutTest):
    def test_phone_has_no_document_sideways_scroll_and_dock_is_visible(self): pass

    def open_music(self, app, viewport=None, details=None, prompts=None):
        mobile = viewport is None
        context = self.browser.new_context(viewport=viewport or {"width": 412, "height": 860},
                                           is_mobile=mobile, has_touch=mobile)
        self.addCleanup(context.close)
        if app:
            context.add_init_script(APP_SCRIPT)
        page = context.new_page()
        # The test server has no music library; serve the page itself.
        html = (base.Path(__file__).resolve().parents[1] / "server/music.html").read_text()
        page.route(f"http://127.0.0.1:{self.port}/music", lambda r: r.fulfill(body=html, content_type="text/html"))
        page.route("**/api/music/catalog", lambda r: r.fulfill(json={"tracks": []}))
        art = io.BytesIO()
        Image.new("RGB", (300, 300), (200, 40, 60)).save(art, "PNG")
        page.route("**/api/music/tracks/**", lambda r: r.fulfill(json=details or {})
                   if r.request.url.endswith("/details") else
                   r.fulfill(body=art.getvalue(), content_type="image/png") if r.request.url.endswith("/art")
                   else r.fulfill(status=404, body=""))
        if prompts is not None:
            page.on("dialog", lambda d: (prompts.append(d.message), d.accept("ACK")))
        page.goto(f"http://127.0.0.1:{self.port}/music")
        page.wait_for_function("typeof playList === 'function'")
        page.evaluate("playList([{id: 1, title: 'The Home Fire', artist: 'Louis Armstrong', album: 'What a Wonderful World',"
                      " year: 1970, genre: 'Jazz', track_number: 3, duration: 197}], 0)")
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


    LYRICS = {"format": "FLAC", "bit_depth": 16, "sample_rate": 44100, "channels": 2, "bitrate_kbps": 912,
              "composer": "Bob Thiele", "lyrics": {"source": "lrc", "plain": "a\nb\nc",
              "synced": [{"time": 0, "text": "First line"}, {"time": 4, "text": "Second line"},
                         {"time": 8, "text": "Third line"}]}}

    def test_full_screen_player_with_details_and_synced_lyrics(self):
        prompts = []
        page = self.open_music(True, details=self.LYRICS, prompts=prompts)
        page.tap("#max-player")
        page.wait_for_selector("#player.max .pf-facts span")
        self.assertIn("oewtv:shell:player:1", prompts, "the phone app hides its tabs and bars")
        facts = page.eval_on_selector_all(".pf-facts span", "s => s.map(x => x.textContent)")
        self.assertEqual(facts, ["Track 3", "Jazz", "3:17", "FLAC", "16-bit / 44.1 kHz", "912 kbps", "Stereo"])
        self.assertEqual(page.text_content(".pf-title"), "The Home Fire")
        self.assertIn("Bob Thiele", page.text_content(".pf-credits"))
        page.screenshot(path="/tmp/music-full-info.png")
        page.tap(".pf-tabs button[data-tab='lyrics']")
        page.evaluate("Object.defineProperty(document.getElementById('audio'), 'currentTime', {get: () => 5, set() {}, configurable: true});"
                      "document.getElementById('audio').dispatchEvent(new Event('timeupdate'))")
        self.assertEqual(page.text_content(".pf-lyrics p.now"), "Second line")
        page.screenshot(path="/tmp/music-full-lyrics.png")
        # Back in the phone app minimises (the app calls yarrShellBack).
        page.evaluate("window.yarrShellBack()")
        self.assertFalse(page.eval_on_selector("#player", "p => p.classList.contains('max')"))
        self.assertIn("oewtv:shell:player:0", prompts)
        self.assertFalse(page.eval_on_selector("#player", "p => p.hidden"), "minimising keeps the music playing")

    def test_no_lyrics_message_and_close_from_full_screen(self):
        page = self.open_music(False, viewport={"width": 1366, "height": 800}, details={"format": "MP3", "lyrics": None})
        page.click("#max-player")
        page.wait_for_selector("#player.max .pf-lyrics .pf-none")
        self.assertIn("No lyrics", page.text_content(".pf-lyrics"))
        self.assertTrue(page.is_visible(".pf-panel[data-panel='lyrics']"), "wide screens show lyrics beside the details")
        page.screenshot(path="/tmp/music-full-desktop.png")
        page.keyboard.press("Escape")
        self.assertFalse(page.eval_on_selector("#player", "p => p.classList.contains('max')"))
        page.click("#max-player")
        page.click("#pf-close")
        self.assertTrue(page.eval_on_selector("#player", "p => p.hidden"))
        self.assertFalse(page.eval_on_selector("#player", "p => p.classList.contains('max')"))


if __name__ == "__main__":
    unittest.main()
