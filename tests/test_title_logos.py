"""TMDB movie and series title logos must remain optional and safe."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from server import artwork, library, metadata


class MediaTitleLogoTests(unittest.TestCase):
    def test_prefers_english_logo_over_foreign_or_language_neutral(self):
        url = metadata.logo_image_url({"logos": [
            {"iso_639_1": "fr", "file_path": "/french.png", "vote_count": 100},
            {"iso_639_1": None, "file_path": "/neutral.png", "vote_count": 50},
            {"iso_639_1": "en", "file_path": "/english.png", "vote_count": 2},
        ]})
        self.assertEqual(url, "https://image.tmdb.org/t/p/w500/english.png")

    def test_falls_back_to_neutral_then_plain_text(self):
        self.assertEqual(metadata.logo_image_url({"logos": [
            {"iso_639_1": None, "file_path": "/neutral.png"},
            {"iso_639_1": "de", "file_path": "/german.png"},
        ]}), "https://image.tmdb.org/t/p/w500/neutral.png")
        self.assertIsNone(metadata.logo_image_url({"logos": [
            {"iso_639_1": "de", "file_path": "/german.png"}
        ]}))
        self.assertIsNone(metadata.logo_image_url(None))
        self.assertIsNone(metadata.logo_image_url({"logos": [
            {"iso_639_1": "en", "file_path": "https://unknown.example/evil.svg"}
        ]}))

    def test_title_logos_use_same_origin_artwork_cache(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(
            library, "DB_PATH", Path(folder) / "test.sqlite"
        ):
            result = artwork.localize({
                "title": "Sample Show",
                "logo_url": "https://image.tmdb.org/t/p/w500/show.png",
            })
            self.assertRegex(result["logo_url"], r"^/api/artwork/[0-9a-f]{64}$")
            self.assertEqual(result["title"], "Sample Show")


if __name__ == "__main__":
    unittest.main()
