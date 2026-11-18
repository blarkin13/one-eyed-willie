"""HEVC Full quality in the web player: a real HEVC file, the real server, Chrome.

The Chrome used in tests cannot decode HEVC, which makes it a good stand-in for
the worst case, a browser that claims support it does not have: the player must
fall back to a normal stream by itself. A browser that honestly reports no HEVC
support must never be offered the original video. (Whether a real HEVC-capable
browser decodes the copied video cannot be tested here.)
"""
import subprocess
import unittest

from tests import test_web_player_full_quality_browser as full
from tests.test_hls_hevc_full_quality import have_x265

CLAIMS_HEVC = """
(() => {
  const real = MediaSource.isTypeSupported.bind(MediaSource);
  MediaSource.isTypeSupported = type => /hvc1|hev1/.test(type) ? true : real(type);
})();
"""
CLAIMS_MAIN_ONLY = CLAIMS_HEVC.replace("/hvc1|hev1/", "/hvc1\\.1\\./")


@unittest.skipUnless(full.READY and have_x265(), "Playwright, Chrome and FFmpeg with x265 are required")
class HevcFullQualityBrowserTests(unittest.TestCase):
    setUpClass = classmethod(full.FullQualityBrowserTests.setUpClass.__func__)
    tearDownClass = classmethod(full.FullQualityBrowserTests.tearDownClass.__func__)
    _playing = full.FullQualityBrowserTests.playing

    def playing(self, page, width=None, engine=None):
        # Software-decoding 10-bit HEVC and re-encoding it is slow on a busy CI runner.
        self._playing(page, width=width, engine=engine, timeout=120000)

    @classmethod
    def make_movie(cls, path):
        subprocess.run(
            [full.FFMPEG, "-v", "error", "-nostdin", "-y", "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=24",
             "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000", "-t", "30",
             "-c:v", "libx265", "-preset", "ultrafast", "-pix_fmt", "yuv420p10le",
             "-x265-params", "keyint=48:min-keyint=48:log-level=error",
             "-c:a", "ac3", "-ac", "2", str(path)], check=True)

    def open_player(self, init_script=None):
        context = self.browser.new_context(viewport={"width": 1280, "height": 720})
        self.addCleanup(context.close)
        page = context.new_page()
        self.requests = []
        page.on("request", lambda r: self.requests.append(r.url) if "/api/stream/hls/" in r.url else None)
        if init_script:
            page.add_init_script(init_script)

        def close_player():
            try:
                page.evaluate("window.WilliePlayer && window.WilliePlayer.close()")
                page.wait_for_timeout(400)
            except Exception:
                pass
        self.addCleanup(close_player)
        page.goto("%s/watch/%d" % (self.origin, self.media_id), wait_until="load")
        page.click("#launch")
        return page

    def starts(self):
        return [u for u in self.requests if "/hls/start/" in u]

    def wait_for_starts(self, page, count):
        for _ in range(200):
            if len(self.starts()) >= count:
                return
            page.wait_for_timeout(100)
        self.fail("expected %d stream starts, saw %s" % (count, self.starts()))

    def test_an_honest_browser_without_hevc_is_never_offered_the_original(self):
        page = self.open_player()
        self.wait_for_starts(page, 1)
        self.assertIn("quality=720p", self.starts()[0])
        self.assertTrue(all("hevc=" not in u for u in self.requests), self.requests)
        self.playing(page, width=1280)
        page.click("button[aria-label='Data use and quality']")
        page.wait_for_selector("button.willie-data-row[data-quality='720p']")
        self.assertEqual(page.locator("button.willie-data-row[data-quality='full']").count(), 0)

    def test_a_browser_that_claims_hevc_is_offered_the_original_video(self):
        page = self.open_player(CLAIMS_HEVC)
        self.wait_for_starts(page, 1)
        self.assertIn("quality=full", self.starts()[0])
        self.assertIn("hevc=10", self.starts()[0])
        self.assertTrue(any("/estimates/" in u and "hevc=10" in u for u in self.requests))

    def test_a_browser_that_only_claims_8_bit_is_not_offered_a_10_bit_file(self):
        page = self.open_player(CLAIMS_MAIN_ONLY)
        self.wait_for_starts(page, 1)
        self.assertIn("quality=720p", self.starts()[0])
        self.assertIn("hevc=8", self.starts()[0])
        self.playing(page, width=1280)

    def test_a_browser_that_cannot_really_decode_it_drops_to_720p_by_itself(self):
        page = self.open_player(CLAIMS_HEVC)
        self.wait_for_starts(page, 2)
        self.assertIn("quality=full", self.starts()[0])
        self.assertIn("quality=720p", self.starts()[1])
        self.assertNotIn("hevc=", self.starts()[1])         # it stops claiming support
        self.playing(page, width=1280)                      # and the picture plays
        self.assertEqual(page.evaluate("sessionStorage.getItem('willie:hevc-failed')"), "1")
        # The fallback is temporary: the saved quality choice is untouched.
        self.assertIsNone(page.evaluate("localStorage.getItem('willie:quality')"))

    def test_after_a_failure_the_next_video_in_the_tab_does_not_try_again(self):
        page = self.open_player(CLAIMS_HEVC)
        self.wait_for_starts(page, 2)
        self.playing(page, width=1280)
        before = len(self.starts())
        page.evaluate("WilliePlayer.open(%d, 'Again')" % self.media_id)
        self.wait_for_starts(page, before + 1)
        self.assertIn("quality=720p", self.starts()[before])
        self.assertNotIn("hevc=", self.starts()[before])


if __name__ == "__main__":
    unittest.main()
