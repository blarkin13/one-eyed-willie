"""Official integration branding stays local and recognizable."""
import unittest
from pathlib import Path
from fastapi import HTTPException
from server.main import integration_brand_svg

ROOT = Path(__file__).resolve().parents[1] / "server"


class IntegrationLogoTests(unittest.TestCase):
    def test_uses_upstream_svg_files(self):
        for brand in ("radarr", "sonarr"):
            svg = (ROOT / f"{brand}-official.svg").read_text()
            self.assertTrue(svg.startswith("<svg"))
            self.assertIn("<path", svg)
            self.assertNotIn("<script", svg)
            response = integration_brand_svg(brand)
            self.assertEqual(response.media_type, "image/svg+xml")
            self.assertTrue(str(response.path).endswith(f"{brand}-official.svg"))

    def test_logo_route_cannot_access_other_files(self):
        for bad in ("../../config", "radarr.svg", "other", "Radarr"):
            with self.assertRaises(HTTPException):
                integration_brand_svg(bad)

    def test_sidebar_and_manager_actions_use_real_logos(self):
        shell = (ROOT / "shell.js").read_text()
        self.assertIn("'/assets/brand/'+item.id+'.svg'", shell)
        self.assertIn("className='integration-logo'", shell)
        for filename in ("manager_dashboard.html", "arr_connections.html"):
            page = (ROOT / filename).read_text()
            self.assertIn("/assets/brand/radarr.svg", page)
            self.assertIn("/assets/brand/sonarr.svg", page)
        credit = (ROOT / "credit_detail.html").read_text()
        self.assertIn("'/assets/brand/'+provider+'.svg'", credit)
        self.assertNotIn("fa-bullseye", credit)


if __name__ == "__main__":
    unittest.main()
