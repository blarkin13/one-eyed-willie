"""The Yarr Media logo stays consistent in the sidebar, PWA, and Android TV launcher."""
import io
import unittest
from pathlib import Path

from PIL import Image
from server.brand_icon import brand_ico, brand_png

ROOT = Path(__file__).resolve().parents[1]


class BrandIconTests(unittest.TestCase):
    def test_generated_png_dimensions_and_transparency(self):
        for size in (128, 180, 192, 512):
            with self.subTest(size=size):
                icon = Image.open(io.BytesIO(brand_png(size)))
                self.assertEqual(icon.size, (size, size))
                self.assertEqual(icon.mode, "RGBA")
                self.assertEqual(icon.getpixel((0, 0))[3], 0)
                self.assertGreater(icon.getpixel((size // 2, size // 4))[3], 200)

    def test_favicon_contains_standard_sizes(self):
        ico = Image.open(io.BytesIO(brand_ico()))
        self.assertEqual(ico.info["sizes"], {(16, 16), (32, 32), (48, 48), (64, 64)})

    def test_android_launcher_uses_same_vector_art(self):
        # The TV launcher now uses a simplified, crisp icon (see
        # test_tv_launcher_icon); the full-detail logo vector is kept as a
        # resource and must still match the site's logo.
        manifest = (ROOT / "google-tv/app/src/main/AndroidManifest.xml").read_text()
        self.assertIn('android:icon="@drawable/yarr_tv_crisp_icon"', manifest)
        android = (ROOT / "google-tv/app/src/main/res/drawable/yarr_media_icon.xml").read_text()
        svg = (ROOT / "server/logo.svg").read_text()
        self.assertIn(svg.split('d="M')[1].split('"')[0], android)


if __name__ == "__main__":
    unittest.main()
