"""Track lists fit the phone screen (long titles are cut off, no sideways scroll); Top songs show in the browser too."""
import io
import unittest

from PIL import Image

from tests import test_mobile_home_browser as base
from tests.test_android_app_shell_browser import APP_SCRIPT

LONG = "These Foolish Things (Remind Me of You) — Live at Carnegie Hall, Remastered 2026 Edition"
TRACKS = [dict(id=i, title=LONG if i == 4 else f"Song {i}", artist="Billie Holiday", album_artist="Billie Holiday",
               album="Solitude", year=1952, track_number=i, disc_number=1, duration=200, genre="Jazz") for i in range(1, 9)]


@unittest.skipUnless(base.sync_playwright and base.CHROME, "Playwright and Chrome required")
class MusicTrackTableTest(base.MobileHomeLayoutTest):
    def test_phone_has_no_document_sideways_scroll_and_dock_is_visible(self): pass

    def open_artist(self, app, width=412):
        context = self.browser.new_context(viewport={"width": width, "height": 860}, is_mobile=True, has_touch=True)
        self.addCleanup(context.close)
        if app:
            context.add_init_script(APP_SCRIPT)
        page = context.new_page()
        html = (base.Path(__file__).resolve().parents[1] / "server/music.html").read_text()
        page.route(f"http://127.0.0.1:{self.port}/music*", lambda r: r.fulfill(body=html, content_type="text/html"))
        page.route("**/api/music/catalog", lambda r: r.fulfill(json={"tracks": TRACKS}))
        page.route("**/api/music/artist-top*", lambda r: r.fulfill(json={"tracks": [4, 2, 7, 1, 3], "source": "ListenBrainz"}))
        page.route("**/api/lidarr/**", lambda r: r.fulfill(json={"found": False}))
        art = io.BytesIO()
        Image.new("RGB", (60, 60), (90, 90, 90)).save(art, "PNG")
        page.route("**/api/music/tracks/**", lambda r: r.fulfill(body=art.getvalue(), content_type="image/png"))
        page.goto(f"http://127.0.0.1:{self.port}/music?artist=Billie%20Holiday")
        page.wait_for_selector(".top-songs:not([hidden]) tr.row", timeout=15000)
        page.wait_for_timeout(300)
        return page

    def test_long_titles_do_not_push_the_page_sideways(self):
        for app in (False, True):
            for width in (360, 412):
                with self.subTest(app=app, width=width):
                    page = self.open_artist(app, width)
                    data = page.evaluate("""() => {
                      const row=[...document.querySelectorAll('.top-songs tr.row')].find(r=>r.dataset.id==='4');
                      const t=row.querySelector('.t-title'), dur=row.querySelector('td.dur');
                      return {doc:document.documentElement.scrollWidth, body:document.body.scrollWidth,
                              table:document.querySelector('.top-songs .tracks').getBoundingClientRect().right,
                              durRight:dur.getBoundingClientRect().right, cut:t.scrollWidth>t.clientWidth};
                    }""")
                    self.assertLessEqual(data["doc"], width)
                    self.assertLessEqual(data["body"], width)
                    self.assertLessEqual(data["table"], width)
                    self.assertLessEqual(data["durRight"], width, "the length column stays on screen")
                    self.assertTrue(data["cut"], "the long title is cut off with …")

    def test_top_songs_show_in_the_phone_browser(self):
        page = self.open_artist(False)
        ids = page.eval_on_selector_all(".top-songs tr.row", "rows => rows.map(r => r.dataset.id)")
        self.assertEqual(ids, ["4", "2", "7", "1", "3"])
