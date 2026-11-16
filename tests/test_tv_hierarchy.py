import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from server import library, metadata, tv


class TVHierarchyTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db = patch.object(library, "DB_PATH", Path(temp.name) / "media.sqlite3")
        self.db.start()
        self.addCleanup(self.db.stop)
        with library.db() as conn:
            conn.execute(
                "INSERT INTO libraries (id,name,kind,path) VALUES "
                "(1,'TV Shows','tv','/media/TV')"
            )
            conn.executemany(
                "INSERT INTO media (id,library_id,path,title,size,mtime_ns,added_at) "
                "VALUES (?,?,?,?,?,?,CURRENT_TIMESTAMP)",
                [
                    (101, 1, "/media/TV/Severance/Season 01/Severance.S01E01.mkv", "S01E01", 10, 0),
                    (102, 1, "/media/TV/Severance/Season 01/Severance.S01E02.mkv", "S01E02", 10, 0),
                    (103, 1, "/media/TV/Severance/Season 02/Severance.S02E01.mkv", "S02E01", 10, 0),
                ],
            )

    def test_show_without_tmdb_is_still_browsable(self):
        with patch.object(tv, "show_metadata", return_value={}):
            result = tv.show_details(library_id=1, key="severance:")
        self.assertEqual(result["title"], "Severance")
        self.assertEqual([season["number"] for season in result["seasons"]], [1, 2])
        self.assertEqual([season["episode_count"] for season in result["seasons"]], [2, 1])
        self.assertEqual(result["episode_count"], 3)

    def test_season_episodes_join_real_metadata(self):
        fake_show = {
            "tmdb_id": 999, "overview": "Show synopsis",
            "poster_url": "https://image.tmdb.org/t/p/w342/mock.jpg",
            "backdrop_url": "https://image.tmdb.org/t/p/w780/stage.jpg",
            "seasons": [{"number": 1, "name": "Season One", "overview": "Season synopsis",
                         "poster_url": "https://image.tmdb.org/t/p/w342/season.jpg"}],
        }
        fake_season = {"overview": "Season synopsis", "poster_url": None,
                       "episodes": {"2": {"title": "The Test", "overview": "Episode synopsis",
                                          "still_url": "https://image.tmdb.org/t/p/w300/still.jpg"}}}
        with patch.object(tv, "show_metadata", return_value=fake_show), patch.object(
            tv, "season_metadata", return_value=fake_season
        ):
            result = tv.season_details(library_id=1, key="severance:", season_number=1)
        self.assertEqual(result["season"]["name"], "Season One")
        self.assertEqual(len(result["episodes"]), 2)
        self.assertEqual(result["episodes"][1]["title"], "The Test")
        self.assertEqual(result["episodes"][1]["overview"], "Episode synopsis")
        self.assertEqual(result["episodes"][1]["id"], 102)
        self.assertEqual([entry["number"] for entry in result["seasons"]], [1, 2])
        self.assertEqual(result["show"]["year"], 0)
        self.assertTrue(result["show"]["backdrop_url"].startswith("/api/artwork/"))

    def test_episode_details_preserve_media_identity(self):
        with patch.object(tv, "show_metadata", return_value={}), patch.object(
            tv, "season_metadata", return_value={}
        ):
            result = tv.episode_details(media_id=103)
        self.assertEqual(result["season_number"], 2)
        self.assertEqual(result["episode_number"], 1)
        self.assertEqual(result["title"], "Episode 1")
        self.assertTrue(result["playback_available"])

    def test_bad_show_and_missing_season_are_404(self):
        with self.assertRaises(HTTPException):
            tv.local_show(1, "not-a-real-show:")
        with patch.object(tv, "show_metadata", return_value={}):
            with self.assertRaises(HTTPException):
                tv.season_details(library_id=1, key="severance:", season_number=99)

    def test_media_paths_are_not_in_detail_response(self):
        with patch.object(tv, "show_metadata", return_value={}):
            response = tv.show_details(library_id=1, key="severance:")
        self.assertNotIn("/media/TV", str(response))


class TMDBSafetyTests(unittest.TestCase):
    def test_image_urls_are_sanitized(self):
        self.assertEqual(
            metadata.image_url("/poster123.jpg"),
            "https://image.tmdb.org/t/p/w342/poster123.jpg",
        )
        self.assertIsNone(metadata.image_url("https://evil.example/anything"))
        self.assertIsNone(metadata.image_url("/../../bad.jpg"))
        self.assertIsNone(metadata.image_url(None))

    def test_token_never_exposed_in_settings(self):
        with patch.object(metadata, "_token", return_value="supersecret"):
            response = metadata.metadata_settings()
        self.assertTrue(response["tmdb_configured"])
        self.assertNotIn("supersecret", str(response))

    def test_show_match_does_not_accept_unrelated_title(self):
        fake_results = {"results": [{"id": 111, "name": "Severance: Behind the Scenes",
                                     "original_name": "Unrelated Show"}]}
        with patch.object(metadata, "_token", return_value="valid"), patch.object(
            metadata, "_call", return_value=fake_results
        ), patch.object(metadata, "_cache_get", return_value=None), patch.object(
            metadata, "_cache_put"
        ):
            self.assertEqual(metadata.show_metadata("Severance"), {})


if __name__ == "__main__":
    unittest.main()
