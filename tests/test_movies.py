import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from server import artwork, library, movies


class MovieMetadataTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / "media"
        self.movies = self.root / "Movies"
        self.folder = self.movies / "Arrival (2016)"
        self.folder.mkdir(parents=True)
        self.movie_file = self.folder / "Arrival.2016.mkv"
        self.movie_file.write_bytes(b"fake video placeholder")
        patches = [
            patch.object(library, "DB_PATH", Path(temp.name) / "db.sqlite3"),
            patch.object(artwork, "CACHE_DIR", Path(temp.name) / "artwork"),
            patch.object(artwork, "MEDIA_ROOT", self.root),
            patch.object(movies, "MEDIA_ROOT", self.root),
            patch.object(movies, "SETTINGS_PATH", Path(temp.name) / "radarr-settings.json"),
        ]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)
        with library.db() as conn:
            conn.execute(
                "INSERT INTO libraries(id,name,kind,path) VALUES(1,'Movies','movies',?)",
                (str(self.movies),),
            )
            conn.execute(
                "INSERT INTO media(id,library_id,path,title,size,mtime_ns,added_at) "
                "VALUES(1,1,?,'Arrival',10,0,CURRENT_TIMESTAMP)",
                (str(self.movie_file),),
            )

    def test_local_poster_without_external_service(self):
        (self.folder / "poster.jpg").write_bytes(b"local artwork")
        with patch.object(movies, "_snapshot", return_value=[]):
            response = movies.movie_details(library_id=1, key="arrival:2016")
        self.assertTrue(response["poster_url"].startswith("/api/artwork/"))
        digest = response["poster_url"].split("/")[-1]
        result = artwork.artwork(digest)
        self.assertEqual(Path(result.path).read_bytes(), b"local artwork")

    def test_sidecar_nfo_description_and_imdb_link(self):
        (self.folder / "movie.nfo").write_text(
            "<movie><plot>Scientific-fiction story.</plot><runtime>116</runtime>"
            "<imdbid>tt2543164</imdbid><genre>Sci-Fi</genre></movie>"
        )
        with patch.object(movies, "_snapshot", return_value=[]):
            result = movies.movie_details(library_id=1, key="arrival:2016")
        self.assertEqual(result["overview"], "Scientific-fiction story.")
        self.assertEqual(result["runtime"], 116)
        self.assertEqual(result["imdb_url"], "https://www.imdb.com/title/tt2543164/")
        self.assertEqual(result["genres"], ["Sci-Fi"])

    def test_radarr_poster_and_synopsis_without_new_tmdb_key(self):
        poster = "https://image.tmdb.org/t/p/original/abc123.jpg"
        records = [{
            "title": "Arrival", "year": 2016, "poster_url": poster,
            "overview": "A linguist encounters visitors.",
            "runtime": 116, "genres": ["Sci-Fi"], "imdb_id": "tt2543164",
        }]
        with patch.object(movies, "_snapshot", return_value=records):
            movie = movies.movie_details(library_id=1, key="arrival:2016")
            posters = movies.movie_posters(movies.PosterBatch(
                items=[movies.MovieReference(library_id=1, key="arrival:2016")]
            ))
        self.assertEqual(movie["overview"], "A linguist encounters visitors.")
        self.assertTrue(movie["poster_url"].startswith("/api/artwork/"))
        self.assertEqual(posters["items"][0]["poster_url"], movie["poster_url"])

    def test_missing_or_ambiguous_year_not_mismatched(self):
        records = [{"title": "Arrival", "year": 2005}, {"title": "Arrival", "year": 2016}]
        self.assertEqual(movies._movie_match("Arrival", None, records), {})
        self.assertEqual(movies._movie_match("Arrival", 2016, records)["year"], 2016)
        self.assertEqual(movies._movie_match("Arrival", 2030, records), {})

    def test_public_radarr_urls_not_allowed(self):
        for url in ("http://8.8.8.8:7878", "http://localhost:7878",
                    "https://example.com:7878", "http://127.0.0.1:7878",
                    "http://192.168.86.29:7878@evil.example.com:7878"):
            with self.assertRaises(HTTPException):
                movies._base_url(url)
        self.assertEqual(movies._base_url("http://192.168.86.29:7878"),
                         "http://192.168.86.29:7878")

    def test_source_state_never_reveals_api_key(self):
        (movies.SETTINGS_PATH).write_text(
            '{"url":"http://192.168.86.29:7878","api_key":"sensitive-local-key"}'
        )
        response = movies.movie_source()
        self.assertTrue(response["connected"])
        self.assertNotIn("sensitive-local-key", str(response))

    def test_radarr_internal_poster_is_registered_without_credentials_in_url(self):
        (movies.SETTINGS_PATH).write_text(
            '{"url":"http://192.168.86.29:7878","api_key":"sensitive-local-key"}'
        )
        records = [{
            "title": "Arrival", "year": 2016,
            "poster_internal": "/MediaCover/123/poster.jpg?lastWrite=2026",
            "overview": "Existing Radarr artwork",
        }]
        with patch.object(movies, "_snapshot", return_value=records):
            result = movies.movie_details(library_id=1, key="arrival:2016")
        self.assertTrue(result["poster_url"].startswith("/api/artwork/"))
        with library.db() as conn:
            row = conn.execute("SELECT source,kind FROM artwork_assets").fetchone()
        self.assertEqual(row["kind"], "radarr")
        self.assertEqual(row["source"], "http://192.168.86.29:7878/MediaCover/123/poster.jpg")
        self.assertNotIn("sensitive-local-key", str(result))

    def test_remote_artwork_does_not_allow_radarr_arbitrary_path(self):
        (movies.SETTINGS_PATH).write_text(
            '{"url":"http://192.168.86.29:7878","api_key":"sensitive-local-key"}'
        )
        self.assertIsNone(artwork.register_radarr("/api/v3/system/status"))
        self.assertIsNone(artwork.register_radarr("/MediaCover/../config.xml"))

    def test_wrong_library_or_movie_returns_404(self):
        with self.assertRaises(HTTPException):
            movies.movie_details(library_id=1, key="other:2020")


if __name__ == "__main__":
    unittest.main()
