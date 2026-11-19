"""Yarr Media display branding must not break installed One-Eyed Willie clients.

Historical identifiers are deliberately preserved as protocol/installation keys.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "server"
ANDROID = ROOT / "google-tv" / "app" / "src" / "main"


class YarrMediaBrandingTests(unittest.TestCase):
    def test_every_server_html_page_uses_new_display_brand(self):
        for path in sorted(SERVER.glob("*.html")):
            with self.subTest(page=path.name):
                self.assertNotRegex(path.read_text(), r"(?i)one-eyed willie")

    def test_sidebar_and_server_return_new_display_name(self):
        shell = (SERVER / "shell.js").read_text()
        main = (SERVER / "main.py").read_text()
        info = (SERVER / "connections.py").read_text()
        settings = (SERVER / "general_settings.html").read_text()
        self.assertIn("words.textContent='Yarr Media'", shell)
        self.assertIn("brand.title='Yarr Media'", shell)
        self.assertIn('FastAPI(title="Yarr Media"', main)
        self.assertIn('"name": "Yarr Media"', main)
        self.assertIn('"name": "Yarr Media"', info)
        self.assertIn("(data.name||'Yarr Media')", settings)

    def test_android_app_displays_yarr_media_without_changing_app_identity(self):
        manifest = (ANDROID / "AndroidManifest.xml").read_text()
        activity = (ANDROID / "java/studio/oneeyedwillie/tv/MainActivity.kt").read_text()
        gradle = (ROOT / "google-tv/app/build.gradle.kts").read_text()
        self.assertIn('android:label="Yarr Media"', manifest)
        self.assertIn("Yarr Media loading artwork", activity)
        self.assertIn("Could not find Yarr Media", activity)
        self.assertIn('applicationId = "studio.oneeyedwillie.tv"', gradle)

    def test_legacy_discovery_and_remote_routing_are_preserved(self):
        main = (SERVER / "main.py").read_text()
        activity = (ANDROID / "java/studio/oneeyedwillie/tv/MainActivity.kt").read_text()
        cloudflare = (ROOT / "cloudflare/yarr/worker.js").read_text()
        self.assertIn('"application": "one-eyed-willie"', main)
        self.assertIn('OneEyedWillieTV/1', activity)
        self.assertIn("result.application!=='one-eyed-willie'", cloudflare)
        self.assertIn("http://one-eyed-willie:8787", cloudflare)


if __name__ == "__main__":
    unittest.main()
