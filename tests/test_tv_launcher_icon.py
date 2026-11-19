"""Verify the original transparent YARR.MEDIA launcher artwork is installed."""
import struct
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ANDROID = ROOT / "google-tv/app/src/main"
MANIFEST = ANDROID / "AndroidManifest.xml"
LAUNCHER = ANDROID / "res/drawable-nodpi/yarr_media_launcher.png"


class LauncherArtworkTests(unittest.TestCase):
    def test_launcher_uses_supplied_round_image(self):
        manifest = MANIFEST.read_text()
        self.assertIn('android:icon="@drawable/yarr_media_launcher"', manifest)
        self.assertIn('android:roundIcon="@drawable/yarr_media_launcher"', manifest)
        self.assertIn('android:label="Yarr Media"', manifest)

    def test_round_artwork_is_original_rgba_png(self):
        data = LAUNCHER.read_bytes()
        self.assertEqual(data[:8], b"\\x89PNG\\r\\n\\x1a\\n")
        self.assertEqual(struct.unpack(">II", data[16:24]), (1800, 1800))
        self.assertEqual(data[25], 6)  # RGBA with alpha: transparent corners
        self.assertLess(len(data), 100_000)

    def test_splash_is_still_a_separate_resource(self):
        self.assertTrue((ANDROID / "res/drawable-nodpi/tv_loading_screen.png").exists())


if __name__ == "__main__":
    unittest.main()
