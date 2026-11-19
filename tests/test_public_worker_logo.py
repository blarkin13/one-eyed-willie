"""Public Yarr Media site uses the same moon-and-sail mark as the app."""
from pathlib import Path
import unittest
ROOT = Path(__file__).resolve().parents[1]
class PublicWorkerLogoTests(unittest.TestCase):
    def test_logo(self):
        worker = (ROOT / "cloudflare/yarr/worker.js").read_text()
        self.assertIn("const YARR_ICON_SVG =", worker)
        self.assertIn("u.pathname==='/favicon.svg'", worker)
        self.assertIn('rel="icon" type="image/svg+xml"', worker)
        self.assertIn('/favicon.svg?v=moon-sail-v1', worker)
        self.assertIn('new%20logo.png', worker)
        self.assertNotIn('ship-float', worker)
        self.assertIn('class="hero-art"', worker)
        self.assertIn("img-src 'self'", worker)
