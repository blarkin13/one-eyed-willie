"""Who's watching? in a browser and on a TV remote; the People settings page."""
import unittest

from tests import test_mobile_home_browser as base


@unittest.skipUnless(base.sync_playwright and base.CHROME, "Playwright and Chrome required")
class ProfilesBrowserTest(base.MobileHomeLayoutTest):
    def test_phone_has_no_document_sideways_scroll_and_dock_is_visible(self): pass
    def test_swiping_posters_updates_feature_selection(self): pass

    def page(self, width=1280, height=800, mobile=False):
        context = self.browser.new_context(viewport={"width": width, "height": height}, is_mobile=mobile, has_touch=mobile)
        self.addCleanup(context.close)
        return context.new_page()

    def test_setting_up_choosing_and_switching_profiles(self):
        url = f"http://127.0.0.1:{self.port}"
        owner = self.page()
        owner.goto(url + "/settings/people")
        owner.wait_for_selector("#setup:not([hidden])")
        owner.fill("#setup-owner", "Brian")
        owner.fill("#setup-name", "Sam")
        owner.check("[name=setup-kind][value=kid]")
        owner.click("#setup-form button[type=submit]")
        owner.wait_for_selector("#manage:not([hidden]) .person-row")
        names = owner.eval_on_selector_all(".person-row strong", "e => e.map(x => x.textContent)")
        self.assertEqual(names, ["Family", "Brian", "Sam"])
        owner.screenshot(path="/tmp/profiles-people.png", full_page=True)

        # A new device lands on Who's watching? and keeps going where it was headed.
        tv = self.page(1280, 720)
        tv.goto(url + "/settings/general")
        tv.wait_for_selector(".person")
        self.assertIn("/who?next=%2Fsettings%2Fgeneral", tv.url)
        tv.screenshot(path="/tmp/profiles-who-tv.png")
        # Remote: arrows move between people, OK picks.
        tv.keyboard.press("ArrowRight")
        self.assertEqual(tv.evaluate("document.activeElement.textContent"), "BBrian")
        tv.keyboard.press("Enter")
        tv.wait_for_url(url + "/settings/general")
        tv.wait_for_selector('.sidebar a[data-nav-id="profile"]')
        self.assertEqual(tv.text_content('.sidebar a[data-nav-id="profile"] .profile-avatar'), "B")

        # A PIN on a profile: the number pad asks for it.
        sam = tv.evaluate("fetch('/api/profiles').then(r => r.json()).then(d => d.profiles.find(p => p.name === 'Sam').id)")
        tv.evaluate(f"fetch('/api/profiles/{sam}/pin', {{method:'PUT', headers:{{'content-type':'application/json'}}, body: JSON.stringify({{pin:'2468'}})}})")
        tv.goto(url + "/who")
        tv.click(f".person[data-id='{sam}']")
        tv.wait_for_selector("#pin-dialog[open]")
        tv.screenshot(path="/tmp/profiles-pin.png")
        for digit in "1111":
            tv.keyboard.press(digit)
        tv.click("#pad [data-key=ok]")
        tv.wait_for_function("document.getElementById('pin-error').textContent.length > 0")
        for digit in "2468":
            tv.keyboard.press(digit)
        tv.click("#pad [data-key=ok]")
        tv.wait_for_url(url + "/")
        self.assertEqual(tv.evaluate("fetch('/api/viewer').then(r => r.json()).then(v => v.role)"), "kid")

        # Phone browser: tiles fit the screen.
        phone = self.page(390, 844, mobile=True)
        phone.goto(url + "/")
        phone.wait_for_selector(".person")
        self.assertLessEqual(phone.evaluate("document.documentElement.scrollWidth"), 390)
        phone.screenshot(path="/tmp/profiles-who-phone.png")
