"""Audio-track choice in the web player (real page and player.js, stubbed media APIs)."""
import json
import unittest

from tests import test_web_player_quality_browser as base

TRACKS = [
    {"id": 0, "language": "eng", "label": "English · 5.1 · AC3", "default": True},
    {"id": 1, "language": "fre", "label": "French · Stereo · AC3", "default": False},
]


def serve_tracks(tracks):
    def setup(page):
        page.route("**/api/stream/hls/audio/7", lambda route: route.fulfill(
            status=200, content_type="application/json", body=json.dumps({"tracks": tracks})))
    return setup


@unittest.skipUnless(base.sync_playwright and base.CHROME, "Playwright and Chrome are required")
class WebPlayerAudioBrowserTests(unittest.TestCase):
    setUpClass = classmethod(base.WebPlayerQualityBrowserTests.setUpClass.__func__)
    tearDownClass = classmethod(base.WebPlayerQualityBrowserTests.tearDownClass.__func__)
    open_player = base.WebPlayerQualityBrowserTests.open_player

    def open_menu(self, page):
        page.click("button[aria-label='Data use and quality']")
        page.wait_for_selector("button.willie-data-row[data-quality='480p']")

    def wait_for(self, items, count=1):
        for _ in range(60):
            if len(items) >= count:
                return
            self.page.wait_for_timeout(100)

    def test_a_single_track_shows_no_audio_choice(self):
        page, _, _ = self.open_player(setup=serve_tracks(TRACKS[:1]))
        self.open_menu(page)
        page.wait_for_timeout(300)
        self.assertEqual(page.locator(".willie-audio-row").count(), 0)

    def test_two_tracks_are_listed_with_the_default_ticked(self):
        page, _, _ = self.open_player(setup=serve_tracks(TRACKS))
        self.open_menu(page)
        page.wait_for_selector(".willie-audio-row")
        labels = page.eval_on_selector_all(".willie-audio-row", "els => els.map(e => e.textContent)")
        self.assertEqual(labels, [t["label"] for t in TRACKS])
        pressed = page.eval_on_selector_all(".willie-audio-row", "els => els.map(e => e.getAttribute('aria-pressed'))")
        self.assertEqual(pressed, ["true", "false"])
        self.assertEqual(page.text_content(".willie-audio-title"), "Audio")
        self.assertIn("✓", page.eval_on_selector(".willie-audio-row[aria-pressed='true'] > span",
                                                "e => getComputedStyle(e, '::before').content"))

    def test_the_first_track_plays_the_original_file(self):
        page, hls_urls, _ = self.open_player(setup=serve_tracks(TRACKS))
        page.wait_for_function("document.querySelector('.willie-player video')?.src.includes('/api/watch/7/stream')")
        self.assertEqual(hls_urls, [])

    def test_choosing_another_track_switches_to_a_stream_with_that_track(self):
        page, hls_urls, _ = self.open_player(setup=serve_tracks(TRACKS))
        page.wait_for_function("document.querySelector('.willie-player video')?.src.includes('/api/watch/7/stream')")
        self.open_menu(page)
        page.click(".willie-audio-row[data-audio='1']")
        for _ in range(60):
            if hls_urls:
                break
            page.wait_for_timeout(100)
        self.assertIn("audio=1", hls_urls[0])
        self.assertFalse(page.is_visible(".willie-data-menu"))
        # The panel now shows the new track as chosen.
        page.click("button[aria-label='Data use and quality']")
        page.wait_for_selector(".willie-audio-row")
        self.assertEqual(page.get_attribute(".willie-audio-row[data-audio='1']", "aria-pressed"), "true")
        # Without a saved quality choice, the quality stays "Best available".
        self.assertIsNone(page.evaluate("localStorage.getItem('willie:quality')"))

    def test_the_language_is_remembered_for_the_next_video(self):
        page, hls_urls, stream_urls = self.open_player(setup=serve_tracks(TRACKS))
        self.open_menu(page)
        page.click(".willie-audio-row[data-audio='1']")
        self.assertEqual(page.evaluate("localStorage.getItem('willie:audio-language')"), "fre")
        del hls_urls[:], stream_urls[:]
        page.reload(wait_until="load")
        page.click("#launch")
        for _ in range(60):
            if hls_urls:
                break
            page.wait_for_timeout(100)
        self.assertIn("audio=1", hls_urls[0])
        self.assertEqual(stream_urls, [], "the original file cannot play a second audio track")

    def test_going_back_to_the_first_track_returns_to_the_original_file(self):
        page, hls_urls, _ = self.open_player(setup=serve_tracks(TRACKS))
        self.open_menu(page)
        page.click(".willie-audio-row[data-audio='1']")
        for _ in range(60):
            if hls_urls:
                break
            page.wait_for_timeout(100)
        page.wait_for_function("document.querySelector('.willie-info').textContent.includes('stub transcoder')")
        page.click("button[aria-label='Data use and quality']")
        page.click(".willie-audio-row[data-audio='0']")
        page.wait_for_function("document.querySelector('.willie-player video')?.src.includes('/api/watch/7/stream')")

    def test_a_file_whose_default_track_is_not_the_first_starts_on_it(self):
        tracks = [dict(TRACKS[0], default=False), dict(TRACKS[1], default=True)]
        page, hls_urls, stream_urls = self.open_player(setup=serve_tracks(tracks))
        for _ in range(60):
            if hls_urls:
                break
            page.wait_for_timeout(100)
        self.assertIn("audio=1", hls_urls[0])
        self.assertEqual(stream_urls, [])

    def test_the_player_still_starts_when_the_track_list_is_unavailable(self):
        def setup(page):
            page.route("**/api/stream/hls/audio/7", lambda route: route.fulfill(
                status=500, content_type="application/json", body="{}"))
        page, hls_urls, _ = self.open_player(setup=setup)
        page.wait_for_function("document.querySelector('.willie-player video')?.src.includes('/api/watch/7/stream')")
        self.open_menu(page)
        page.wait_for_timeout(300)
        self.assertEqual(page.locator(".willie-audio-row").count(), 0)


if __name__ == "__main__":
    unittest.main()
