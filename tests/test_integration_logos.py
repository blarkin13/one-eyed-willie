"""Official integration branding stays local and recognizable."""
import unittest
from pathlib import Path
from fastapi import HTTPException
from server.main import integration_brand_svg

ROOT = Path(__file__).resolve().parents[1] / "server"


class IntegrationLogoTests(unittest.TestCase):
    def test_uses_upstream_svg_files(self):
        for brand in ("radarr", "sonarr", "sabnzbd"):
            svg = (ROOT / f"{brand}-official.svg").read_text()
            self.assertTrue(svg.startswith("<svg"))
            self.assertIn("<path", svg)
            self.assertNotIn("<script", svg)
            response = integration_brand_svg(brand)
            self.assertEqual(response.media_type, "image/svg+xml")
            self.assertTrue(str(response.path).endswith(f"{brand}-official.svg"))

    def test_download_service_tabs_are_identical_and_sabnzbd_first(self):
        from html.parser import HTMLParser

        class ServiceTabs(HTMLParser):
            def __init__(self):
                super().__init__()
                self.in_nav = False
                self.links = []
                self.logos = []

            def handle_starttag(self, tag, attrs):
                attrs = dict(attrs)
                if tag == "nav" and attrs.get("class") == "service-switcher":
                    self.in_nav = True
                elif self.in_nav and tag == "a":
                    self.links.append(attrs.get("href"))
                elif self.in_nav and tag == "img":
                    self.logos.append(attrs.get("src"))

            def handle_endtag(self, tag):
                if tag == "nav":
                    self.in_nav = False

        for filename in ("manager_dashboard.html", "sab_dashboard.html"):
            content = (ROOT / filename).read_text()
            parsed = ServiceTabs()
            parsed.feed(content)
            self.assertEqual(parsed.links, ["/sabnzbd", "/radarr", "/sonarr"], filename)
            self.assertEqual(parsed.logos, [
                "/assets/brand/sabnzbd.svg",
                "/assets/brand/radarr.svg",
                "/assets/brand/sonarr.svg",
            ], filename)
            self.assertNotIn("Manage connections", content)
        css = (ROOT / "ui.css").read_text()
        self.assertIn(".service-switcher", css)

    def test_logo_route_cannot_access_other_files(self):
        for bad in ("../../config", "radarr.svg", "other", "Radarr"):
            with self.assertRaises(HTTPException):
                integration_brand_svg(bad)

    def test_sidebar_and_manager_actions_use_real_logos(self):
        shell = (ROOT / "shell.js").read_text()
        # The sidebar offers only SABnzbd among the integrations (Radarr and
        # Sonarr are managed from Settings), drawn with the shared sidebar icon
        # set; the real brand logos are used on the manager pages below.
        self.assertIn("{id:'sabnzbd',href:'/sabnzbd',name:'SABnzbd'", shell)
        self.assertNotIn("{id:'radarr'", shell)
        self.assertNotIn("{id:'sonarr'", shell)
        for filename in ("manager_dashboard.html", "arr_connections.html",
                         "services.html"):
            page = (ROOT / filename).read_text()
            for brand in ("radarr", "sonarr", "sabnzbd"):
                self.assertIn(f"/assets/brand/{brand}.svg", page, filename)
        sab = (ROOT / "sab_dashboard.html").read_text()
        self.assertIn("/assets/brand/sabnzbd.svg", sab)
        self.assertIn("SABnzbd Team", sab)
        self.assertIn("name and icon", sab)
        svg = (ROOT / "sabnzbd-official.svg").read_text()
        self.assertIn('viewBox="0 0 608 608"', svg)
        self.assertIn('#FFB300', svg)
        self.assertIn('#FFCA28', svg)
        self.assertIn("SABnzbd name and icon", (ROOT.parent / "README.md").read_text())
        credit = (ROOT / "credit_detail.html").read_text()
        self.assertIn("'/assets/brand/'+provider+'.svg'", credit)
        self.assertNotIn("fa-bullseye", credit)


if __name__ == "__main__":
    unittest.main()
