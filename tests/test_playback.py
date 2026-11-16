import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from server import library, playback
from server.catalog import catalog
from server.home import PlaybackUpdate, home_shelves, update_playback


class PlaybackTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.media_root = root / "media"
        movie = self.media_root / "Movies" / "Example (2024)"
        episode = self.media_root / "TV" / "Example Show" / "Season 01"
        movie.mkdir(parents=True)
        episode.mkdir(parents=True)
        self.movie = movie / "Example (2024).mp4"
        self.mkv = episode / "Example.Show.S01E01.mkv"
        self.movie.write_bytes(b"test mp4")
        self.mkv.write_bytes(b"test mkv")
        for p in (
            patch.object(library, "DB_PATH", root / "library.sqlite"),
            patch.object(playback, "MEDIA_ROOT", self.media_root),
        ):
            p.start()
            self.addCleanup(p.stop)
        with library.db() as conn:
            conn.execute(
                "INSERT INTO libraries(id,name,kind,path) VALUES(1,'Movies','movies',?)",
                (str(movie.parent),),
            )
            conn.execute(
                "INSERT INTO libraries(id,name,kind,path) VALUES(2,'TV','tv',?)",
                (str(self.media_root / "TV"),),
            )
            conn.execute(
                "INSERT INTO media(id,library_id,path,title,size,mtime_ns,added_at) "
                "VALUES(1,1,?,'Example',8,1,CURRENT_TIMESTAMP)",
                (str(self.movie),),
            )
            conn.execute(
                "INSERT INTO media(id,library_id,path,title,size,mtime_ns,added_at) "
                "VALUES(2,2,?,'Episode',8,1,CURRENT_TIMESTAMP)",
                (str(self.mkv),),
            )

    def test_direct_playback_returns_local_file_and_byte_range_type(self):
        result = playback.stream_media(1)
        self.assertEqual(Path(result.path), self.movie.resolve())
        self.assertEqual(result.media_type, "video/mp4")
        self.assertEqual(result.headers["accept-ranges"], "bytes")
        # Native Android players can direct-stream MKV; browser negotiation
        # still chooses HLS if its decoders/container cannot play it.
        mkv_result = playback.stream_media(2)
        self.assertEqual(mkv_result.media_type, "video/x-matroska")

    def test_status_exposes_actual_probed_media_not_extension_guesses(self):
        with patch.object(playback, "inspect_media", return_value={
            "container": "mkv", "video_codec": "hevc",
            "audio_codec": "eac3", "width": 3840, "height": 2160
        }):
            status = playback.watch_status(2)
        self.assertEqual(status["mode"], "compatible")  # legacy client hint
        self.assertEqual(status["media"]["video_codec"], "hevc")
        self.assertEqual(status["media"]["audio_codec"], "eac3")

    def test_watched_unwatched_and_continue_watching(self):
        update_playback(PlaybackUpdate(
            media_id=1, position_seconds=120, duration_seconds=3600
        ))
        self.assertFalse(playback.watch_status(1)["watched"])
        self.assertEqual(playback.watch_status(1)["position_seconds"], 120)
        self.assertEqual(len(home_shelves()["continue_watching"]), 1)
        result = playback.mark_watched(1, playback.WatchedRequest(watched=True))
        self.assertTrue(result["watched"])
        self.assertEqual(home_shelves()["continue_watching"], [])
        self.assertTrue(catalog(kind="movies")["items"][0]["watched"])
        playback.mark_watched(1, playback.WatchedRequest(watched=False))
        self.assertFalse(playback.watch_status(1)["watched"])
        self.assertEqual(playback.watch_status(1)["position_seconds"], 0)
        self.assertFalse(catalog(kind="movies")["items"][0]["watched"])

    def test_watched_before_first_play_has_no_fake_duration(self):
        playback.mark_watched(2, playback.WatchedRequest(watched=True))
        with patch.object(playback, "probe_duration", return_value=2500):
            status = playback.watch_status(2)
        self.assertTrue(status["watched"])
        self.assertEqual(status["position_seconds"], 0)
        self.assertEqual(status["duration_seconds"], 2500)

    def test_unknown_duration_resume_appears_in_continue_watching(self):
        # Android TV/HLS can know the played position before the duration.
        # Its progress must not be discarded merely because duration is zero.
        result = update_playback(PlaybackUpdate(
            media_id=2, position_seconds=900, duration_seconds=0
        ))
        self.assertTrue(result["saved"])
        self.assertFalse(result["completed"])
        shelf = home_shelves()["continue_watching"]
        self.assertEqual(len(shelf), 1)
        self.assertEqual(shelf[0]["media_id"], 2)
        self.assertEqual(shelf[0]["position_seconds"], 900)
        self.assertEqual(shelf[0]["play_state"], "resume")
        self.assertEqual(playback.watch_status(2)["position_seconds"], 900)

    def test_near_end_progress_sets_watched(self):
        result = update_playback(PlaybackUpdate(
            media_id=2, position_seconds=195, duration_seconds=200
        ))
        self.assertTrue(result["completed"])
        self.assertTrue(playback.watch_status(2)["watched"])

    def test_rejects_nonindexed_and_missing_files(self):
        with self.assertRaises(HTTPException) as error:
            playback.stream_media(999)
        self.assertEqual(error.exception.status_code, 404)
        self.movie.unlink()
        with self.assertRaises(HTTPException) as error:
            playback.stream_media(1)
        self.assertEqual(error.exception.status_code, 404)

    def test_rejects_media_symlink_escape(self):
        outside = Path(self.media_root.parent / "outside.mp4")
        outside.write_bytes(b"private")
        self.movie.unlink()
        self.movie.symlink_to(outside)
        with self.assertRaises(HTTPException) as error:
            playback.stream_media(1)
        self.assertEqual(error.exception.status_code, 404)

    def test_episode_status_in_catalog(self):
        playback.mark_watched(2, playback.WatchedRequest(watched=True))
        row = catalog(kind="tv")["items"][0]
        self.assertTrue(row["watched"])
        self.assertTrue(row["episodes"][0]["watched"])

    def test_progress_deleted_on_library_deletion(self):
        playback.mark_watched(2, playback.WatchedRequest(watched=True))
        library.delete_library(2)
        with library.db() as conn:
            self.assertEqual(conn.execute(
                "SELECT count(*) FROM playback_progress WHERE media_id=2"
            ).fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
