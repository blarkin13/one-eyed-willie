"""TV launcher uses separate crisp icon and actual 16:9 banner assets."""
from pathlib import Path
import struct
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
ANDROID = ROOT / "google-tv/app/src/main"
MANIFEST = ANDROID / "AndroidManifest.xml"
ICON = ANDROID / "res/drawable/yarr_tv_crisp_icon.xml"
BANNER = ANDROID / "res/drawable-nodpi/yarr_tv_banner.png"
ICON_SOURCE = ROOT / "google-tv/artwork/yarr_tv_crisp_icon.svg"
BANNER_SOURCE = ROOT / "google-tv/artwork/yarr_tv_banner.svg"
ORIGINAL_ICON = ANDROID / "res/drawable-nodpi/yarr_media_launcher.png"
ORIGINAL_VECTOR = ANDROID / "res/drawable/yarr_media_launcher_vector.xml"
ANDROID_NS = "{http://schemas.android.com/apk/res/android}"


class LauncherArtworkTests(unittest.TestCase):
    def test_tv_launcher_icon_and_banner_both_declared(self):
        manifest = MANIFEST.read_text()
        self.assertIn('android:icon="@drawable/yarr_tv_crisp_icon"', manifest)
        self.assertIn('android:roundIcon="@drawable/yarr_tv_crisp_icon"', manifest)
        self.assertIn('android:banner="@drawable/yarr_tv_banner"', manifest)
        self.assertIn('android:label="Yarr Media"', manifest)

    def test_round_icon_is_simplified_crisp_vector(self):
        vector = ET.parse(ICON).getroot()
        self.assertEqual(vector.tag, "vector")
        self.assertEqual(vector.attrib[ANDROID_NS + "viewportWidth"], "512")
        self.assertEqual(vector.attrib[ANDROID_NS + "viewportHeight"], "512")
        paths = list(vector)
        self.assertEqual(
            [path.attrib[ANDROID_NS + "fillColor"] for path in paths],
            ["#FFFFFF", "#000000", "#9B9B9B"],
        )
        self.assertTrue(all("C" in path.attrib[ANDROID_NS + "pathData"] for path in paths[1:]))
        self.assertLess(ICON.stat().st_size, 4_000)
        self.assertNotIn("YARR.MEDIA", ICON.read_text())

    def test_banner_is_large_and_correct_aspect(self):
        data = BANNER.read_bytes()
        self.assertTrue(data.startswith(bytes.fromhex("89504e470d0a1a0a")))
        width, height = struct.unpack(">II", data[16:24])
        self.assertEqual((width, height), (1280, 720))
        self.assertEqual(width * 9, height * 16)
        self.assertLess(len(data), 120_000)

    def test_vector_artwork_and_original_graphics_remain_editable(self):
        self.assertIn('viewBox="0 0 512 512"', ICON_SOURCE.read_text())
        svg = BANNER_SOURCE.read_text()
        self.assertIn('viewBox="0 0 640 360"', svg)
        self.assertIn('fill="#A61E1E"', svg)
        self.assertIn('fill="#F5F1E8"', svg)
        self.assertTrue(ORIGINAL_ICON.exists())
        self.assertTrue(ORIGINAL_VECTOR.exists())
        self.assertTrue((ANDROID / "res/drawable-nodpi/tv_loading_screen.png").exists())


if __name__ == "__main__":
    unittest.main()
