"""Regression tests for series/season bulk tracking and richer movie metadata."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from server import library, tv, movies, metadata


class DetailEnhancementTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root=Path(self.temp.name)
        patcher=patch.object(library, "DB_PATH", root/"test.sqlite")
        patcher.start();self.addCleanup(patcher.stop)
        self.tvroot=root/"media"/"TV"
        self.tvroot.mkdir(parents=True)
        with library.db() as conn:
            conn.execute("INSERT INTO libraries(id,name,kind,path) VALUES(1,'TV','tv',?)",(str(self.tvroot),))
            for id,filename in [(11,"S01E01.mkv"),(12,"S01E02.mkv"),(13,"S02E01.mkv")]:
                path=self.tvroot/"Sample Show"/filename
                path.parent.mkdir(exist_ok=True)
                path.write_bytes(b"video")
                conn.execute("INSERT INTO media(id,library_id,path,title,size,mtime_ns,added_at) "
                             "VALUES(?,?,?,'Sample Show',5,1,CURRENT_TIMESTAMP)",(id,1,str(path)))

    def _show(self):
        return {"episodes":[
            {"id":11,"season":1},{"id":12,"season":1},{"id":13,"season":2}]}

    def test_series_bulk_watched_and_unwatched(self):
        with patch.object(tv, "local_show", return_value=self._show()):
            result=tv.set_show_watched(1,"sample show",tv.BulkWatched(watched=True))
            self.assertEqual(result["updated"],3)
            with library.db() as conn:
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM playback_progress WHERE completed=1").fetchone()[0],3)
            result=tv.set_show_watched(1,"sample show",tv.BulkWatched(watched=False))
            self.assertEqual(result["updated"],3)
            with library.db() as conn:
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM playback_progress").fetchone()[0],0)

    def test_season_updates_only_matching_episodes(self):
        with patch.object(tv, "local_show", return_value=self._show()):
            result=tv.set_season_watched(1,"sample show",1,tv.BulkWatched(watched=True))
            self.assertEqual(result["updated"],2)
            with library.db() as conn:
                ids=[row["media_id"] for row in conn.execute(
                    "SELECT media_id FROM playback_progress ORDER BY media_id")]
            self.assertEqual(ids,[11,12])
            result=tv.set_season_watched(1,"sample show",2,tv.BulkWatched(watched=True))
            self.assertEqual(result["updated"],1)
            with library.db() as conn:
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM playback_progress").fetchone()[0],3)

    def test_nonexistent_season_rejected(self):
        with patch.object(tv, "local_show", return_value=self._show()):
            with self.assertRaises(HTTPException) as error:
                tv.set_season_watched(1,"sample show",5,tv.BulkWatched(watched=True))
            self.assertEqual(error.exception.status_code,404)

    def test_movie_extras_provider_is_one_cached_request(self):
        data={"tagline":"A story","vote_average":8.1,"vote_count":200,
              "credits":{"cast":[{"name":"Actor","character":"Lead","profile_path":None}]},
              "reviews":{"results":[{"author":"Reviewer","content":"Worth watching."}]}}
        with patch.object(metadata,"token_status",return_value=True),\
             patch.object(metadata,"_cache_get",return_value=None),\
             patch.object(metadata,"_cache_put") as put,\
             patch.object(metadata,"_call",return_value=data) as call:
            result=movies._movie_extras({"tmdb_id":321})
        self.assertEqual(call.call_count,1)
        self.assertEqual(call.call_args.kwargs["query"]["append_to_response"],"credits,reviews,videos")
        self.assertEqual(result["cast"][0]["name"],"Actor")
        self.assertEqual(result["reviews"][0]["source"],"TMDB")
        self.assertEqual(result["tmdb_rating"],8.1)
        self.assertTrue(put.called)

    def test_movie_trailer_id_requires_valid_youtube_key(self):
        with patch.object(movies, "_movie_path", return_value=(
            {"title": "Example", "year": 2024}, Path("/media/Example.mkv"), Path("/media"))), \
             patch.object(movies, "_local_nfo", return_value={}), \
             patch.object(movies, "_local_poster", return_value=None), \
             patch.object(movies, "register_remote", return_value=None), \
             patch.object(movies, "register_radarr", return_value=None), \
             patch.object(movies, "_movie_extras", return_value={}), \
             patch.object(movies, "db") as db_mock:
            from unittest.mock import MagicMock
            manager=MagicMock()
            manager.__enter__.return_value.execute.return_value.fetchone.return_value=None
            db_mock.return_value=manager
            sample={"title":"Example","year":2024,"youtube_trailer_id":"aBcD1234_-X"}
            result=movies._details(1,"example:2024",snapshot=[sample])
            self.assertEqual(result["trailer_key"],"aBcD1234_-X")
            sample["youtube_trailer_id"]="https://evil.invalid/example"
            result=movies._details(1,"example:2024",snapshot=[sample])
            self.assertIsNone(result["trailer_key"])

    def test_no_tmdb_token_returns_no_invented_ratings_or_reviews(self):
        with patch.object(metadata,"token_status",return_value=False):
            result=movies._movie_extras({"tmdb_id":321})
        self.assertEqual(result,{})


if __name__=="__main__":
    unittest.main()
