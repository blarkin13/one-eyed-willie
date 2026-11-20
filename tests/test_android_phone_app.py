"""Yarr Media for Android phones is a separate app built from the TV app's code.

Source-level guards: the phone app has its own identity and launcher entry,
and every phone-only behaviour in the shared code is gated so the Google TV
app is unchanged.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TV = ROOT / "google-tv"
PHONE_GRADLE = (TV / "phone/build.gradle.kts").read_text()
PHONE_MANIFEST = (TV / "phone/src/main/AndroidManifest.xml").read_text()
TV_GRADLE = (TV / "app/build.gradle.kts").read_text()
TV_MANIFEST = (TV / "app/src/main/AndroidManifest.xml").read_text()
SRC = TV / "app/src/main/java/studio/oneeyedwillie/tv"
MAIN = (SRC / "MainActivity.kt").read_text()
PLAYER = (SRC / "PlayerActivity.kt").read_text()


class SeparateAppTests(unittest.TestCase):
    def test_phone_is_its_own_app(self):
        self.assertIn('include(":app", ":phone")', (TV / "settings.gradle.kts").read_text())
        self.assertIn('applicationId = "media.yarr.android"', PHONE_GRADLE)
        self.assertIn('applicationId = "studio.oneeyedwillie.tv"', TV_GRADLE)
        self.assertIn('const val TV_PACKAGE = "studio.oneeyedwillie.tv"', (SRC / "AppKind.kt").read_text())

    def test_phone_reuses_the_tv_code_and_artwork(self):
        self.assertIn('java.srcDirs("../app/src/main/java")', PHONE_GRADLE)
        self.assertIn('res.srcDirs("../app/src/main/res")', PHONE_GRADLE)
        for artifact in ("media3-exoplayer", "media3-exoplayer-hls", "media3-ui"):
            self.assertIn('"androidx.media3:%s:' % artifact, PHONE_GRADLE)

    def test_phone_manifest_is_a_normal_launcher_app(self):
        self.assertIn("android.intent.category.LAUNCHER", PHONE_MANIFEST)
        self.assertNotIn("LEANBACK", PHONE_MANIFEST)
        self.assertNotIn("leanback", PHONE_MANIFEST)
        self.assertIn('android:screenOrientation="sensorLandscape"', PHONE_MANIFEST)
        main = PHONE_MANIFEST[PHONE_MANIFEST.index('android:name=".MainActivity"'):]
        self.assertNotIn("screenOrientation", main.split("</activity>")[0])

    def test_tv_manifest_is_unchanged(self):
        self.assertIn('android:name="android.software.leanback" android:required="true"', TV_MANIFEST)
        self.assertIn("android.intent.category.LEANBACK_LAUNCHER", TV_MANIFEST)
        self.assertNotIn("android.intent.category.LAUNCHER", TV_MANIFEST)


class TvBehaviourIsGatedTests(unittest.TestCase):
    def test_tv_only_behaviour_stays_tv_only(self):
        self.assertIn('if (isTv && !userAgentString.contains("OneEyedWillieTV/1"))', MAIN)
        self.assertIn("if (isTv) installRemoteNavigation(web)", MAIN)
        self.assertIn("if (playedStartupSound || !isTv) return", MAIN)
        self.assertRegex(MAIN, r"if \(isTv\) \{\s+window\.decorView\.systemUiVisibility")

    def test_phone_only_behaviour_is_behind_the_check(self):
        self.assertIn('if (!isTv && !userAgentString.contains("YarrMediaAndroid/1"))', MAIN)
        self.assertIn("if (!AppKind.isTv(this)) playerView.setOnClickListener", PLAYER)
        self.assertIn('if (isTv) "google_tv" else "android"', MAIN)

    def test_settings_page_offers_the_phone_its_connection_settings(self):
        hub = (ROOT / "server/settings_hub.html").read_text()
        self.assertIn("YarrMediaAndroid/1", hub)
        self.assertIn("prompt('oewtv:settings:server','')", hub)


class DistributionTests(unittest.TestCase):
    def test_ci_and_release_build_the_phone_app(self):
        ci = (ROOT / ".github/workflows/google-tv.yml").read_text()
        self.assertIn(":phone:assembleDebug :phone:assembleLean", ci)
        self.assertIn("yarr-media-android-lean-apk", ci)
        release = (ROOT / ".github/workflows/release.yml").read_text()
        self.assertIn(":phone:assembleLean", release)
        self.assertEqual(release.count("dist/yarr-media-android.apk"), 3)


if __name__ == "__main__":
    unittest.main()
