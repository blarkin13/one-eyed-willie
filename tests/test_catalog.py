import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
from server import library
from server.catalog import catalog
from server.catalog import episode_info, movie_info, pretty

class CatalogTests(unittest.TestCase):
    def test_movies(self):
        x = movie_info("/media/Media/Movies/Alien (1979)/Alien.1979.mkv", "/media/Media/Movies")
        self.assertEqual(x["title"], "Alien")
        self.assertEqual(x["year"], 1979)

    def test_tv_episode(self):
        x = episode_info("/media/Media/TV/Severance/Season 01/Severance.S01E02.mkv", "/media/Media/TV")
        self.assertEqual(x["title"], "Severance")
        self.assertEqual((x["season"], x["episode"]), (1, 2))

    def test_title_cleanup(self):
        self.assertEqual(pretty("The.Matrix.1080p.BluRay"), "The Matrix")

class AutoScanRevisionTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.movies = root / "Movies"
        self.movies.mkdir()
        for name, value in (("DB_PATH", root / "library.sqlite3"), ("MEDIA_ROOT", root)):
            patcher = patch.object(library, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        with library.db() as conn:
            conn.execute(
                "INSERT INTO libraries(id,name,kind,path) VALUES(1,'Movies','movies',?)",
                (str(self.movies),)
            )

    def revision(self):
        with library.db() as conn:
            return conn.execute("SELECT revision FROM catalog_state WHERE id=1").fetchone()[0]

    def test_new_media_and_unchanged_scans(self):
        self.assertEqual(self.revision(), 0)
        self.assertFalse(library.scan_library(1)["changed"])
        self.assertEqual(self.revision(), 0)

        film = self.movies / "Arrival (2016).mkv"
        film.write_bytes(b"test media")
        self.assertTrue(library.scan_library(1)["changed"])
        self.assertEqual(self.revision(), 1)
        entries = catalog(kind="movies")
        self.assertEqual(entries["total"], 1)
        self.assertEqual(entries["revision"], 1)
        first_id = entries["items"][0]["media_id"]

        # A periodic scan must not rebuild open clients without any change.
        self.assertFalse(library.scan_library(1)["changed"])
        self.assertEqual(self.revision(), 1)
        self.assertEqual(catalog(kind="movies")["items"][0]["media_id"], first_id)

        film.write_bytes(b"updated media data")
        self.assertTrue(library.scan_library(1)["changed"])
        self.assertEqual(self.revision(), 2)
        self.assertEqual(catalog(kind="movies")["items"][0]["media_id"], first_id)

        film.unlink()
        self.assertTrue(library.scan_library(1)["changed"])
        self.assertEqual(self.revision(), 3)
        self.assertEqual(catalog(kind="movies")["total"], 0)

    def test_new_episode_in_existing_show_updates_revision(self):
        tv = self.movies / "Example"
        tv.mkdir()
        (tv / "Example.S01E01.mkv").write_bytes(b"one")
        with library.db() as conn:
            conn.execute("UPDATE libraries SET kind='tv' WHERE id=1")
        self.assertTrue(library.scan_library(1)["changed"])
        before = catalog(kind="tv")
        self.assertEqual(before["items"][0]["files"], 1)
        (tv / "Example.S01E02.mkv").write_bytes(b"two")
        self.assertTrue(library.scan_library(1)["changed"])
        after = catalog(kind="tv")
        self.assertEqual(after["total"], 1)
        self.assertEqual(after["items"][0]["files"], 2)
        self.assertGreater(after["revision"], before["revision"])


if __name__ == "__main__":
    unittest.main()
