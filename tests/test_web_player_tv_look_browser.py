"""The web player looks like the TV app, shows measured data use, and offers a
cheaper quality when the connection is too slow for the current one.

Runs the real server page and ``player.js`` in headless Chrome with the media
APIs stubbed (same harness as the quality tests).
"""
import json
import unittest

from tests import test_web_player_quality_browser as base

SELECT = "rgb(139, 92, 246)"      # default TV selection colour, #8B5CF6
PLAYER = ".willie-player"


@unittest.skipUnless(base.sync_playwright and base.CHROME, "Playwright and Chrome are required")
class WebPlayerTvLookTests(unittest.TestCase):
    setUpClass = classmethod(base.WebPlayerQualityBrowserTests.setUpClass.__func__)
    tearDownClass = classmethod(base.WebPlayerQualityBrowserTests.tearDownClass.__func__)
    open_player = base.WebPlayerQualityBrowserTests.open_player
    choose = staticmethod(base.WebPlayerQualityBrowserTests.choose)

    def style(self, page, selector, prop, pseudo=None):
        return page.eval_on_selector(
            selector, "(el, [prop, pseudo]) => getComputedStyle(el, pseudo)[prop]", [prop, pseudo])

    def open_menu(self, page):
        page.click("button[aria-label='Data use and quality']")
        page.wait_for_selector("button.willie-data-row[data-quality='480p']")

    # ----- look ----------------------------------------------------------------
    def test_top_bar_has_the_tv_heading(self):
        page, _, _ = self.open_player()
        self.assertEqual(page.text_content(".willie-kicker"), "NOW PLAYING")
        self.assertEqual(self.style(page, ".willie-title", "fontSize"), "22px")
        self.assertEqual(self.style(page, ".willie-title", "fontWeight"), "700")
        self.assertEqual(self.style(page, ".willie-kicker", "fontSize"), "11px")
        self.assertNotEqual(self.style(page, ".willie-kicker", "letterSpacing"), "normal")

    def test_controls_use_the_tv_order_sizes_and_black_background(self):
        page, _, _ = self.open_player()
        labels = page.eval_on_selector_all(
            ".willie-toolbar .willie-group:first-child button", "els => els.map(e => e.getAttribute('aria-label'))")
        self.assertEqual(labels[0], "Rewind 10 seconds")
        self.assertIn(labels[1], ("Pause", "Play"))
        self.assertEqual(labels[2], "Forward 10 seconds")
        self.assertEqual(self.style(page, "button[aria-label='Rewind 10 seconds']", "width"), "54px")
        self.assertEqual(self.style(page, ".willie-toolbar button.willie-large", "width"), "64px")
        self.assertEqual(self.style(page, PLAYER, "backgroundColor"), "rgb(0, 0, 0)")
        self.assertIn("linear-gradient", self.style(page, ".willie-bottom", "backgroundImage"))
        self.assertEqual(self.style(page, ".willie-bottom", "paddingLeft"), "50px")

    def test_focused_icon_takes_the_selection_colour_and_grows(self):
        page, _, _ = self.open_player()
        page.keyboard.press("Shift")
        page.focus("button[aria-label='Forward 10 seconds']")
        page.wait_for_timeout(250)
        self.assertEqual(self.style(page, "button[aria-label='Forward 10 seconds']", "color"), SELECT)
        self.assertIn("1.16", self.style(page, "button[aria-label='Forward 10 seconds']", "transform"))

    def test_menu_is_a_dark_glass_panel_like_the_tv_menu(self):
        page, _, _ = self.open_player()
        self.open_menu(page)
        menu = ".willie-data-menu"
        self.assertEqual(self.style(page, menu, "borderRadius"), "17px")
        self.assertEqual(self.style(page, menu, "backgroundColor"), "rgba(10, 17, 29, 0.937)")
        self.assertEqual(self.style(page, ".willie-data-menu .willie-menu-title", "fontSize"), "22px")
        self.assertEqual(page.text_content(".willie-data-menu .willie-menu-title"), "Quality and data")
        row = "button.willie-data-row[data-quality='480p']"
        self.assertEqual(self.style(page, row, "minHeight"), "49px")
        self.assertEqual(self.style(page, row, "borderRadius"), "9px")
        self.assertEqual(self.style(page, row, "fontSize"), "16px")

    def test_focused_menu_row_is_outlined_in_the_selection_colour(self):
        page, _, _ = self.open_player()
        self.open_menu(page)
        row = "button.willie-data-row[data-quality='480p']"
        page.keyboard.press("Shift")
        page.focus(row)
        self.assertEqual(self.style(page, row, "borderTopColor"), SELECT)
        self.assertEqual(self.style(page, row, "color"), SELECT)

    def test_the_chosen_row_is_ticked_and_coloured_like_on_the_tv(self):
        page, _, _ = self.open_player()
        self.open_menu(page)
        chosen = "button.willie-data-row[aria-pressed='true']"
        self.assertIn("✓", self.style(page, chosen + " > span:first-child", "content", "::before"))
        self.assertEqual(self.style(page, chosen, "color"), SELECT)
        other = "button.willie-data-row[data-quality='480p']"
        self.assertEqual(self.style(page, other + " > span:first-child", "content", "::before"), "none")

    def test_subtitle_menu_shares_the_same_panel_style(self):
        page, _, _ = self.open_player()
        page.click("button[aria-label='Subtitles']")
        self.assertEqual(page.text_content(".willie-subtitle-menu .willie-menu-title"), "Subtitles")
        self.assertEqual(self.style(page, ".willie-subtitle-menu", "borderRadius"), "17px")
        self.assertEqual(self.style(page, ".willie-provider-search", "minHeight"), "49px")

    def test_the_users_selection_colour_setting_is_used(self):
        def setup(page):
            page.route("**/api/settings/tv-appearance", lambda route: route.fulfill(
                status=200, content_type="application/json", body=json.dumps({"selection_color": "#22AA66"})))
        page, _, _ = self.open_player(setup=setup)
        self.open_menu(page)
        page.keyboard.press("Shift")
        page.focus("button.willie-data-row[data-quality='480p']")
        self.assertEqual(self.style(page, "button.willie-data-row[data-quality='480p']", "borderTopColor"),
                         "rgb(34, 170, 102)")

    def test_message_banner_matches_the_tv_message(self):
        page, _, _ = self.open_player()
        page.evaluate("document.querySelector('.willie-info').textContent = 'Preparing video…'")
        self.assertEqual(self.style(page, ".willie-info", "backgroundColor"), "rgba(16, 24, 32, 0.867)")
        self.assertEqual(self.style(page, ".willie-info", "fontSize"), "16px")

    def test_escape_closes_the_open_panel_before_the_player(self):
        page, _, _ = self.open_player()
        self.open_menu(page)
        page.keyboard.press("Escape")
        self.assertFalse(page.is_visible(".willie-data-menu"))
        self.assertTrue(page.is_visible(PLAYER))

    # ----- phones --------------------------------------------------------------
    def test_menus_fit_and_are_touch_sized_on_a_phone(self):
        page, _, _ = self.open_player(viewport={"width": 390, "height": 780})
        self.open_menu(page)
        box = page.eval_on_selector(".willie-data-menu", "e => { const r = e.getBoundingClientRect(); return [r.left, r.right, r.top, r.bottom]; }")
        self.assertGreaterEqual(box[0], 0)
        self.assertLessEqual(box[1], 390)
        self.assertGreaterEqual(box[2], 0)
        row = page.eval_on_selector("button.willie-data-row[data-quality='480p']",
                                    "e => e.getBoundingClientRect().height")
        self.assertGreaterEqual(row, 44)
        icon = page.eval_on_selector("button[aria-label='Forward 10 seconds']",
                                     "e => { const r = e.getBoundingClientRect(); return [r.width, r.height]; }")
        self.assertGreaterEqual(icon[0], 40)
        self.assertGreaterEqual(icon[1], 44)
        # Every control stays on screen on a narrow phone.
        page.keyboard.press("Escape")
        edges = page.eval_on_selector_all(".willie-toolbar button", "els => els.map(e => e.getBoundingClientRect().right)")
        self.assertLessEqual(max(edges), 390)
        self.open_menu(page)
        page.keyboard.press("Escape")
        page.click("button[aria-label='Subtitles']")
        right = page.eval_on_selector(".willie-subtitle-menu", "e => e.getBoundingClientRect().right")
        self.assertLessEqual(right, 390)

    # ----- data used so far ----------------------------------------------------
    def test_requests_for_one_viewing_share_one_id(self):
        page, hls_urls, stream_urls = self.open_player()
        page.wait_for_function("document.querySelector('.willie-player video')?.src.includes('/api/watch/7/stream')")
        direct_id = page.evaluate("new URL(document.querySelector('.willie-player video').src).searchParams.get('viewing')")
        self.assertRegex(direct_id, r"^[0-9a-f]{24}$")
        self.choose(page, "480p")
        for _ in range(50):
            if hls_urls:
                break
            page.wait_for_timeout(100)
        self.assertIn("viewing=" + direct_id, hls_urls[0])

    def test_playing_another_video_while_fullscreen_keeps_the_player_open(self):
        # Next episode: the old player is removed (which ends fullscreen) as the new one opens.
        page, _, _ = self.open_player()
        page.wait_for_function("document.fullscreenElement !== null")
        page.evaluate("WilliePlayer.open(7, 'Next episode')")
        page.wait_for_timeout(2500)
        self.assertEqual(page.evaluate("document.querySelectorAll('.willie-player').length"), 1)
        self.assertEqual(page.text_content(".willie-title"), "Next episode")

    def test_a_new_video_gets_a_new_viewing_id(self):
        page, _, _ = self.open_player()
        page.wait_for_function("document.querySelector('.willie-player video')?.src.includes('viewing=')")
        first = page.evaluate("new URL(document.querySelector('.willie-player video').src).searchParams.get('viewing')")
        page.evaluate("WilliePlayer.open(7, 'Again')")
        page.wait_for_function(
            "(old) => { const v = document.querySelector('.willie-player video');"
            " return v && v.src.includes('viewing=') && !v.src.includes(old); }", arg=first)

    def test_counter_shows_measured_bytes_and_keeps_counting(self):
        sizes = iter([123_000_000, 123_000_000, 640_000_000] + [640_000_000] * 20)
        seen = []

        def setup(page):
            def usage(route):
                seen.append(route.request.url)
                route.fulfill(status=200, content_type="application/json",
                              body=json.dumps({"bytes": next(sizes)}))
            page.route("**/api/stream/hls/usage/*", usage)

        page, _, _ = self.open_player(setup=setup)
        self.assertTrue(page.evaluate("document.querySelector('.willie-usage').hidden"))   # nothing yet
        self.open_menu(page)                                  # opening the panel asks right away
        page.wait_for_function("document.querySelector('.willie-usage').textContent === '123 MB used'")
        self.assertIn("Used so far this viewing: 123 MB", page.text_content(".willie-data-menu"))
        # ...and it keeps polling while playing.
        page.wait_for_function("document.querySelector('.willie-usage').textContent === '640 MB used'", timeout=15000)
        viewing = page.evaluate("new URL(document.querySelector('.willie-player video').src).searchParams.get('viewing')")
        self.assertTrue(all(url.endswith("/usage/" + viewing) for url in seen))

    def test_counter_stays_hidden_when_the_server_has_counted_nothing(self):
        def setup(page):
            page.route("**/api/stream/hls/usage/*", lambda route: route.fulfill(
                status=200, content_type="application/json", body=json.dumps({"bytes": 0})))
        page, _, _ = self.open_player(setup=setup)
        self.open_menu(page)
        page.wait_for_timeout(500)
        self.assertTrue(page.evaluate("document.querySelector('.willie-usage').hidden"))
        self.assertNotIn("Used so far", page.text_content(".willie-data-menu"))

    # ----- slow connection -----------------------------------------------------
    STALL = """
        (times) => {
          const video = document.querySelector('.willie-player video');
          for (let i = 0; i < times; i++) {
            video.dispatchEvent(new Event('waiting'));
            video.dispatchEvent(new Event('playing'));
          }
        }"""

    def start_playing(self, page):
        page.wait_for_function("document.querySelector('.willie-player video')?.src.includes('/api/watch/7/stream')")
        page.evaluate("document.querySelector('.willie-player video').dispatchEvent(new Event('playing'))")

    def test_repeated_stalls_offer_a_cheaper_quality(self):
        page, hls_urls, _ = self.open_player()
        self.start_playing(page)
        page.evaluate(self.STALL, 2)
        self.assertFalse(page.is_visible(".willie-slow-prompt"), "two stalls are not yet a pattern")
        page.evaluate(self.STALL, 1)
        page.wait_for_selector(".willie-slow-prompt", state="visible")
        text = page.text_content(".willie-slow-prompt")
        self.assertIn("Slow connection", text)
        self.assertIn("keeps pausing", text)
        self.assertEqual(page.text_content(".willie-slow-prompt button[data-action='lower']"), "Switch to 720p")
        self.assertIn("about 1.5 GB for the rest", text)

    def test_switching_drops_quality_without_changing_the_saved_choice(self):
        page, hls_urls, _ = self.open_player()
        self.start_playing(page)
        page.evaluate(self.STALL, 3)
        page.click(".willie-slow-prompt button[data-action='lower']")
        for _ in range(50):
            if hls_urls:
                break
            page.wait_for_timeout(100)
        self.assertIn("quality=720p", hls_urls[0])
        self.assertIsNone(page.evaluate("localStorage.getItem('willie:quality')"))
        self.assertFalse(page.is_visible(".willie-slow-prompt"))

    def test_keeping_the_quality_stops_the_nagging(self):
        page, hls_urls, _ = self.open_player()
        self.start_playing(page)
        page.evaluate(self.STALL, 3)
        page.click(".willie-slow-prompt button[data-action='keep']")
        self.assertFalse(page.is_visible(".willie-slow-prompt"))
        page.evaluate(self.STALL, 6)
        page.wait_for_timeout(300)
        self.assertFalse(page.is_visible(".willie-slow-prompt"))
        self.assertEqual(hls_urls, [])

    def test_escape_dismisses_the_prompt_like_keeping(self):
        page, _, _ = self.open_player()
        self.start_playing(page)
        page.evaluate(self.STALL, 3)
        page.wait_for_selector(".willie-slow-prompt", state="visible")
        page.keyboard.press("Escape")
        self.assertFalse(page.is_visible(".willie-slow-prompt"))
        self.assertTrue(page.is_visible(PLAYER))

    def test_start_up_buffering_does_not_count(self):
        page, _, _ = self.open_player()
        page.wait_for_function("document.querySelector('.willie-player video')?.src.includes('/api/watch/7/stream')")
        # Buffering before the first frame is not a slow connection.
        page.evaluate("""
            () => { const v = document.querySelector('.willie-player video');
                    for (let i = 0; i < 6; i++) v.dispatchEvent(new Event('waiting'));
                    v.dispatchEvent(new Event('playing')); }""")
        page.wait_for_timeout(300)
        self.assertFalse(page.is_visible(".willie-slow-prompt"))

    def stall_on_transcode(self, quality):
        """Choose a transcode (the stub transcoder refuses), pretend it plays, and stall 3 times."""
        page, hls_urls, _ = self.open_player(setup=lambda page: page.clock.install())
        self.choose(page, quality)
        for _ in range(50):
            if hls_urls:
                break
            page.wait_for_timeout(100)
        page.wait_for_function("document.querySelector('.willie-info').textContent.includes('stub transcoder')")
        page.clock.run_for(11000)       # stalls right after a quality switch are ignored for 10 s
        page.evaluate("Object.defineProperty(document.querySelector('.willie-player video'), 'paused', {value: false})")
        page.evaluate("document.querySelector('.willie-player video').dispatchEvent(new Event('playing'))")
        page.evaluate(self.STALL, 3)
        page.wait_for_timeout(300)
        return page

    def test_a_slow_transcode_is_offered_the_next_tier_down(self):
        page = self.stall_on_transcode("720p")
        page.wait_for_selector(".willie-slow-prompt", state="visible")
        self.assertEqual(page.text_content(".willie-slow-prompt button[data-action='lower']"), "Switch to 480p")

    def test_the_cheapest_quality_is_never_asked_to_drop_further(self):
        self.assertTrue(self.stall_on_transcode("360p").is_visible(".willie-slow-prompt"),
                        "control: 360p can still drop to 240p")
        self.assertFalse(self.stall_on_transcode("240p").is_visible(".willie-slow-prompt"))

    def test_stalls_right_after_a_quality_switch_are_ignored(self):
        page, hls_urls, _ = self.open_player()
        self.choose(page, "720p")
        page.wait_for_function("document.querySelector('.willie-info').textContent.includes('stub transcoder')")
        page.evaluate("Object.defineProperty(document.querySelector('.willie-player video'), 'paused', {value: false})")
        page.evaluate("document.querySelector('.willie-player video').dispatchEvent(new Event('playing'))")
        page.evaluate(self.STALL, 6)
        page.wait_for_timeout(300)
        self.assertFalse(page.is_visible(".willie-slow-prompt"))

    def test_one_long_stall_also_triggers_the_offer(self):
        def setup(page):
            page.clock.install()
        page, _, _ = self.open_player(setup=setup)
        self.start_playing(page)
        page.evaluate("document.querySelector('.willie-player video').dispatchEvent(new Event('waiting'))")
        page.clock.run_for(9000)
        page.wait_for_selector(".willie-slow-prompt", state="visible")

    def test_prompt_fits_on_a_phone(self):
        page, _, _ = self.open_player(viewport={"width": 390, "height": 780})
        self.start_playing(page)
        page.evaluate(self.STALL, 3)
        page.wait_for_selector(".willie-slow-prompt", state="visible")
        box = page.eval_on_selector(".willie-slow-prompt",
                                    "e => { const r = e.getBoundingClientRect(); return [r.left, r.right]; }")
        self.assertGreaterEqual(box[0], 0)
        self.assertLessEqual(box[1], 390)
        height = page.eval_on_selector(".willie-slow-prompt button[data-action='lower']",
                                       "e => e.getBoundingClientRect().height")
        self.assertGreaterEqual(height, 44)


if __name__ == "__main__":
    unittest.main()
