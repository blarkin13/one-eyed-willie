"""Verify the four-color vector launcher is used instead of a downscaled raster."""
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ANDROID = ROOT / "google-tv/app/src/main"
MANIFEST = ANDROID / "AndroidManifest.xml"
VECTOR = ANDROID / "res/drawable/yarr_media_launcher_vector.xml"
SOURCE = ROOT / "google-tv/artwork/yarr_media_launcher.svg"
ORIGINAL = ANDROID / "res/drawable-nodpi/yarr_media_launcher.png"
ANDROID_NS = "{http://schemas.android.com/apk/res/android}"


class LauncherArtworkTests(unittest.TestCase):
    def test_launcher_uses_vector_for_both_entry_points(self):
        manifest = MANIFEST.read_text()
        self.assertIn('android:icon="@drawable/yarr_media_launcher_vector"', manifest)
        self.assertIn('android:roundIcon="@drawable/yarr_media_launcher_vector"', manifest)
        self.assertIn('android:label="Yarr Media"', manifest)
        self.assertNotIn('android:icon="@drawable/yarr_media_launcher"', manifest)

    def test_vector_matches_original_four_color_palette(self):
        root = ET.parse(VECTOR).getroot()
        self.assertEqual(root.tag, "vector")
        self.assertEqual(root.attrib[ANDROID_NS + "viewportWidth"], "1800")
        self.assertEqual(root.attrib[ANDROID_NS + "viewportHeight"], "1800")
        paths = list(root)
        self.assertEqual(len(paths), 4)
        self.assertEqual(
            [path.attrib[ANDROID_NS + "fillColor"] for path in paths],
            ["#FFFFFF", "#000000", "#9B9B9B", "#A61E1E"],
        )
        for path in paths:
            self.assertEqual(path.attrib[ANDROID_NS + "fillType"], "evenOdd")
            self.assertTrue(path.attrib[ANDROID_NS + "pathData"])
        self.assertLess(VECTOR.stat().st_size, 32_000)

    def test_editable_svg_and_original_assets_are_preserved(self):
        self.assertTrue(SOURCE.exists())
        svg = SOURCE.read_text()
        self.assertIn('viewBox="0 0 1800 1800"', svg)
        self.assertIn('fill="#A61E1E"', svg)
        self.assertTrue(ORIGINAL.is_file())
        self.assertTrue((ANDROID / "res/drawable-nodpi/tv_loading_screen.png").exists())


if __name__ == "__main__":
    unittest.main()
