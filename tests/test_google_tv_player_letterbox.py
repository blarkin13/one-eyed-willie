"""The TV player's letterbox/pillarbox bands must be black, not the theme grey.

The bands are whatever lies behind the video view, so the window, the root
layout and the PlayerView itself must all be black. This is a source-level
guard (the real rendering needs a TV); the web player's black background is
checked against its stylesheet.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLAYER = (ROOT / "google-tv/app/src/main/java/studio/oneeyedwillie/tv/PlayerActivity.kt").read_text()


class LetterboxColorTests(unittest.TestCase):
    def test_tv_window_root_and_player_view_are_black(self):
        self.assertIn("window.setBackgroundDrawable(ColorDrawable(Color.BLACK))", PLAYER)
        root = PLAYER[PLAYER.index("val surface = FrameLayout(this)"):]
        self.assertIn("setBackgroundColor(Color.BLACK)", root[:80])
        view = root[root.index("playerView = PlayerView(this)"):][:300]
        self.assertIn("setBackgroundColor(Color.BLACK)", view)
        self.assertIn("setShutterBackgroundColor(Color.BLACK)", view)

    def test_web_player_bands_are_black(self):
        css = (ROOT / "server/player.js").read_text()
        self.assertRegex(css, r"\.willie-player\{[^}]*background:#000")
        self.assertRegex(css, r"\.willie-video\{[^}]*object-fit:contain;background:#000")


if __name__ == "__main__":
    unittest.main()
