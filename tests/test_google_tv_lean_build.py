"""The TV APK carries only what it uses, and starts without avoidable work.

Source-level guards: the real effect (size, first frame) needs a TV.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TV = ROOT / "google-tv"
GRADLE = (TV / "app/build.gradle.kts").read_text()
DEPENDENCIES = "\n".join(l for l in GRADLE.splitlines() if l.strip().startswith(
    ("implementation(", "testImplementation(", "id(")))
MAIN = (TV / "app/src/main/java/studio/oneeyedwillie/tv/MainActivity.kt").read_text()
SOURCES = "\n".join(p.read_text() for p in (TV / "app/src").rglob("*.kt"))


class UnusedLibrariesTests(unittest.TestCase):
    def test_nothing_imports_compose_tv_material_or_coil(self):
        self.assertNotRegex(SOURCES, r"^import (androidx\.compose|androidx\.tv|coil)", )
        self.assertNotIn("@Composable", SOURCES)

    def test_those_libraries_are_not_bundled(self):
        for name in ("compose", "tv-material", "coil", "material3"):
            self.assertNotIn(name, DEPENDENCIES, name)
        self.assertNotIn("compose", (TV / "build.gradle.kts").read_text())

    def test_the_activity_library_the_app_needs_is_declared_directly(self):
        self.assertRegex(GRADLE, r'implementation\("androidx\.activity:activity:[\d.]+"\)')
        self.assertIn("import androidx.activity.ComponentActivity", MAIN)

    def test_media3_is_still_there(self):
        for artifact in ("media3-exoplayer", "media3-exoplayer-hls", "media3-ui"):
            self.assertIn('"androidx.media3:%s:' % artifact, GRADLE)


class LeanBuildTests(unittest.TestCase):
    def test_lean_build_is_shrunk_and_not_debuggable_and_debug_is_untouched(self):
        lean = GRADLE[GRADLE.index('create("lean")'):]
        lean = lean[:lean.index("\n        }")]
        self.assertIn('initWith(getByName("debug"))', lean)
        self.assertIn("isDebuggable = false", lean)
        self.assertIn("isMinifyEnabled = true", lean)
        self.assertIn("isShrinkResources = true", lean)
        self.assertNotIn("isDebuggable", GRADLE.replace(lean, ""))

    def test_the_js_bridge_survives_shrinking(self):
        rules = (TV / "app/proguard-rules.pro").read_text()
        self.assertIn("@android.webkit.JavascriptInterface <methods>", rules)
        self.assertIn("-dontobfuscate", rules)
        self.assertIn("@JavascriptInterface", MAIN)

    def test_ci_builds_and_uploads_both_apks(self):
        workflow = (ROOT / ".github/workflows/google-tv.yml").read_text()
        self.assertIn(":app:assembleDebug", workflow)
        self.assertIn(":app:assembleLean", workflow)
        self.assertIn("yarr-media-google-tv-debug-apk", workflow)
        self.assertIn("yarr-media-google-tv-lean-apk", workflow)


class StartupWorkTests(unittest.TestCase):
    def test_startup_sounds_are_prepared_off_the_main_thread(self):
        body = MAIN[MAIN.index("private fun playStartupSoundOnce()"):]
        body = body[:body.index("private fun restoreSplashArt()")]
        self.assertIn("Thread({", body)
        self.assertLess(body.index("Thread({"), body.index("MediaPlayer.create(this"))
        self.assertIn("isDestroyed", body)          # a late sound must not leak
        self.assertIn("CopyOnWriteArrayList<MediaPlayer>", MAIN)

    def test_the_splash_bitmap_is_released_when_the_splash_ends(self):
        finish = MAIN[MAIN.index("private fun finishLoading("):]
        finish = finish[:finish.index("private fun finishTvTextEditing")]
        self.assertIn("loadingArt?.setImageDrawable(null)", finish)

    def test_the_splash_art_comes_back_wherever_the_overlay_is_shown_again(self):
        for signature in ("private fun showLoading()", "private fun showLoadingFailure(",
                          "private fun discoverLocalServer()"):
            start = MAIN.index(signature)
            body = MAIN[start:start + 1500]
            self.assertIn("restoreSplashArt()", body, signature)
            shown = body.index("loadingOverlay?.apply") if "loadingOverlay?.apply" in body \
                else body.index("loadingOverlay?.visibility = View.VISIBLE")
            self.assertLess(body.index("restoreSplashArt()"), shown, signature)


if __name__ == "__main__":
    unittest.main()
