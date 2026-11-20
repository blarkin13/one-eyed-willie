import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from server import library
from server.catalog import catalog, title_sort_key
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
        self.assertEqual(
            [(lib["name"], [item["title"] for item in lib["items"]])
             for lib in data["recent_libraries"]],
            [("Movies", ["Arrival", "Alien"]), ("TV Shows", ["Severance"])]
        )

    def test_recently_added_is_separate_for_each_movie_library(self):
        with library.db() as connection:
            connection.execute(
                "INSERT INTO libraries(id,name,kind,path) "
                "VALUES(3,'Horror','movies','/media/Horror')"
            )
            media = [
                (4, 3, '/media/Horror/The Thing (1982)/The Thing.mkv',
                 'The Thing', 10, '2026-11-18 10:00:00'),
                (5, 3, '/media/Horror/Get Out (2017)/Get Out.mkv',
                 'Get Out', 999999, '2026-11-17 10:00:00'),
                (6, 1, '/media/Movies/Dune (2021)/Dune.mkv',
                 'Dune', 0, '2026-11-19 10:00:00'),
                (7, 3, '/media/Horror/Alien (1979)/Alien.mkv',
                 'Alien', 30, '2026-11-16 10:00:00'),
            ]
            for media_id, lib_id, path, title, mtime, added in media:
                connection.execute(
                    "INSERT INTO media(id,library_id,path,title,size,mtime_ns,added_at) "
                    "VALUES(?,?,?,?,100,?,?)",
                    (media_id, lib_id, path, title, mtime, added)
                )
        data = home_shelves()
        shelves = {row["name"]: row for row in data["recent_libraries"]}
        self.assertEqual(list(shelves), ["Movies", "Horror", "TV Shows"])
        self.assertEqual(
            [item["title"] for item in shelves["Movies"]["items"]],
            ["Dune", "Arrival", "Alien"]
        )
        self.assertEqual(
            [item["title"] for item in shelves["Horror"]["items"]],
            ["The Thing", "Get Out", "Alien"]
        )
        self.assertEqual(
            {item["library_id"] for item in shelves["Movies"]["items"]}, {1}
        )
        self.assertEqual(
            {item["library_id"] for item in shelves["Horror"]["items"]}, {3}
        )
        self.assertEqual(data["totals"], {"movies": 6, "tv": 1})

    def test_recently_added_limit_applies_separately_to_libraries(self):
        with library.db() as connection:
            connection.execute(
                "INSERT INTO libraries(id,name,kind,path) "
                "VALUES(3,'Horror','movies','/media/Horror')"
            )
            for number in range(20):
                path = f'/media/Horror/Film {number} (2020)/Film {number}.mkv'
                connection.execute(
                    "INSERT INTO media(library_id,path,title,size,mtime_ns,added_at) "
                    "VALUES(3,?,?,100,0,?)",
                    (path, f'Film {number}', f'2026-11-16 10:00:{number:02d}')
                )
        shelves = {row["name"]: row["items"]
                   for row in home_shelves()["recent_libraries"]}
        self.assertEqual([item["title"] for item in shelves["Movies"]],
                         ["Arrival", "Alien"])
        self.assertEqual(len(shelves["Horror"]), 16)
        self.assertEqual([item["title"] for item in shelves["Horror"][:2]],
                         ["Film 19", "Film 18"])

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

    def test_unknown_duration_movie_and_episode_are_in_continue_watching(self):
        # Fragmented/HLS playback can provide a valid position but unknown
        # duration; both must still appear in Continue Watching.
        movie = update_playback(PlaybackUpdate(
            media_id=1, position_seconds=180, duration_seconds=0
        ))
        episode = update_playback(PlaybackUpdate(
            media_id=3, position_seconds=300, duration_seconds=0
        ))
        self.assertTrue(movie["saved"])
        self.assertFalse(movie["completed"])
        self.assertTrue(episode["saved"])
        self.assertFalse(episode["completed"])
        shelf = home_shelves()["continue_watching"]
        self.assertEqual(len(shelf), 2)
        by_id = {entry["media_id"]: entry for entry in shelf}
        self.assertEqual(by_id[1]["kind"], "movies")
        self.assertEqual(by_id[1]["position_seconds"], 180)
        self.assertEqual(by_id[1]["progress_percent"], None)
        self.assertEqual(by_id[3]["kind"], "tv")
        self.assertEqual(by_id[3]["position_seconds"], 300)
        self.assertEqual(by_id[3]["progress_percent"], None)

    def test_unknown_duration_resume_becomes_known_and_completes(self):
        update_playback(PlaybackUpdate(
            media_id=1, position_seconds=180, duration_seconds=0
        ))
        update_playback(PlaybackUpdate(
            media_id=1, position_seconds=185, duration_seconds=1800
        ))
        shelf = home_shelves()["continue_watching"]
        self.assertEqual(len(shelf), 1)
        self.assertEqual(shelf[0]["progress_percent"], 10)
        self.assertEqual(shelf[0]["duration_seconds"], 1800)
        update_playback(PlaybackUpdate(
            media_id=1, position_seconds=1800, duration_seconds=0, completed=True
        ))
        self.assertEqual(home_shelves()["continue_watching"], [])

    def test_short_unknown_duration_progress_below_threshold_is_hidden(self):
        update_playback(PlaybackUpdate(
            media_id=1, position_seconds=12, duration_seconds=0
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

    def test_recent_movies_same_scan_order_by_file_modification_not_insert_id(self):
        # Files seen on the same scan share a first-seen timestamp; use the
        # file timestamp to order recently downloaded movies.
        with library.db() as connection:
            connection.execute(
                "INSERT INTO media(id,library_id,path,title,size,mtime_ns,added_at) "
                "VALUES(4,1,'/media/Movies/The Batman (2022)/The Batman.mkv',"
                "'The Batman',100,900,'2026-11-14 10:00:00')"
            )
            connection.execute(
                "INSERT INTO media(id,library_id,path,title,size,mtime_ns,added_at) "
                "VALUES(5,1,'/media/Movies/The Thing (1982)/The Thing.mkv',"
                "'The Thing',100,700,'2026-11-14 10:00:00')"
            )
            connection.execute(
                "INSERT INTO media(id,library_id,path,title,size,mtime_ns,added_at) "
                "VALUES(6,1,'/media/Movies/The Matrix (1999)/The Matrix.mkv',"
                "'The Matrix',100,800,'2026-11-14 10:00:00')"
            )
        home = home_shelves()
        self.assertEqual([x["title"] for x in home["recent_movies"][:3]],
                         ["The Batman", "The Matrix", "The Thing"])
        recent = catalog(kind="movies", sort="added")
        self.assertEqual([x["title"] for x in recent["items"][:3]],
                         ["The Batman", "The Matrix", "The Thing"])

    def test_title_articles_ignored_in_sort_and_navigation(self):
        self.assertEqual(title_sort_key("The Batman"), "batman")
        self.assertEqual(title_sort_key("A Quiet Place"), "quiet place")
        self.assertEqual(title_sort_key("An American Werewolf"), "american werewolf")
        self.assertEqual(title_sort_key("Alien"), "alien")
        with library.db() as connection:
            connection.execute(
                "INSERT INTO media(id,library_id,path,title,size,mtime_ns,added_at) "
                "VALUES(4,1,'/media/Movies/The Batman (2022)/The Batman.mkv',"
                "'The Batman',100,0,'2026-11-14 10:00:00')"
            )
        titles = [x["title"] for x in catalog(kind="movies", sort="title")["items"]]
        self.assertEqual(titles, ["Alien", "Arrival", "The Batman"])

    def test_length_rating_and_genre_use_indexed_metadata_with_missing_last(self):
        from server.poster_index import _table
        import json
        with library.db() as connection:
            _table(connection)
            rows = [
                ("movies", 1, "alien:1979", {"genres": ["Horror", "Science Fiction"], "runtime": 117, "rating": 8.5}),
                ("movies", 1, "arrival:2016", {"genres": ["Drama", "Science Fiction"], "runtime": 116, "rating": 7.9}),
            ]
            for kind, lib, key, meta in rows:
                connection.execute(
                    "INSERT INTO indexed_posters(kind,library_id,show_key,poster_url,checked_at,metadata_json) "
                    "VALUES(?,?,?,?,?,?)", (kind, lib, key, None, 0, json.dumps(meta))
                )
            connection.execute(
                "INSERT INTO media(id,library_id,path,title,size,mtime_ns,added_at) "
                "VALUES(4,1,'/media/Movies/The Batman (2022)/The Batman.mkv',"
                "'The Batman',100,0,'2026-11-14 10:00:00')"
            )
        longest = catalog(kind="movies", sort="length")
        self.assertEqual([x["title"] for x in longest["items"]],
                         ["Alien", "Arrival", "The Batman"])
        best = catalog(kind="movies", sort="rating")
        self.assertEqual([x["title"] for x in best["items"]],
                         ["Alien", "Arrival", "The Batman"])
        self.assertEqual(best["items"][0]["rating"], 8.5)
        self.assertEqual(best["items"][0]["runtime"], 117)
        horror = catalog(kind="movies", genre="hOrRoR")
        self.assertEqual([x["title"] for x in horror["items"]], ["Alien"])
        self.assertEqual(horror["genres"], ["Drama", "Horror", "Science Fiction"])
        self.assertEqual(catalog(kind="movies", genre="comedy")["total"], 0)
        self.assertEqual(catalog(kind="tv", genre="Horror")["total"], 0)

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
