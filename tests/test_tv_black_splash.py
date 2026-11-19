"""Google TV starts with the approved Yarr Media image and black surfaces."""
from pathlib import Path
import struct
import unittest

ROOT = Path(__file__).resolve().parents[1]
TV = ROOT / "google-tv/app/src/main"
MAIN = TV / "java/studio/oneeyedwillie/tv/MainActivity.kt"
PLAYER = TV / "java/studio/oneeyedwillie/tv/PlayerActivity.kt"
SERVER = ROOT / "server/main.py"
SPLASH = TV / "res/drawable-nodpi/tv_loading_screen.png"


class TvBlackSplashTests(unittest.TestCase):
    def test_uploaded_splash_is_packaged_at_4k(self):
        data = SPLASH.read_bytes()
        self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(struct.unpack(">II", data[16:24]), (3840, 2160))
        self.assertLess(len(data), 500_000)
        self.assertIn("R.drawable.tv_loading_screen", MAIN.read_text())

    def test_webview_uses_black_surfaces_and_backdrop_gradients(self):
        app = MAIN.read_text()
        server = SERVER.read_text()
        self.assertIn("--panel:#000000!important", app)
        self.assertIn("--panel:#000000!important", server)
        self.assertIn("background:#000000!important", app)
        self.assertNotIn("#0d1520f5", app)
        self.assertNotIn("#080d16", app)
        self.assertIn("var(--oew-tv-select-color,#A61E1E)", app)

    def test_native_player_controls_are_neutral(self):
        player = PLAYER.read_text()
        self.assertIn("0xDB000000", player)
        self.assertIn("0xF0000000", player)
        self.assertNotIn("0xDB090B10", player)
        self.assertNotIn("0xF00B111C", player)


if __name__ == "__main__":
    unittest.main()
