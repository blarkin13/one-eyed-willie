"""Regression checks for Select/OK playback hand-off and native menu styling.

The native Android build is also compiled through the Google TV APK workflow.
"""
import unittest
from pathlib import Path

PLAYER = (Path(__file__).resolve().parents[1] / "google-tv" / "app" /
          "src" / "main" / "java" / "studio" / "oneeyedwillie" /
          "tv" / "PlayerActivity.kt")


class NativePlayerSelectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = PLAYER.read_text()

    def test_first_select_pauses_and_focuses_play(self):
        src = self.source
        self.assertIn('val controlsHidden = chrome.visibility != View.VISIBLE', src)
        self.assertIn('focused === timeline', src)
        self.assertIn('controlsHidden || videoSelected || focused === playButton', src)
        self.assertIn('if (active?.isPlaying == true) active.pause() else active?.play()', src)
        self.assertIn('playButton.requestFocus()', src)
        self.assertIn('applyPlayerSelectionColor(selectedColor)', src)

    def test_key_up_is_consumed_after_focus_change(self):
        src = self.source
        self.assertIn('private var consumedPlaybackSelect = false', src)
        self.assertIn('if (selectKey && event.action == KeyEvent.ACTION_UP && consumedPlaybackSelect)', src)
        self.assertIn('consumedPlaybackSelect = false', src)
        self.assertIn('consumedPlaybackSelect = true', src)
        self.assertNotIn(
            'event.action == KeyEvent.ACTION_UP &&\n'
            '                (focused == null || focused === timeline || focused === playerView)',
            src,
        )

    def test_back_is_not_activated_by_playback_select(self):
        src = self.source
        before = src.index('val selectKey = direction == KeyEvent.KEYCODE_DPAD_CENTER')
        consumed = src.index('if (selectKey && event.action == KeyEvent.ACTION_UP', before)
        passed = src.index('return super.dispatchKeyEvent(event)', consumed)
        self.assertLess(consumed, passed)

    def test_menus_use_translucent_dark_remote_style(self):
        # Check the look (a translucent dark panel that dims the video and
        # shows focus in the selection colour), not exact colour values, so
        # restyling the menus does not break this test.
        import re
        src = self.source
        self.assertIn('private fun showPlayerMenu(', src)
        panel = re.search(r'cornerRadius = dp\(\d+\)\.toFloat\(\)\s+setColor\(0x([0-9A-Fa-f]{8})\.toInt\(\)\)', src)
        self.assertIsNotNone(panel, 'menu panel colour not found')
        argb = int(panel.group(1), 16)
        alpha, red, green, blue = (argb >> 24) & 255, (argb >> 16) & 255, (argb >> 8) & 255, argb & 255
        self.assertTrue(200 <= alpha < 255, 'panel should be translucent')
        self.assertLess(max(red, green, blue), 60, 'panel should be dark')
        dim = re.search(r'setDimAmount\(([0-9.]+)f\)', src)
        self.assertIsNotNone(dim)
        self.assertTrue(0.2 <= float(dim.group(1)) <= 0.8)
        self.assertIn('setBackgroundDrawable(ColorDrawable(Color.TRANSPARENT))', src)
        self.assertRegex(src, r'setColor\(if \(focused[^)]*\) selectedColor else Color\.TRANSPARENT\)')
        self.assertIn('isFocusableInTouchMode = true', src)

    def test_all_player_menus_share_style(self):
        src = self.source
        for name in (
            'showPlayerMenu("Playback options"',
            'showPlayerMenu("Closed Captions"',
            'showPlayerMenu("Search subtitle language"',
            'showPlayerMenu("OpenSubtitles results"',
            'showPlayerMenu("Playback diagnostics"',
        ):
            self.assertIn(name, src)
        self.assertNotIn('AlertDialog.Builder(this).setTitle("Closed Captions")', src)


if __name__ == "__main__":
    unittest.main()
