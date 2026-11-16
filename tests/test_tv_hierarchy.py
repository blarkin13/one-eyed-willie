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
        self.assertIn("year", result["show"])
        self.assertTrue(result["show"]["backdrop_url"].startswith("/api/artwork/"))

    def test_long_season_and_multiple_seasons_are_not_truncated(self):
        with library.db() as conn:
            conn.executemany(
                "INSERT INTO media (id,library_id,path,title,size,mtime_ns,added_at) "
                "VALUES (?,?,?,?,?,?,CURRENT_TIMESTAMP)",
                [
                    (200 + episode, 1,
                     f"/media/TV/Severance/Season 01/Severance.S01E{episode:02d}.mkv",
                     f"S01E{episode:02d}", 10, 0)
                    for episode in range(3, 31)
                ] + [
                    (300 + season, 1,
                     f"/media/TV/Severance/Season {season:02d}/Severance.S{season:02d}E01.mkv",
                     f"S{season:02d}E01", 10, 0)
                    for season in range(3, 13)
                ],
            )
        with patch.object(tv, "show_metadata", return_value={}), patch.object(
            tv, "season_metadata", return_value={}
        ):
            result = tv.season_details(library_id=1, key="severance:", season_number=1)
        self.assertEqual([item["episode"] for item in result["episodes"]], list(range(1, 31)))
        self.assertEqual([item["number"] for item in result["seasons"]], list(range(1, 13)))

    def test_show_next_episode_prefers_partial_then_first_unwatched(self):
        episodes = [
            {"id": 1, "season": 1, "episode": 1, "watched": True,
             "position_seconds": 0, "duration_seconds": 0},
            {"id": 2, "season": 1, "episode": 2, "watched": False,
             "position_seconds": 0, "duration_seconds": 0},
            {"id": 3, "season": 1, "episode": 3, "watched": False,
             "position_seconds": 240, "duration_seconds": 1800},
            {"id": 4, "season": 0, "episode": 1, "watched": False,
             "position_seconds": 0, "duration_seconds": 0},
        ]
        selected = tv.next_for_series(episodes)
        self.assertEqual(selected["media_id"], 3)
        self.assertTrue(selected["resume"])
        episodes[2]["watched"] = True
        self.assertEqual(tv.next_for_series(episodes)["media_id"], 2)
        episodes[1]["watched"] = True
        episodes[3]["watched"] = True
        replay = tv.next_for_series(episodes)
        self.assertEqual(replay["media_id"], 1)
        self.assertTrue(replay["replay"])

    def test_series_metadata_exposes_parental_rating_and_verified_imdb(self):
        fake = {
            "title": "Severance", "rating": 8.1, "genres": ["Drama"],
            "content_rating": "TV-MA", "imdb_id": "tt11280740", "network": "Apple TV+",
            "trailer_key": "abcdefghijk",
        }
        with patch.object(tv, "show_metadata", return_value=fake), patch.object(
            tv, "imdb_details", return_value={
                "rating": 8.7, "content_rating": "TV-MA", "rotten_tomatoes": 92
            }
        ):
            series = tv.show_details(library_id=1, key="severance:")
            season = tv.season_details(library_id=1, key="severance:", season_number=1)
        self.assertEqual(series["content_rating"], "TV-MA")
        self.assertEqual(series["imdb_rating"], 8.7)
        self.assertEqual(series["rotten_tomatoes"], 92)
        self.assertEqual(season["show"]["rotten_tomatoes"], 92)
        self.assertEqual(series["network"], "Apple TV+")
        self.assertEqual(series["next_episode"]["media_id"], 101)
        self.assertEqual(season["show"]["content_rating"], "TV-MA")
        self.assertEqual(season["show"]["trailer_key"], "abcdefghijk")

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
    def test_tmdb_tv_details_extract_us_age_rating_and_imdb_id(self):
        details = {
            "id": 901, "name": "Test Series", "seasons": [],
            "credits": {"cast": []}, "videos": {"results": []},
            "reviews": {"results": []},
            "content_ratings": {"results": [
                {"iso_3166_1": "GB", "rating": "15"},
                {"iso_3166_1": "US", "rating": "TV-14"},
            ]},
            "external_ids": {"imdb_id": "tt12345678"},
        }
        with patch.object(metadata, "token_status", return_value=True), patch.object(
            metadata, "_call", return_value=details
        ):
            result = metadata.show_metadata_by_id(901)
        self.assertEqual(result["content_rating"], "TV-14")
        self.assertEqual(result["imdb_id"], "tt12345678")

    def test_omdb_rotten_tomatoes_score_requires_explicit_source(self):
        import io
        import json
        sample = {"Response": "True", "imdbRating": "8.8", "Rated": "TV-MA",
                  "Ratings": [
                      {"Source": "Internet Movie Database", "Value": "8.8/10"},
                      {"Source": "Rotten Tomatoes", "Value": "94%"},
                  ]}
        with patch.dict("os.environ", {"OMDB_API_KEY": "example-key"}), patch.object(
            metadata, "_cache_get", return_value=None
        ), patch.object(metadata, "_cache_put"), patch.object(
            metadata.urllib.request, "urlopen",
            return_value=io.BytesIO(json.dumps(sample).encode())
        ):
            score = metadata.imdb_details("tt11280740")
        self.assertEqual(score["rotten_tomatoes"], 94)
        self.assertEqual(score["rating"], 8.8)
        sample["Ratings"][1]["Value"] = "110%"
        with patch.dict("os.environ", {"OMDB_API_KEY": "example-key"}), patch.object(
            metadata, "_cache_get", return_value=None
        ), patch.object(metadata, "_cache_put"), patch.object(
            metadata.urllib.request, "urlopen",
            return_value=io.BytesIO(json.dumps(sample).encode())
        ):
            invalid = metadata.imdb_details("tt11280740")
        self.assertIsNone(invalid["rotten_tomatoes"])

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
