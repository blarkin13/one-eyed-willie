"""Explore search results show right under the search box, not below the discovery rows."""
import json
import unittest

from tests import test_mobile_home_browser as base


def item(n):
    return {"id": n, "title": f"Lethal Weapon {n}", "year": 1987 + n, "overview": "Cops.", "poster_url": None}


@unittest.skipUnless(base.sync_playwright and base.CHROME, "Playwright and Chrome required")
class ExploreResultsTest(base.MobileHomeLayoutTest):
    def test_phone_has_no_document_sideways_scroll_and_dock_is_visible(self): pass

    def test_results_replace_the_discovery_rows_until_the_search_is_cleared(self):
        context = self.browser.new_context(viewport={"width": 900, "height": 420}, is_mobile=True, has_touch=True)
        self.addCleanup(context.close)
        page = context.new_page()
        html = (base.Path(__file__).resolve().parents[1] / "server/explore.html").read_text()
        page.route(f"http://127.0.0.1:{self.port}/explore*", lambda r: r.fulfill(body=html, content_type="text/html"))

        def arr(route):
            url = route.request.url
            if "/lookup" in url:
                return route.fulfill(json={"items": [item(n) for n in range(9)]})
            if "/discover" in url:
                return route.fulfill(json={"items": [item(n + 20) for n in range(6)]})
            return route.fulfill(json={"connections": [{"id": "radarr", "configured": True}], "items": []})
        page.route("**/api/arr/**", arr)
        page.goto(f"http://127.0.0.1:{self.port}/explore?type=movies")
        page.fill("#query", "Lethal weapon")
        page.click("#search-button")
        page.wait_for_selector("#results .explore-card")
        self.assertTrue(page.eval_on_selector("#discovery", "d => d.hidden"))
        status_bottom = page.eval_on_selector("#status", "s => s.getBoundingClientRect().bottom")
        first_top = page.eval_on_selector("#results .explore-card", "c => c.getBoundingClientRect().top")
        self.assertLess(first_top - status_bottom, 120, "the first result sits right under the result count")
        self.assertEqual(page.locator("#results .explore-card").count(), 9)
        # Clearing the search brings discovery back.
        page.fill("#query", "")
        self.assertFalse(page.eval_on_selector("#discovery", "d => d.hidden"))
        self.assertEqual(page.locator("#results .explore-card").count(), 0)
