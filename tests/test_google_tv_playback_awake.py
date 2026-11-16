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

    def test_unknown_duration_progress_is_saved_and_errors_are_visible(self):
        src = (ANDROID / "PlayerActivity.kt").read_text()
        self.assertIn("val knownDuration = currentDuration().takeIf", src)
        self.assertIn('put("duration_seconds", knownDuration)', src)
        self.assertIn("else position", src)
        self.assertIn('resolveUrl("/api/playback/progress")', src)
        self.assertIn("if (status in 200..299) return null", src)
        self.assertIn("Playback progress was not saved", src)
        self.assertIn("saveProgress(false)", src)

    def test_native_progress_saves_post_and_reports_real_failures(self):
        player = (ANDROID / "PlayerActivity.kt").read_text()
        server = (ROOT / "server" / "home.py").read_text()
        self.assertIn('connection.requestMethod = "POST"', player)
        self.assertIn('@router.post("/playback/progress")', server)
        self.assertIn("connection.readTimeout = 12_000", player)
        self.assertIn('lastFailure = "HTTP $status"', player)
        self.assertIn("error.javaClass.simpleName", player)
        self.assertIn("if (status < 500) break", player)
        self.assertIn("if (network.isShutdown) return", player)
        self.assertIn("network.execute {", player)

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
