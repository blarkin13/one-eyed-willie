"""Regression coverage for Android TV screen-on lifecycle during playback."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ANDROID = ROOT / "google-tv" / "app" / "src" / "main" / "java" / "studio" / "oneeyedwillie" / "tv"


class GoogleTvPlaybackAwakeTests(unittest.TestCase):
    def test_native_player_prevents_inactivity_sleep_only_during_playback(self):
        src = (ANDROID / "PlayerActivity.kt").read_text()
        self.assertIn("import android.view.WindowManager", src)
        self.assertIn("private fun updatePlaybackScreenAwake()", src)
        self.assertIn("active != null && active.playWhenReady", src)
        self.assertIn("active.playbackState == Player.STATE_READY", src)
        self.assertIn("active.playbackState == Player.STATE_BUFFERING", src)
        self.assertIn("window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)", src)
        self.assertIn("window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)", src)
        self.assertIn("override fun onPlayWhenReadyChanged(playWhenReady: Boolean, reason: Int)", src)
        self.assertIn("override fun onPlaybackStateChanged(state: Int)", src)
        self.assertIn("visibleForPlayback = false", src)
        self.assertIn("override fun onStop()", src)
        self.assertIn("override fun onStart()", src)
        self.assertIn("override fun onDestroy()", src)

    def test_webview_fallback_releases_screen_after_video_or_navigation(self):
        src = (ANDROID / "MainActivity.kt").read_text()
        self.assertIn('message == "oewtv:awake:1" || message == "oewtv:awake:0"', src)
        self.assertIn("sameOrigin(url) && browser === web", src)
        self.assertIn("web.keepScreenOn = awake", src)
        self.assertIn("document.addEventListener('playing'", src)
        self.assertIn("['pause','ended','emptied']", src)
        self.assertIn(".willie-player video", src)
        self.assertIn("override fun onPageStarted(", src)
        self.assertIn("override fun onPause()", src)
        self.assertIn("browser?.keepScreenOn = false", src)
        self.assertIn("window.__oewTvVideoAwakeHook=true", src)
        self.assertNotIn("android.permission.WAKE_LOCK", src)


if __name__ == "__main__":
    unittest.main()
