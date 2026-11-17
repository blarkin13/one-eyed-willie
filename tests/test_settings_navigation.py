"""Settings navigation should stay grouped and all pages should be reachable."""
import unittest
from pathlib import Path
from server.main import app

ROOT = Path(__file__).resolve().parents[1] / "server"


class SettingsNavigationTests(unittest.TestCase):
    def test_four_settings_pages_have_routes(self):
        routes = {getattr(route, "path", "") for route in app.routes}
        for expected in ("/settings", "/settings/general", "/settings/appearance", "/settings/libraries",
                         "/settings/metadata", "/settings/connections"):
            self.assertIn(expected, routes)

    def test_general_links_to_real_maintenance_playback_remote_endpoints(self):
        page = (ROOT / "general_settings.html").read_text()
        for endpoint in (
            "/api/settings/playback", "/api/maintenance/settings",
            "/api/maintenance/run", "/api/maintenance/previews/generate",
            "/api/remote/settings",
        ):
            self.assertIn(endpoint, page)
        appearance = (ROOT / "appearance_settings.html").read_text()
        self.assertIn("/api/settings/sidebar", appearance)
        self.assertIn('id="sidebar-order"', appearance)
        self.assertIn("/api/settings/tv-appearance", appearance)
        self.assertIn('id="tv-selection-color"', appearance)

    def test_gear_is_only_settings_sidebar_entry(self):
        shell = (ROOT / "shell.js").read_text()
        self.assertIn("href:'/settings',name:'Settings'", shell)
        self.assertNotIn("settingsSections", shell)
        self.assertNotIn("settings-shortcuts", shell)
        self.assertNotIn("const settingsSheet=document.createElement('dialog')", shell)
        css = (ROOT / "ui.css").read_text()
        self.assertNotIn("settings-shortcuts", css)
        # The four settings destinations belong to the landing page,
        # not the sidebar on settings screens.
        page = (ROOT / "settings_hub.html").read_text()
        for heading, route in [
            ("Playback &amp; Server", "/settings/general"),
            ("Appearance &amp; Navigation", "/settings/appearance"),
            ("Libraries", "/settings/libraries"),
            ("Metadata", "/settings/metadata"),
            ("Connections", "/settings/connections"),
        ]:
            self.assertIn("<h2>"+heading+"</h2>", page)
            self.assertIn('href="'+route+'"', page)

    def test_tv_uses_device_specific_playback_settings_page(self):
        from starlette.requests import Request
        from server.main import settings_home_page
        tv_request = Request({"type": "http", "method": "GET", "path": "/settings",
                              "headers": [(b"user-agent", b"OneEyedWillieTV/1")]})
        browser_request = Request({"type": "http", "method": "GET", "path": "/settings",
                                   "headers": [(b"user-agent", b"Mozilla/5.0")]})
        self.assertTrue(str(settings_home_page(tv_request).path).endswith("tv_settings.html"))
        self.assertTrue(str(settings_home_page(browser_request).path).endswith("settings_hub.html"))
        page = (ROOT / "tv_settings.html").read_text()
        for term in ("tv-subtitle-form", "tv-subtitles-on", "tv-language-dialog",
                     "tv-playback-form", "tv-server-connection"):
            self.assertIn(term, page)
        for title in ("Library settings", "Metadata", "Maintenance", "Connections",
                      "Appearance &amp; Navigation"):
            self.assertNotIn("<h2>" + title + "</h2>", page)
        main = (ROOT.parent / "google-tv/app/src/main/java/studio/oneeyedwillie/tv/MainActivity.kt").read_text()
        player = (ROOT.parent / "google-tv/app/src/main/java/studio/oneeyedwillie/tv/PlayerActivity.kt").read_text()
        self.assertIn('getSharedPreferences("oew_tv_subtitles"', main)
        self.assertIn('getSharedPreferences("oew_tv_subtitles"', player)
        self.assertIn("applyDefaultSubtitlesForThisTv", player)
        self.assertIn('id="tv-color-form"', page)
        self.assertIn('id="tv-color-dialog"', page)
        self.assertIn('/api/settings/tv-appearance', page)
        self.assertIn("document.documentElement.style.setProperty('--oew-tv-select-color',chosen)", page)


    def test_tv_appearance_is_shared_with_native_and_web_players(self):
        main = (ROOT / "sidebar_settings.py").read_text()
        native = (ROOT.parent / "google-tv/app/src/main/java/studio/oneeyedwillie/tv/PlayerActivity.kt").read_text()
        web = (ROOT / "player.js").read_text()
        self.assertIn('tv_selection_color', main)
        self.assertIn('/api/settings/tv-appearance', native)
        self.assertIn('/api/settings/tv-appearance', web)
        self.assertIn('applyPlayerSelectionColor', native)

    def test_radarr_sonarr_are_service_tabs_not_sidebar_destinations(self):
        from server.sidebar_settings import NAV, ICON_NAMES
        nav_ids = {item[0] for item in NAV}
        self.assertNotIn("radarr", nav_ids)
        self.assertNotIn("sonarr", nav_ids)
        self.assertNotIn("radarr", ICON_NAMES)
        self.assertNotIn("sonarr", ICON_NAMES)
        self.assertIn("sabnzbd", nav_ids)
        self.assertIn("sabnzbd", ICON_NAMES)
        shell = (ROOT / "shell.js").read_text()
        for link in ("{id:'radarr'", "{id:'sonarr'"):
            self.assertNotIn(link, shell)
        appearance = (ROOT / "appearance_settings.html").read_text()
        self.assertNotIn("radarr:'Radarr'", appearance)
        self.assertNotIn("sonarr:'Sonarr'", appearance)
        for name in ("manager_dashboard.html", "sab_dashboard.html"):
            page = (ROOT / name).read_text()
            self.assertIn('href="/radarr"', page)
            self.assertIn('href="/sonarr"', page)

    def test_playback_is_only_configured_in_general(self):
        from server.main import playback_settings_page
        general = (ROOT / "general_settings.html").read_text()
        self.assertIn('id="auto-next"', general)
        self.assertNotIn('Advanced playback page', general)
        self.assertNotIn('href="/settings/playback"', general)
        response = playback_settings_page()
        self.assertEqual(response.status_code, 307)
        self.assertEqual(response.headers["location"], "/settings/general#playback-heading")

    def test_library_editor_supports_icon_font_and_multi_folders(self):
        page = (ROOT / "index.html").read_text()
        for label in ("Sidebar icon","Sidebar font","Add folder",
                      "Remove folder", "Scan", "Edit"):
            self.assertIn(label,page)
        self.assertIn("method:'PATCH'",page)
        self.assertIn("'/folders'",page)


if __name__ == "__main__":
    unittest.main()
