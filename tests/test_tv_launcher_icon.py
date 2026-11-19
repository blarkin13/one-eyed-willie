"""Verify the user-approved YarrMedia SVG renders as the TV launcher icon."""
from pathlib import Path
import struct
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
ANDROID = ROOT / "google-tv/app/src/main"
MANIFEST = ANDROID / "AndroidManifest.xml"
ICON = ANDROID / "res/drawable-nodpi/yarrmedia_launcher.png"
ICON_SOURCE = ROOT / "google-tv/artwork/yarrmedia_launcher.svg"
BANNER = ANDROID / "res/drawable-nodpi/yarr_tv_banner.png"
ORIGINAL_ICON = ANDROID / "res/drawable-nodpi/yarr_media_launcher.png"
ORIGINAL_VECTOR = ANDROID / "res/drawable/yarr_media_launcher_vector.xml"


class LauncherArtworkTests(unittest.TestCase):
    def test_tv_launcher_uses_approved_image_and_exact_name(self):
        manifest = MANIFEST.read_text()
        self.assertIn('android:label="YarrMedia"', manifest)
        self.assertIn('android:icon="@drawable/yarrmedia_launcher"', manifest)
        self.assertIn('android:roundIcon="@drawable/yarrmedia_launcher"', manifest)
        self.assertIn('android:banner="@drawable/yarr_tv_banner"', manifest)
        self.assertNotIn('android:icon="@drawable/yarr_tv_crisp_icon"', manifest)

    def test_launcher_raster_from_approved_svg_is_rgba_and_square(self):
        from PIL import Image
        with Image.open(ICON) as image:
            self.assertEqual(image.format, "PNG")
            self.assertEqual(image.size, (1024, 1024))
            self.assertEqual(image.mode, "RGBA")
            self.assertEqual(image.getpixel((0, 0))[3], 0)
            self.assertEqual(image.getpixel((1023, 1023))[3], 0)
            self.assertEqual(image.getpixel((800, 540)), (166, 30, 30, 255))
            self.assertEqual(image.getpixel((460, 616)), (181, 177, 177, 255))
            self.assertEqual(image.getpixel((512, 50)), (255, 255, 255, 255))
        self.assertLess(ICON.stat().st_size, 300_000)

    def test_original_svg_is_preserved_with_crimson_wordmark(self):
        source = ICON_SOURCE.read_text()
        root = ET.fromstring(source)
        self.assertEqual(root.attrib["viewBox"], "0 0 3600 3600")
        colors = {path.attrib.get("fill") for path in root}
        self.assertEqual(
            colors,
            {"rgb(181,177,177)", "#A61E1E", "rgb(255,255,255)", "rgb(0,0,0)"},
        )
        self.assertGreater(source.count('fill="#A61E1E"'), 70)

    def test_banner_and_loading_screen_unchanged(self):
        data = BANNER.read_bytes()
        self.assertTrue(data.startswith(bytes.fromhex("89504e470d0a1a0a")))
        self.assertEqual(struct.unpack(">II", data[16:24]), (1280, 720))
        self.assertTrue(ORIGINAL_ICON.exists())
        self.assertTrue(ORIGINAL_VECTOR.exists())
        self.assertTrue((ANDROID / "res/drawable-nodpi/tv_loading_screen.png").exists())


if __name__ == "__main__":
    unittest.main()
