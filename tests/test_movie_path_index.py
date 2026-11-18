import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from server import library, movies
from server.catalog import movie_info

COUNT = 300


class MoviePathIndexTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        patcher = patch.object(library, "DB_PATH", Path(directory.name) / "t.sqlite3")
        patcher.start()
        self.addCleanup(patcher.stop)
        movies._PATH_INDEX.clear()
        self.addCleanup(movies._PATH_INDEX.clear)
        with library.db() as conn:
            conn.execute("INSERT INTO libraries(id,name,kind,path) "
                         "VALUES (1,'Movies','movies','/media/Movies')")
            conn.execute("INSERT INTO libraries(id,name,kind,path) "
                         "VALUES (2,'TV','tv','/media/TV')")
            for index in range(COUNT):
                self.add_file(conn, "/media/Movies/Film %03d (%d)/Film %03d.mkv"
                              % (index, 1990 + index % 30, index))

    def add_file(self, conn, path):
        conn.execute("INSERT INTO media(library_id,path,title,size,mtime_ns,added_at) "
                     "VALUES (1,?,?,1,0,'2026-11-14')", (path, Path(path).stem))

    def key(self, index):
        return "film %03d:%d" % (index, 1990 + index % 30)

    def test_lookup_matches_the_brute_force_scan(self):
        for index in (0, 7, 150, COUNT - 1):
            parsed, path, root = movies._movie_path(1, self.key(index))
            expected = movie_info(str(path), root)
            self.assertEqual(parsed, expected)
            self.assertEqual(path.parent.name, "Film %03d (%d)" % (index, 1990 + index % 30))
            self.assertEqual(root, Path("/media/Movies"))

    def test_many_lookups_parse_the_library_once(self):
        calls = []
        real = movies.movie_info
        with patch.object(movies, "movie_info",
                          side_effect=lambda *a: calls.append(1) or real(*a)):
            started = time.perf_counter()
            for index in range(COUNT):
                movies._movie_path(1, self.key(index))
            elapsed = time.perf_counter() - started
        self.assertEqual(len(calls), COUNT, "each file must be parsed once, not per lookup")
        self.assertLess(elapsed, 2.0)

    def test_missing_movie_and_wrong_library_kind_are_404(self):
        for library_id, key in ((1, "nothing:1999"), (2, "film 001:1991"), (9, "x:")):
            with self.subTest(library_id=library_id), self.assertRaises(HTTPException) as caught:
                movies._movie_path(library_id, key)
            self.assertEqual(caught.exception.status_code, 404)

    def test_index_follows_added_and_removed_media(self):
        with self.assertRaises(HTTPException):
            movies._movie_path(1, "brand new:2024")
        with library.db() as conn:
            self.add_file(conn, "/media/Movies/Brand New (2024)/Brand New.mkv")
        self.assertEqual(movies._movie_path(1, "brand new:2024")[0]["title"], "Brand New")
        with library.db() as conn:
            conn.execute("DELETE FROM media WHERE path LIKE '%Brand New%'")
        with self.assertRaises(HTTPException):
            movies._movie_path(1, "brand new:2024")

    def test_index_rebuilds_when_the_catalog_revision_changes(self):
        movies._movie_path(1, self.key(1))
        with library.db() as conn:
            conn.execute("UPDATE media SET path='/media/Movies/Renamed (2001)/Renamed.mkv' "
                         "WHERE path LIKE '/media/Movies/Film 001 %'")
            conn.execute("UPDATE catalog_state SET revision=revision+1 WHERE id=1")
        with self.assertRaises(HTTPException):
            movies._movie_path(1, self.key(1))
        self.assertEqual(movies._movie_path(1, "renamed:2001")[0]["title"], "Renamed")

    def test_duplicate_keys_resolve_to_the_first_path_like_the_old_scan(self):
        with library.db() as conn:
            self.add_file(conn, "/media/Movies/Film 005 (1995)/Film 005 4K.mkv")
            self.add_file(conn, "/media/Movies/Archive/Film 005 (1995)/a.mkv")
        _, path, _ = movies._movie_path(1, self.key(5))
        self.assertEqual(str(path), "/media/Movies/Archive/Film 005 (1995)/a.mkv")

    def test_callers_cannot_corrupt_the_cached_entry(self):
        first = movies._movie_path(1, self.key(3))[0]
        first["title"] = "mutated"
        self.assertNotEqual(movies._movie_path(1, self.key(3))[0]["title"], "mutated")


if __name__ == "__main__":
    unittest.main()
