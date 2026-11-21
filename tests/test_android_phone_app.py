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
    def test_signed_out_phone_away_from_home_is_offered_sign_in(self):
        # A fresh phone install only knows the home address; when that can't be
        # reached it must point to signing in rather than a dead end.
        self.assertIn('if (!isTv) addView(loadingSignIn', MAIN)
        self.assertIn('setOnClickListener { startYarrSignIn() }', MAIN)
        self.assertIn("Sign in to Yarr Media to watch away from home.", MAIN)
        # After signing in from the failed screen it connects again (home first, then away).
        self.assertIn("if (browser == null || loadingFailed) {", MAIN)
        # The TV keeps its wording.
        self.assertIn('if (isTv) "TV Server Connection" else "Server connection"', MAIN)

    def test_phone_player_hides_tabs_and_grey_poster_but_tv_is_unchanged(self):
        shell = (TV / "phone/src/main/java/studio/oneeyedwillie/tv/AppShell.kt").read_text()
        tv_shell = (TV / "app/src/tvShell/java/studio/oneeyedwillie/tv/AppShell.kt").read_text()
        self.assertIn('tabBarView?.visibility = if (open) View.GONE else View.VISIBLE', shell)
        self.assertIn('bars.hide(androidx.core.view.WindowInsetsCompat.Type.systemBars())', shell)
        self.assertIn('if(window.yarrShellBack)window.yarrShellBack();else if(window.WilliePlayer)window.WilliePlayer.close()', shell)
        self.assertIn('fun onPrompt(activity: Activity, message: String): Boolean = false', tv_shell)
        self.assertIn('fun defaultVideoPoster(): android.graphics.Bitmap? = null', tv_shell)
        self.assertIn('AppShell.defaultVideoPoster() ?: super.getDefaultVideoPoster()', MAIN)

    def test_offline_downloads_are_phone_only(self):
        shell = (TV / "phone/src/main/java/studio/oneeyedwillie/tv/AppShell.kt").read_text()
        tv_shell = (TV / "app/src/tvShell/java/studio/oneeyedwillie/tv/AppShell.kt").read_text()
        phone_src = TV / "phone/src/main/java/studio/oneeyedwillie/tv"
        for name in ("DownloadService.kt", "DownloadsActivity.kt", "OfflinePlayerActivity.kt", "OfflineStore.kt", "OfflineNet.kt", "OfflineSync.kt"):
            self.assertTrue((phone_src / name).is_file(), name)
            self.assertFalse((TV / "app/src/main/java/studio/oneeyedwillie/tv" / name).exists(), "not in the TV app: " + name)
        self.assertIn('message.startsWith("oewtv:shell:download:")', shell)
        self.assertIn('row("Downloads") { openDownloads(activity) }', shell)
        self.assertIn("fun openDownloads(activity: Activity) = Unit", tv_shell)
        self.assertIn('android:foregroundServiceType="dataSync"', PHONE_MANIFEST)
        for permission in ("FOREGROUND_SERVICE_DATA_SYNC", "POST_NOTIFICATIONS", "ACCESS_NETWORK_STATE"):
            self.assertIn(permission, PHONE_MANIFEST)
            self.assertNotIn(permission, TV_MANIFEST)
        self.assertIn("if (!isTv) addView(Button(this@MainActivity).apply {", MAIN)
        self.assertIn("AppShell.openDownloads(this@MainActivity)", MAIN)
        # Part 3: offline progress is sent back with when it was watched; the next episode is offered.
        sync = (phone_src / "OfflineSync.kt").read_text()
        self.assertIn('"/api/playback/progress", "PUT"', sync)
        self.assertIn('.put("played_at"', sync)
        self.assertIn("OfflineSync.later(activity)", shell)
        self.assertIn("Also download the next episode", shell)
        self.assertIn("Download the next episode?", (phone_src / "OfflinePlayerActivity.kt").read_text())

    def test_phone_menus_use_the_app_style_and_tv_dialogs_are_unchanged(self):
        phone_src = TV / "phone/src/main/java/studio/oneeyedwillie/tv"
        tv_shell = (TV / "app/src/tvShell/java/studio/oneeyedwillie/tv/AppShell.kt").read_text()
        for name in ("AppShell.kt", "DownloadsActivity.kt", "OfflinePlayerActivity.kt"):
            self.assertNotIn("AlertDialog", (phone_src / name).read_text(), name + " uses the app's sheet")
        self.assertIn("fun dialogTheme(): Int = 0", tv_shell)
        self.assertIn("fun styleDialog(dialog: android.app.Dialog) = Unit", tv_shell)
        self.assertEqual(MAIN.count("AlertDialog.Builder(this, AppShell.dialogTheme())"), 3)
        self.assertIn('<style name="YarrSheet"', (TV / "phone/src/main/res/values/yarr_sheet.xml").read_text())
        # A dropped connection mid-session shows the app's offline screen (phone only).
        self.assertIn("!isTv && (initialPageLoaded || failedAfterLoad)) connectionLost()", MAIN)

    def test_ci_and_release_build_the_phone_app(self):
        ci = (ROOT / ".github/workflows/google-tv.yml").read_text()
        self.assertIn(":phone:assembleDebug :phone:assembleLean", ci)
        self.assertIn("yarr-media-android-lean-apk", ci)
        release = (ROOT / ".github/workflows/release.yml").read_text()
        self.assertIn(":phone:assembleLean", release)
        self.assertEqual(release.count("dist/yarr-media-android.apk"), 3)


if __name__ == "__main__":
    unittest.main()


class AppShellTests(unittest.TestCase):
    """The phone app's native shell; the TV app gets a no-op with the same functions."""
    PHONE_SHELL = (TV / "phone/src/main/java/studio/oneeyedwillie/tv/AppShell.kt").read_text()
    TV_SHELL = (TV / "app/src/tvShell/java/studio/oneeyedwillie/tv/AppShell.kt").read_text()

    def test_tv_shell_does_nothing(self):
        self.assertIn('java.srcDirs("src/tvShell/java")', TV_GRADLE)
        self.assertIn("): View = screen", self.TV_SHELL)
        self.assertIn("Boolean = false", self.TV_SHELL)
        for fn in ("fun prepareWebView", "fun wrap", "fun onPageStarted", "fun onPageFinished", "fun onBack"):
            self.assertIn(fn, self.TV_SHELL)
            self.assertIn(fn, self.PHONE_SHELL)

    def test_phone_only_libraries_stay_out_of_the_tv_app(self):
        for lib in ("androidx.webkit:webkit", "androidx.swiperefreshlayout:swiperefreshlayout"):
            self.assertIn(lib, PHONE_GRADLE)
            self.assertNotIn(lib, TV_GRADLE)
        self.assertNotIn("androidx.webkit", MAIN)
        self.assertNotIn("swiperefreshlayout", MAIN)

    def test_phone_tab_bar(self):
        for label in ('"Home"', '"Movies"', '"TV Shows"', '"Music"', '"More"'):
            self.assertIn(label, self.PHONE_SHELL)
        for icon in ("home", "movies", "tv", "music", "more"):
            self.assertTrue((TV / f"phone/src/main/res/drawable/ic_tab_{icon}.xml").exists(), icon)
        self.assertIn('row("Server connection")', self.PHONE_SHELL)
        self.assertIn('row("Yarr account")', self.PHONE_SHELL)
