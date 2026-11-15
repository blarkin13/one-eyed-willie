import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from server import library, plex_import


class PlexImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.db_patch = patch.object(library, "DB_PATH", root / "library.sqlite")
        self.db_patch.start()
        self.addCleanup(self.db_patch.stop)
        movies = root / "Movies"
        tv = root / "TV"
        movie = movies / "Arrival (2016)" / "Arrival (2016).mkv"
        episode = tv / "The Expanse" / "Season 01" / "The.Expanse.S01E02.mkv"
        movie.parent.mkdir(parents=True)
        episode.parent.mkdir(parents=True)
        movie.touch()
        episode.touch()
        with library.db() as conn:
            conn.execute("INSERT INTO libraries(id,name,kind,path) VALUES(1,'Movies','movies',?)", (str(movies),))
            conn.execute("INSERT INTO libraries(id,name,kind,path) VALUES(2,'TV','tv',?)", (str(tv),))
            conn.execute("INSERT INTO media(id,library_id,path,title,size,mtime_ns) VALUES(1,1,?,'Arrival',0,1)", (str(movie),))
            conn.execute("INSERT INTO media(id,library_id,path,title,size,mtime_ns) VALUES(2,2,?,'Expanse',0,1)", (str(episode),))
        self.config = patch.object(plex_import, "_require_config", return_value={
            "url": "http://host.docker.internal:32400", "token": "secret"})
        self.config.start()
        self.addCleanup(self.config.stop)

    def test_preview_is_read_only_and_import_marks_only_matched_items(self):
        plex = [
            ("movie", {"title": "Arrival", "year": 2016, "viewCount": 1}),
            ("show", {"grandparentTitle": "The Expanse", "parentIndex": 1, "index": 2, "viewCount": 1}),
            ("movie", {"title": "Missing Film", "year": 2023, "viewCount": 1}),
        ]
        with patch.object(plex_import, "_plex_items", return_value=plex):
            preview = plex_import.preview_import()
            self.assertEqual(preview["new_matches"], 2)
            self.assertEqual(preview["unmatched"], 1)
            with library.db() as conn:
                self.assertEqual(conn.execute("SELECT count(*) FROM playback_progress").fetchone()[0], 0)
            result = plex_import.import_watched(plex_import.ImportRequest(confirm=True))
            self.assertEqual(result["imported"], 2)
            again = plex_import.import_watched(plex_import.ImportRequest(confirm=True))
            self.assertEqual(again["imported"], 0)
            with library.db() as conn:
                self.assertEqual(conn.execute("SELECT count(*) FROM playback_progress WHERE completed=1").fetchone()[0], 2)

    def test_unwatched_plex_items_do_not_clear_local_watched(self):
        with library.db() as conn:
            conn.execute("INSERT INTO playback_progress(media_id,position_seconds,duration_seconds,completed) VALUES(1,0,0,1)")
        with patch.object(plex_import, "_plex_items", return_value=[]):
            self.assertEqual(plex_import.import_watched(plex_import.ImportRequest(confirm=True))["imported"], 0)
            with library.db() as conn:
                self.assertEqual(conn.execute("SELECT completed FROM playback_progress WHERE media_id=1").fetchone()[0], 1)

    def test_local_only_url_validation(self):
        self.assertEqual(plex_import._base_url("http://host.docker.internal:32400/"), "http://host.docker.internal:32400")
        for url in ("https://example.com:32400", "http://8.8.8.8:32400", "http://127.0.0.1:9999",
                    "http://localhost:32400/evil", "http://localhost:32400/?token=abc"):
            with self.assertRaises(Exception):
                plex_import._base_url(url)


if __name__ == "__main__":
    unittest.main()
