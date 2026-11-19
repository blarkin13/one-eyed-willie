"""TV Connections and Settings theme must be remote-accessible and neutral black."""
from pathlib import Path
import unittest

SERVER=Path(__file__).resolve().parents[1]/"server"
HUB=(SERVER/"connections_hub.html").read_text()
TV=(SERVER/"tv_settings.html").read_text()
MANAGER=(SERVER/"manager_dashboard.html").read_text()
SHELL=(SERVER/"shell.js").read_text()


class TvConnectionsAndAppearanceTests(unittest.TestCase):
    def test_api_only_integrations_are_selectable_on_tv(self):
        self.assertIn("service.dashboard?'a':'button'", HUB)
        self.assertIn("card.addEventListener('click',()=>showServiceDetails(service))", HUB)
        self.assertIn("visibility.visible?.[service.id]===false", HUB)
        self.assertIn("id=\"connection-plex-clone\"", HUB)
        self.assertIn("status('/api/plex/import/preview')", HUB)
        self.assertIn("statusPost('/api/plex/import',{confirm:true})", HUB)
        self.assertIn("serviceDialog.showModal()", HUB)
        self.assertIn("id=\"connections-manage\"", HUB)
        self.assertIn("document.getElementById('connections-manage')?.remove()", HUB)

    def test_tv_connection_focus_uses_configured_color(self):
        self.assertIn("body[data-page=\"connectionshub\"].oew-tv-client", HUB)
        self.assertIn("outline:2px solid var(--oew-tv-select-color,#A61E1E)!important", HUB)
        self.assertIn("border-color:var(--oew-tv-select-color,#A61E1E)!important", HUB)
        self.assertIn("serviceLogo(service)", HUB)
        self.assertIn("var(--oew-tv-select-color,#A61E1E)", HUB)
        self.assertNotIn("#a78bfa", HUB)

    def test_connection_dashboards_keep_active_sidebar_icon(self):
        self.assertIn("'radarr','sonarr','sabnzbd'", SHELL)
        self.assertIn("?'connections':inSettings?'settings':page", SHELL)

    def test_manager_dashboard_has_service_brand_logo(self):
        self.assertIn('id="manager-logo"', MANAGER)
        self.assertIn("'/assets/brand/'+managerName+'.svg'", MANAGER)

    def test_tv_theme_picker_matches_server_and_is_local(self):
        for value in ("clean","pirate","adventure"):
            self.assertIn("['"+value+"'", TV)
        self.assertIn("localStorage.setItem(iconThemeKey,theme)", TV)
        self.assertIn("const iconThemeKey='willie-icon-theme'", TV)
        self.assertIn("location.reload()", TV)
        self.assertIn('id="tv-icon-theme-dialog"', TV)

    def test_tv_settings_no_longer_uses_navy(self):
        for old in ("#142131f2","#101b2af2","#18283a","#263d58","#263c57","#0a1828f5"):
            self.assertNotIn(old, TV)
        self.assertIn("backdrop-filter:blur(18px)", TV)
        self.assertIn("background-color:#333333!important", TV)
        self.assertIn("var(--oew-tv-select-color,#A61E1E)", TV)


if __name__=="__main__":
    unittest.main()
