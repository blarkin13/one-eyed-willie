"""The Download button on a movie page: phone app only, only when the server allows it."""
import json
import unittest

from tests import test_mobile_home_browser as base

MOVIE = {"title": "Easy", "year": 2020, "media_id": 7, "poster_url": "/api/artwork/abc", "duration_seconds": 5400,
         "overview": "", "genres": [], "position_seconds": 0, "watched": False}
PHONE_UA = "Mozilla/5.0 (Linux; Android 15) Chrome/131 Mobile YarrMediaAndroid/1"


@unittest.skipUnless(base.sync_playwright and base.CHROME, "Playwright and Chrome required")
class DownloadButtonTest(base.MobileHomeLayoutTest):
    def test_phone_has_no_document_sideways_scroll_and_dock_is_visible(self): pass

    def movie(self, ua=None, allowed=True):
        context = self.browser.new_context(viewport={"width": 412, "height": 860}, user_agent=ua or PHONE_UA,
                                           is_mobile=True, has_touch=True)
        self.addCleanup(context.close)
        page = context.new_page()
        prompts = []
        page.on("dialog", lambda d: (prompts.append(d.message), d.accept("ACK")))
        page.route("**/api/movies/details*", lambda r: r.fulfill(json=MOVIE))
        page.route("**/api/downloads/status", lambda r: r.fulfill(json={"allowed": allowed, "reason": None if allowed else "pro_required"}))
        page.goto(f"http://127.0.0.1:{self.port}/movie?library_id=1&key=easy")
        page.wait_for_function("document.getElementById('movie-title').textContent==='Easy'", timeout=15000)
        page.wait_for_timeout(400)
        return page, prompts

    def visible(self, page):
        return page.evaluate("(()=>{const b=document.querySelector('.yarr-download');return !!b&&!b.hidden})()")

    def test_phone_app_with_pro_gets_a_download_button(self):
        page, prompts = self.movie()
        self.assertTrue(self.visible(page))
        page.tap(".yarr-download")
        sent = [m for m in prompts if m.startswith("oewtv:shell:download:")]
        self.assertEqual(len(sent), 1)
        item = json.loads(sent[0].removeprefix("oewtv:shell:download:"))
        self.assertEqual((item["media_id"], item["kind"], item["title"], item["subtitle"], item["poster_url"]),
                         (7, "movie", "Easy", "2020", "/api/artwork/abc"))
        order = page.eval_on_selector_all(".movie-detail-actions > button:not([hidden])", "b => b.map(x => x.id || x.className)")
        self.assertLess(order.index("play-movie"), [i for i, x in enumerate(order) if "yarr-download" in x][0])

    def test_hidden_without_pro_on_tv_and_on_the_website(self):
        page, _ = self.movie(allowed=False)
        self.assertFalse(self.visible(page), "no Pro: no button")
        page, _ = self.movie(ua="Mozilla/5.0 (Linux; Android 14) Chrome/131 OneEyedWillieTV/1")
        self.assertFalse(self.visible(page), "the TV app never shows it")
        page, _ = self.movie(ua="Mozilla/5.0 (X11; Linux x86_64) Chrome/131")
        self.assertFalse(self.visible(page), "nor does the website")


if __name__ == "__main__":
    unittest.main()
