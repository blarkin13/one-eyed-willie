"""The Integrations rename is display-only and preserves saved service settings."""
import unittest
from pathlib import Path

from server.main import app, download_services_page, connections_hub_page, arr_connections_page
from server.sidebar_settings import NAV, CONNECTION_SERVICE_IDS

ROOT=Path(__file__).resolve().parents[1]/"server"

class IntegrationsRenameTests(unittest.TestCase):
    def test_canonical_and_legacy_routes_coexist(self):
        paths={getattr(route,"path","") for route in app.routes}
        for path in ("/integrations","/connections","/settings/integrations","/settings/connections"):
            self.assertIn(path,paths)
        self.assertTrue(str(connections_hub_page().path).endswith("connections_hub.html"))
        self.assertTrue(str(arr_connections_page().path).endswith("arr_connections.html"))
        self.assertEqual(download_services_page().headers["location"],"/integrations")

    def test_navigation_uses_new_display_name_with_stable_id(self):
        shell=(ROOT/"shell.js").read_text()
        self.assertIn("{id:'connections',href:'/integrations',name:'Integrations'",shell)
        self.assertNotIn("href:'/connections',name:'Connections'",shell)
        self.assertIn(("connections","Integrations"),NAV)
        self.assertEqual(set(CONNECTION_SERVICE_IDS),{"radarr","sonarr","lidarr","sabnzbd","plex","opensubtitles","time-adrift"})

    def test_hub_and_server_settings_use_integrations_label(self):
        hub=(ROOT/"connections_hub.html").read_text()
        settings=(ROOT/"arr_connections.html").read_text()
        landing=(ROOT/"settings_hub.html").read_text()
        self.assertIn("<h1>Integrations</h1>",hub)
        self.assertIn("<h1>Integrations</h1>",settings)
        self.assertIn("Show in Integrations",settings)
        self.assertIn("Manage integrations",hub)
        self.assertIn('href="/settings/integrations"',landing)
        self.assertIn("<h2>Integrations</h2>",landing)
        self.assertNotIn("<h1>Connections</h1>",hub)

    def test_visibility_api_and_saved_preference_id_do_not_change(self):
        sidebar=(ROOT/"sidebar_settings.py").read_text()
        hub=(ROOT/"connections_hub.html").read_text()
        self.assertIn('CONNECTION_HIDDEN_KEY = "connections_hub_hidden"',sidebar)
        self.assertIn('@router.get("/connections/visibility")',sidebar)
        self.assertIn('@router.put("/connections/visibility")',sidebar)
        self.assertIn("'/api/settings/connections/visibility'",hub)

if __name__=="__main__":
    unittest.main()
