"""The web player on a phone: tap to show/hide controls, playback info that goes away,
and the phone app hiding its tabs while a video is open."""
import unittest

from tests import test_web_player_quality_browser as base
from tests.test_android_app_shell_browser import APP_SCRIPT

PHONE = {"width": 412, "height": 860}


@unittest.skipUnless(base.sync_playwright and base.CHROME, "Playwright and Chrome are required")
class PhonePlayerTests(unittest.TestCase):
    setUpClass = classmethod(base.WebPlayerQualityBrowserTests.setUpClass.__func__)
    tearDownClass = classmethod(base.WebPlayerQualityBrowserTests.tearDownClass.__func__)
    open_player = base.WebPlayerQualityBrowserTests.open_player

    def hidden(self, page):
        return page.evaluate("document.querySelector('.willie-player').classList.contains('willie-chrome-hidden')")

    def test_tap_puts_the_controls_away_and_brings_them_back_without_pausing(self):
        page, _, _ = self.open_player(viewport=PHONE, touch=True)
        page.wait_for_selector(".willie-player video")
        page.wait_for_timeout(300)
        page.evaluate("""() => { window.__calls = [];
          for (const name of ['play', 'pause']) { const real = HTMLMediaElement.prototype[name];
            HTMLMediaElement.prototype[name] = function () { window.__calls.push(name); return real.apply(this, arguments); }; } }""")
        self.assertFalse(self.hidden(page))
        page.tap(".willie-player video", position={"x": 200, "y": 420})
        page.wait_for_timeout(500)
        self.assertTrue(self.hidden(page), "a tap with the controls showing puts them away")
        self.assertEqual(page.evaluate("getComputedStyle(document.querySelector('.willie-bottom')).opacity"), "0")
        page.tap(".willie-player video", position={"x": 200, "y": 420})
        page.wait_for_timeout(100)
        self.assertFalse(self.hidden(page), "a tap with them hidden brings them back")
        self.assertEqual(page.evaluate("window.__calls"), [], "tapping never pauses or plays")

    def test_mouse_click_still_pauses_on_a_computer(self):
        page, _, _ = self.open_player()
        page.wait_for_selector(".willie-player video")
        page.wait_for_timeout(300)
        page.evaluate("""() => { window.__calls = [];
          HTMLMediaElement.prototype.play = function () { window.__calls.push('play'); return Promise.resolve(); };
          HTMLMediaElement.prototype.pause = function () { window.__calls.push('pause'); }; }""")
        page.click(".willie-player video", position={"x": 640, "y": 360})
        self.assertEqual(len(page.evaluate("window.__calls")), 1, "a click plays or pauses as before")

    def test_playback_info_toggles_closes_on_tap_and_times_out(self):
        page, _, _ = self.open_player(viewport=PHONE, touch=True)
        info = "button[aria-label='Playback diagnostics']"
        page.wait_for_selector(info)
        text = lambda: page.text_content(".willie-info")
        page.tap(info)
        self.assertIn("Client GPU decoding", text())
        page.tap(info)
        self.assertEqual(text(), "", "the info button closes it again")
        page.tap(info)
        page.tap(".willie-info")
        self.assertEqual(text(), "", "tapping the box closes it")
        page.tap(info)
        page.wait_for_timeout(8400)
        self.assertEqual(text(), "", "it goes away on its own")

    def test_phone_app_is_told_when_the_player_opens_and_closes(self):
        prompts = []

        def answer(dialog):
            prompts.append(dialog.message)
            dialog.accept("ACK")

        page, _, _ = self.open_player(viewport=PHONE, touch=True, init_script=APP_SCRIPT,
                                      setup=lambda p: p.on("dialog", answer))
        page.wait_for_selector(".willie-player")
        page.wait_for_timeout(300)
        self.assertEqual([m for m in prompts if m.startswith("oewtv:shell:")], ["oewtv:shell:player:1"])
        page.evaluate("document.querySelector('.willie-player').remove()")
        page.wait_for_timeout(200)
        self.assertEqual([m for m in prompts if m.startswith("oewtv:shell:")], ["oewtv:shell:player:1", "oewtv:shell:player:0"])


if __name__ == "__main__":
    unittest.main()
