"""New moon-and-sail Yarr Media OG image and social metadata."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKER = (ROOT / "cloudflare/yarr/worker.js").read_text()
HOME = (ROOT / "server/dashboard.html").read_text()
SERVER = (ROOT / "server/main.py").read_text()
ASSET = ROOT / "server/yarr-media-og-v2.jpg"
URL = "https://yarr.media/assets/yarr-media-og-v2.jpg"


class SocialPreviewTests(unittest.TestCase):
    def test_image_is_standard_share_card_size(self):
        from PIL import Image
        with Image.open(ASSET) as im:
            self.assertEqual(im.size, (1200, 630))
            self.assertEqual(im.format, "JPEG")
        self.assertLess(ASSET.stat().st_size, 200_000)

    def test_public_website_points_to_versioned_image(self):
        self.assertIn(URL, WORKER)
        self.assertIn('property="og:image"', WORKER)
        self.assertIn('name="twitter:card" content="summary_large_image"', WORKER)
        # Served from the Worker's public asset table (fetched from this repo).
        self.assertIn("'/assets/yarr-media-og-v2.jpg':'yarr-media-og-v2.jpg'", WORKER)

    def test_media_server_uses_same_image(self):
        self.assertEqual(HOME.count(URL), 3)
        self.assertIn('@app.get("/assets/yarr-media-og-v2.jpg")', SERVER)
        self.assertIn('with_name("yarr-media-og-v2.jpg")', SERVER)


if __name__ == "__main__":
    unittest.main()
