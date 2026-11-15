import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from server import library
from server.catalog import catalog
from server.home import PlaybackUpdate, home_shelves, update_playback


class HomeDashboardTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.patch = patch.object(library, "DB_PATH", Path(self.directory.name) / "library.sqlite3")
        self.patch.start()
        self.addCleanup(self.patch.stop)
        with library.db() as connection:
            connection.execute(
                "INSERT INTO libraries(id,name,kind,path) VALUES(1,'Movies','movies','/media/Movies')"
            )
            connection.execute(
                "INSERT INTO libraries(id,name,kind,path) VALUES(2,'TV Shows','tv','/media/TV')"
            )
            connection.execute(
                "INSERT INTO media(id,library_id,path,title,size,mtime_ns,added_at) "
                "VALUES(1,1,'/media/Movies/Alien (1979)/Alien.mkv','Alien',100,0,'2026-11-11 10:00:00')"
            )
            connection.execute(
                "INSERT INTO media(id,library_id,path,title,size,mtime_ns,added_at) "
                "VALUES(2,1,'/media/Movies/Arrival (2016)/Arrival.mkv','Arrival',100,0,'2026-11-12 10:00:00')"
            )
            connection.execute(
                "INSERT INTO media(id,library_id,path,title,size,mtime_ns,added_at) "
                "VALUES(3,2,'/media/TV/Severance/Season 01/Severance.S01E02.mkv','Severance',100,0,'2026-11-13 10:00:00')"
            )

    def test_home_sections_are_grounded_in_library(self):
        data = home_shelves()
        self.assertEqual([m["title"] for m in data["recent_movies"]], ["Arrival", "Alien"])
        self.assertEqual([t["title"] for t in data["recent_tv"]], ["Severance"])
        self.assertEqual(data["totals"], {"movies": 2, "tv": 1})
        self.assertEqual(data["continue_watching"], [])
        self.assertTrue(data["playback_available"])

    def test_unfinished_progress_and_completion(self):
        saved = update_playback(PlaybackUpdate(
            media_id=3, position_seconds=650, duration_seconds=2400
        ))
        self.assertTrue(saved["saved"])
        watching = home_shelves()["continue_watching"]
        self.assertEqual(len(watching), 1)
        self.assertEqual(watching[0]["title"], "Severance")
        self.assertEqual(watching[0]["subtitle"], "S01 · E02")
        self.assertEqual(watching[0]["progress_percent"], 27)
        update_playback(PlaybackUpdate(
            media_id=3, position_seconds=2395, duration_seconds=2400
        ))
        self.assertEqual(home_shelves()["continue_watching"], [])

    def test_invalid_progress_rejected(self):
        with self.assertRaises(HTTPException):
            update_playback(PlaybackUpdate(
                media_id=2, position_seconds=400, duration_seconds=200
            ))
        with self.assertRaises(HTTPException):
            update_playback(PlaybackUpdate(
                media_id=9999, position_seconds=40, duration_seconds=200
            ))

    def test_recent_sorting_and_pagination(self):
        recent = catalog(kind="movies", sort="recent", limit=1)
        self.assertEqual(recent["total"], 2)
        self.assertEqual([m["title"] for m in recent["items"]], ["Arrival"])
        second = catalog(kind="movies", sort="recent", offset=1, limit=1)
        self.assertEqual([m["title"] for m in second["items"]], ["Alien"])
        alpha = catalog(kind="movies", sort="title")
        self.assertEqual([m["title"] for m in alpha["items"]], ["Alien", "Arrival"])

    def test_progress_is_removed_with_library(self):
        update_playback(PlaybackUpdate(
            media_id=3, position_seconds=650, duration_seconds=2400
        ))
        library.delete_library(2)
        with library.db() as connection:
            self.assertEqual(connection.execute(
                "SELECT count(*) FROM playback_progress"
            ).fetchone()[0], 0)


class MediaMigrationTests(unittest.TestCase):
    def test_existing_database_gets_first_seen_column(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "legacy.sqlite3"
            connection = sqlite3.connect(path)
            connection.execute(
                "CREATE TABLE media (id INTEGER PRIMARY KEY,library_id INTEGER NOT NULL,"
                "path TEXT NOT NULL UNIQUE,title TEXT NOT NULL,size INTEGER NOT NULL,"
                "mtime_ns INTEGER NOT NULL)"
            )
            connection.execute(
                "INSERT INTO media(id,library_id,path,title,size,mtime_ns) "
                "VALUES(1,1,'/media/Movies/Alien.mkv','Alien',1,0)"
            )
            connection.commit()
            connection.close()
            with patch.object(library, "DB_PATH", path):
                with library.db() as upgraded:
                    added = upgraded.execute(
                        "SELECT added_at FROM media WHERE id=1"
                    ).fetchone()[0]
                    self.assertTrue(added)


if __name__ == "__main__":
    unittest.main()
