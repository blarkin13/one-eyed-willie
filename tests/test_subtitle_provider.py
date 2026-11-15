import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from server import subtitle_provider as provider, subtitles


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.video = self.root / "Sample.Movie.2024.mkv"
        self.video.write_bytes(b"test")
        for target, attr, value in (
            (provider, "CACHE", self.root / "cache"),
            (subtitles, "CACHE", self.root / "cache"),
            (provider, "_item", ({"id": 2, "title": "Sample Movie"}, self.video)),
            (subtitles, "_item", ({"id": 2}, self.video)),
        ):
            stub = patch.object(target, attr, return_value=value) if attr == "_item" else patch.object(target, attr, value)
            stub.start()
            self.addCleanup(stub.stop)

    def test_save_key_verifies_and_keeps_secrets_private(self):
        config = self.root / "opensubtitles-settings.json"
        with patch.object(provider, "SETTINGS_PATH", config), \
             patch.object(provider, "_json", return_value={"data": []}) as verify:
            result = provider.save_settings(provider.SettingsRequest(api_key="demo-key-123", token="demo-token"))
            self.assertTrue(result["configured"])
            self.assertTrue(result["token_configured"])
            self.assertEqual(result["source"], "settings")
            self.assertNotIn("demo-key-123", str(result))
            self.assertNotIn("demo-token", str(result))
            self.assertEqual(config.stat().st_mode & 0o777, 0o600)
            self.assertEqual(provider._headers()["Api-Key"], "demo-key-123")
            self.assertEqual(verify.call_count, 1)
            cleared = provider.remove_settings()
            self.assertFalse(config.exists())
            self.assertEqual(cleared["source"], "none")

    def test_invalid_provider_key_does_not_replace_existing_key(self):
        config = self.root / "opensubtitles-settings.json"
        config.write_text(json.dumps({"api_key": "previous-working-key", "token": ""}))
        with patch.object(provider, "SETTINGS_PATH", config), \
             patch.object(provider, "_json", side_effect=HTTPException(502, "Provider rejected key")):
            with self.assertRaises(HTTPException):
                provider.save_settings(provider.SettingsRequest(api_key="new-bad-key"))
        self.assertEqual(json.loads(config.read_text())["api_key"], "previous-working-key")

    def test_key_required_and_no_leak(self):
        with patch.dict("os.environ", {"OPENSUBTITLES_API_KEY": ""}):
            with self.assertRaises(HTTPException) as error:
                provider.search_subtitles(2, "en")
        self.assertEqual(error.exception.status_code, 503)

    def test_search_sanitizes_provider_data(self):
        response = {"data": [{"attributes": {
            "files": [{"file_id": 1234}], "release": "Sample Movie",
            "language": "en", "hearing_impaired": True}}]}
        with patch.dict("os.environ", {"OPENSUBTITLES_API_KEY": "test-key"}), \
             patch.object(provider, "_json", return_value=response) as mock:
            result = provider.search_subtitles(2, "en")
        self.assertEqual(result["results"][0]["file_id"], 1234)
        self.assertTrue(result["results"][0]["hearing_impaired"])
        self.assertIn("Sample+Movie", mock.call_args.args[0])
        self.assertNotIn("test-key", str(result))

    def test_download_is_cached_and_appears_in_player_tracks(self):
        with patch.dict("os.environ", {"OPENSUBTITLES_API_KEY": "test-key"}), \
             patch.object(provider, "_json", return_value={"link": "https://dl.opensubtitles.com/file.srt"}), \
             patch.object(provider, "_read", return_value=b"1\n00:00:01,000 --> 00:00:02,000\nHello\n") as download:
            first = provider.download_subtitle(2, provider.DownloadRequest(file_id=1234), "en")
            second = provider.download_subtitle(2, provider.DownloadRequest(file_id=1234), "en")
        self.assertEqual(download.call_count, 1)
        self.assertEqual(first, second)
        with patch.object(subtitles, "_embedded", return_value=[]):
            tracks = subtitles.subtitle_list(2)["tracks"]
        self.assertIn(first["track_id"], [item["id"] for item in tracks])

    def test_rejects_untrusted_host_and_invalid_language(self):
        with self.assertRaises(HTTPException):
            provider._read("http://localhost/internal", {})
        with self.assertRaises(HTTPException):
            provider._read("https://opensubtitles.com.evil.net/file", {})
        with self.assertRaises(HTTPException):
            provider.search_subtitles(2, "en/../x")
        with self.assertRaises(HTTPException):
            provider.download_subtitle(2, provider.DownloadRequest(file_id=1), "../")


if __name__ == "__main__":
    unittest.main()
