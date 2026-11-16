"""Continue Watching state: persistent resume positions and next available TV episodes."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from server import library
from server.home import PlaybackUpdate, home_shelves, update_playback


class ContinueWatchingTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        patcher = patch.object(library, "DB_PATH", Path(temp.name) / "progress.sqlite3")
        patcher.start()
        self.addCleanup(patcher.stop)
        with library.db() as conn:
            conn.execute("INSERT INTO libraries(id,name,kind,path) "
                         "VALUES(1,'Movies','movies','/media/movies')")
            conn.execute("INSERT INTO libraries(id,name,kind,path) "
                         "VALUES(2,'TV','tv','/media/tv')")
            for media_id, kind, path in [
                (1, 1, "/media/movies/Arrival (2016)/Arrival.mkv"),
                (2, 2, "/media/tv/Example/Season 01/Example.S01E01.mkv"),
                (3, 2, "/media/tv/Example/Season 01/Example.S01E02.mkv"),
                (4, 2, "/media/tv/Example/Season 02/Example.S02E01.mkv"),
                (5, 2, "/media/tv/Another/Season 01/Another.S01E01.mkv"),
                (6, 2, "/media/tv/Another/Season 01/Another.S01E02.mkv"),
            ]:
                conn.execute(
                    "INSERT INTO media(id,library_id,path,title,size,mtime_ns,added_at) "
                    "VALUES(?,?,?,?,?,?,'2026-11-15 10:00:00')",
                    (media_id, kind, path, Path(path).stem, 100, 100),
                )

    def cards(self):
        return home_shelves()["continue_watching"]

    def test_movie_and_series_resume_survive_new_connections(self):
        update_playback(PlaybackUpdate(media_id=1,position_seconds=180,duration_seconds=7200))
        update_playback(PlaybackUpdate(media_id=2,position_seconds=300,duration_seconds=0))
        expected = {item["media_id"]: item for item in self.cards()}
        self.assertEqual(set(expected), {1,2})
        self.assertEqual(expected[1]["play_state"], "resume")
        self.assertEqual(expected[1]["position_seconds"], 180)
        self.assertEqual(expected[2]["position_seconds"], 300)
        self.assertEqual(expected[2]["subtitle"], "S01 · E01")
        # New database connection and Home fetch still have the same resume points.
        with library.db() as conn:
            values = conn.execute("SELECT media_id,position_seconds FROM playback_progress "
                                  "ORDER BY media_id").fetchall()
        self.assertEqual([(row["media_id"],row["position_seconds"]) for row in values],
                         [(1,180),(2,300)])
        self.assertEqual({x["media_id"] for x in self.cards()}, {1,2})

    def test_completed_episode_advances_to_next_downloaded_episode(self):
        update_playback(PlaybackUpdate(media_id=2,position_seconds=1800,
                                       duration_seconds=1800,completed=True))
        entries = self.cards()
        self.assertEqual(len(entries),1)
        self.assertEqual(entries[0]["media_id"],3)
        self.assertEqual(entries[0]["subtitle"],"S01 · E02")
        self.assertEqual(entries[0]["play_state"],"next")
        self.assertEqual(entries[0]["position_seconds"],0)
        self.assertIsNone(entries[0]["progress_percent"])
        # Once the next episode starts, Resume replaces the Next episode card.
        update_playback(PlaybackUpdate(media_id=3,position_seconds=300,duration_seconds=1800))
        entries = self.cards()
        self.assertEqual(len(entries),1)
        self.assertEqual(entries[0]["media_id"],3)
        self.assertEqual(entries[0]["play_state"],"resume")
        self.assertEqual(entries[0]["position_seconds"],300)

    def test_next_episode_advances_to_next_season_then_stops(self):
        for media_id in (2,3):
            update_playback(PlaybackUpdate(media_id=media_id,position_seconds=1800,
                                           duration_seconds=1800,completed=True))
        upcoming=self.cards()
        self.assertEqual(len(upcoming),1)
        self.assertEqual(upcoming[0]["media_id"],4)
        self.assertEqual(upcoming[0]["subtitle"],"S02 · E01")
        update_playback(PlaybackUpdate(media_id=4,position_seconds=1800,
                                       duration_seconds=1800,completed=True))
        self.assertEqual(self.cards(),[])

    def test_do_not_suggest_unstarted_shows_or_finished_movies(self):
        self.assertEqual(self.cards(),[])
        update_playback(PlaybackUpdate(media_id=1,position_seconds=7200,
                                       duration_seconds=7200,completed=True))
        self.assertEqual(self.cards(),[])

    def test_completed_episodes_stay_completed_after_delayed_progress_write(self):
        update_playback(PlaybackUpdate(media_id=2,position_seconds=200,duration_seconds=1800))
        update_playback(PlaybackUpdate(media_id=2,position_seconds=1800,
                                       duration_seconds=1800,completed=True))
        # A network-late heartbeat still cannot unmark the episode.
        delayed = update_playback(PlaybackUpdate(media_id=2,position_seconds=190,
                                                 duration_seconds=1800,completed=False))
        self.assertTrue(delayed["completed"])
        self.assertEqual(self.cards()[0]["media_id"],3)
        with library.db() as conn:
            saved=conn.execute("SELECT completed FROM playback_progress WHERE media_id=2").fetchone()
        self.assertEqual(saved["completed"],1)

    def test_preserve_known_duration_when_a_later_hls_update_is_unknown(self):
        update_playback(PlaybackUpdate(media_id=1,position_seconds=180,duration_seconds=7200))
        result=update_playback(PlaybackUpdate(media_id=1,position_seconds=205,duration_seconds=0))
        self.assertEqual(result["duration_seconds"],7200)
        movie=self.cards()[0]
        self.assertEqual(movie["position_seconds"],205)
        self.assertEqual(movie["duration_seconds"],7200)

    def test_completed_older_series_and_active_movie_both_appear(self):
        update_playback(PlaybackUpdate(media_id=2,position_seconds=1800,
                                       duration_seconds=1800,completed=True))
        update_playback(PlaybackUpdate(media_id=1,position_seconds=180,duration_seconds=7200))
        self.assertEqual({x["media_id"] for x in self.cards()}, {1,3})

    def test_no_duplicate_next_card_for_a_series_with_multiple_watched_episodes(self):
        for media_id in (2,3):
            update_playback(PlaybackUpdate(media_id=media_id,position_seconds=1800,
                                           duration_seconds=1800,completed=True))
        next_cards=[x for x in self.cards() if x["kind"]=="tv"]
        self.assertEqual(len(next_cards),1)
        self.assertEqual(next_cards[0]["media_id"],4)

    def test_post_endpoint_supports_unload_beacon(self):
        from server.main import app
        methods=[route.methods for route in app.routes
                 if getattr(route,"path","")=="/api/playback/progress"]
        self.assertTrue(any("POST" in x for x in methods),
                        [(getattr(route,"path",None),getattr(route,"methods",None))
                         for route in app.routes])
        self.assertTrue(any("PUT" in x for x in methods))


if __name__=="__main__":
    unittest.main()
