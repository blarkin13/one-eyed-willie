"""Settings navigation should stay grouped and all pages should be reachable."""
import unittest
from pathlib import Path
from server.main import app

ROOT = Path(__file__).resolve().parents[1] / "server"


class SettingsNavigationTests(unittest.TestCase):
    def test_four_settings_pages_have_routes(self):
        routes = {getattr(route, "path", "") for route in app.routes}
        for expected in ("/settings", "/settings/general", "/settings/libraries",
                         "/settings/metadata", "/settings/connections"):
            self.assertIn(expected, routes)

    def test_general_links_to_real_maintenance_playback_remote_endpoints(self):
        page = (ROOT / "general_settings.html").read_text()
        for endpoint in (
            "/api/settings/playback", "/api/maintenance/settings",
            "/api/maintenance/run", "/api/maintenance/previews/generate",
            "/api/remote/settings", "/api/settings/sidebar",
        ):
            self.assertIn(endpoint, page)
        self.assertIn('id="sidebar-order"', page)

    def test_gear_links_to_hub_and_sidebar_has_four_sections(self):
        shell = (ROOT / "shell.js").read_text()
        self.assertIn("href:'/settings',name:'Settings'", shell)
        for route in ("/settings/general","/settings/libraries",
                      "/settings/metadata","/settings/connections"):
            self.assertIn(route,shell)
        self.assertNotIn("const settingsSheet=document.createElement('dialog')",shell)
        page = (ROOT / "settings_hub.html").read_text()
        for heading in ("General", "Library", "Metadata", "Connections"):
            self.assertIn("<h2>"+heading+"</h2>",page)

    def test_library_editor_supports_icon_font_and_multi_folders(self):
        page = (ROOT / "index.html").read_text()
        for label in ("Sidebar icon","Sidebar font","Add folder",
                      "Remove folder", "Scan", "Edit"):
            self.assertIn(label,page)
        self.assertIn("method:'PATCH'",page)
        self.assertIn("'/folders'",page)


if __name__ == "__main__":
    unittest.main()
