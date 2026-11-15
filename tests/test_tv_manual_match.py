import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from server import library, tv


class ManualMatchTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        db_patch = patch.object(library, "DB_PATH", Path(temp.name) / "matches.sqlite")
        db_patch.start()
        self.addCleanup(db_patch.stop)
        show_patch = patch.object(tv, "local_show", return_value={
            "library_id": 3, "key": "alternate title:", "title": "Alternate Title",
            "year": None, "episodes": [{"id": 5, "season": 1, "episode": 1, "watched": False}]
        })
        show_patch.start()
        self.addCleanup(show_patch.stop)

    def test_manual_match_is_persistent_and_overrides_automatic_matching(self):
        with patch.object(tv, "tmdb_by_id", return_value={"source": "TMDB", "title": "Correct Show"}) as provider:
            saved = tv.save_match(3, "alternate title:", tv.MatchRequest(provider="TMDB", provider_id=777))
            self.assertTrue(saved["matched"])
            result = tv.show_metadata("Alternate Title", None, 3, "alternate title:")
        self.assertEqual(result["title"], "Correct Show")
        self.assertEqual(tv.manual_match(3, "alternate title:"), {"provider": "TMDB", "provider_id": 777})
        provider.assert_called_with(777)

    def test_clear_match_restores_automatic_matching(self):
        with patch.object(tv, "tvmaze_by_id", return_value={"title": "Correct"}):
            tv.save_match(3, "alternate title:", tv.MatchRequest(provider="TVmaze", provider_id=21))
        tv.clear_match(3, "alternate title:")
        self.assertIsNone(tv.manual_match(3, "alternate title:"))
        with patch.object(tv, "token_status", return_value=False), \
             patch.object(tv, "tvmaze_show_metadata", return_value={"source": "TVmaze", "title": "Automatic"}), \
             patch.object(tv, "sonarr_metadata", return_value={}):
            result = tv.show_metadata("Alternate Title", None, 3, "alternate title:")
        self.assertEqual(result["title"], "Automatic")

    def test_rejects_unavailable_or_invalid_selection_without_saving(self):
        for provider in ("UNKNOWN", "TMDB"):
            with patch.object(tv, "tmdb_by_id", return_value={}):
                with self.assertRaises(HTTPException):
                    tv.save_match(3, "alternate title:", tv.MatchRequest(provider=provider, provider_id=77))
        self.assertIsNone(tv.manual_match(3, "alternate title:"))

    def test_search_returns_selectable_provider_ids(self):
        with patch.object(tv, "token_status", return_value=True), \
             patch.object(tv, "tmdb_call", return_value={"results": [
                 {"id": 4, "name": "Correct Show", "first_air_date": "2024-01-01"}]}), \
             patch.object(tv, "tvmaze_get", return_value=[
                 {"show": {"id": 9, "name": "Correct Show", "premiered": "2024-02-01"}}]):
            response = tv.search_matches(3, "alternate title:", "Correct")
        self.assertEqual({m["provider"] for m in response["results"]}, {"TMDB", "TVmaze"})
        self.assertEqual({m["provider_id"] for m in response["results"]}, {4, 9})


if __name__ == "__main__":
    unittest.main()
