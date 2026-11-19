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
        self.assertIn('class="site-brand-label">YARR<span class="brand-dot">.</span><span class="brand-media">MEDIA</span>', worker)
        self.assertIn('src="/favicon.svg?v=moon-sail-v1"', worker)
        self.assertIn('class="hero-art" src="https://raw.githubusercontent.com/', worker)
        self.assertIn('class="brand-label">YARR<span class="brand-dot">.</span><span class="brand-media">MEDIA</span>', worker)
        self.assertIn('.brand-dot{color:#9b9b9b}', worker)
        self.assertIn('.brand-media{color:#c62838}', worker)
        self.assertIn("font-weight:900;letter-spacing:.01em", worker)
        self.assertIn("font-size:clamp(18px,1.8vw,23px);font-weight:900", worker)
        self.assertIn("img-src 'self'", worker)
