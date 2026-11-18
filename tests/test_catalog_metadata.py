import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from server import arr, catalog_metadata, library, movies, poster_index, tv
from server.catalog import catalog


class CatalogMetadataTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        patcher = patch.object(library, "DB_PATH", Path(directory.name) / "test.sqlite3")
        patcher.start()
        self.addCleanup(patcher.stop)
        with library.db() as conn:
            conn.execute(
                "INSERT INTO libraries(id,name,kind,path) VALUES (1,'Movies','movies','/media/Movies')"
            )
            conn.execute(
                "INSERT INTO libraries(id,name,kind,path) VALUES (2,'TV Shows','tv','/media/TV')"
            )
            conn.execute(
                "INSERT INTO media(id,library_id,path,title,size,mtime_ns,added_at) "
                "VALUES (1,1,'/media/Movies/The Thing (1982)/The Thing.mkv','The Thing',100,0,'2026-11-14')"
            )
            conn.execute(
                "INSERT INTO media(id,library_id,path,title,size,mtime_ns,added_at) "
                "VALUES (2,2,'/media/TV/Severance/Season 01/Severance.S01E01.mkv','Severance',100,0,'2026-11-14')"
            )

    def test_bulk_radarr_sonarr_sync_populates_sorting_and_genre(self):
        radarr = [{
            "title": "The Thing", "year": 1982,
            "genres": ["Horror", "Science Fiction"], "runtime": 109,
            "ratings": {"imdb": {"value": 8.2}},
        }]
        sonarr = [{
            "title": "Severance", "year": 2022,
            "genres": ["Drama", "Science Fiction"], "runtime": 52,
            "ratings": {"tmdb": {"value": 8.6}},
        }]
        with patch.object(movies, "_snapshot", return_value=radarr), \
             patch.object(movies, "_details", side_effect=AssertionError("unneeded movie lookup")), \
             patch.object(arr, "_settings", return_value={"url": "http://localhost:8989",
                                                          "api_key": "private-token"}), \
             patch.object(arr, "_request", return_value=sonarr) as req, \
             patch.object(tv, "show_metadata", side_effect=AssertionError("unneeded TV lookup")):
            report = catalog_metadata.sync_once()
        self.assertEqual(report["updated"], 2)
        self.assertEqual(report["processed"], 2)
        req.assert_called_once()
        movie = catalog(kind="movies", sort="rating")
        self.assertEqual(movie["genres"], ["Horror", "Science Fiction"])
        self.assertEqual(movie["items"][0]["rating"], 8.2)
        self.assertEqual(movie["items"][0]["runtime"], 109)
        self.assertEqual(catalog(kind="movies", genre="Horror")["total"], 1)
        show = catalog(kind="tv", sort="length")
        self.assertEqual(show["genres"], ["Drama", "Science Fiction"])
        self.assertEqual(show["items"][0]["rating"], 8.6)
        self.assertEqual(show["items"][0]["runtime"], 52)
        self.assertNotIn("private-token", str(movie) + str(show))

    def test_fallback_to_local_or_tmdb_metadata_when_manager_does_not_match(self):
        with patch.object(movies, "_snapshot", return_value=[]), \
             patch.object(arr, "_settings", return_value=None), \
             patch.object(movies, "_details", return_value={
                 "genres": ["Horror"], "runtime": 109, "tmdb_rating": 8.1
             }) as details, \
             patch.object(tv, "show_metadata", return_value={
                 "genres": ["Thriller"], "rating": 7.5, "episode_run_time": [47]
             }) as show:
            catalog_metadata.sync_once()
        details.assert_called_once()
        show.assert_called_once()
        self.assertEqual(catalog(kind="movies", sort="rating")["items"][0]["rating"], 8.1)
        self.assertEqual(catalog(kind="tv", sort="length")["items"][0]["runtime"], 47)
        self.assertEqual(catalog(kind="tv", genre="Thriller")["total"], 1)

    def test_partial_manager_fields_are_completed_by_automatic_lookup(self):
        # A rating alone must not suppress genres and runtime enrichment.
        radarr = [{"title": "The Thing", "year": 1982,
                   "ratings": {"imdb": {"value": 8.2}}, "genres": [], "runtime": None}]
        sonarr = [{"title": "Severance", "year": 2022,
                   "rating": 8.6, "genres": ["Drama"], "runtime": None}]
        with patch.object(movies, "_snapshot", return_value=radarr), \
             patch.object(movies, "_details", return_value={
                 "genres": ["Horror"], "runtime": 109
             }) as details, \
             patch.object(arr, "_settings", return_value={"url": "http://localhost:8989"}), \
             patch.object(arr, "_request", return_value=sonarr), \
             patch.object(tv, "show_metadata", return_value={
                 "genres": ["Mystery"], "rating": 9.0, "runtime": 52
             }) as show:
            report = catalog_metadata.sync_once()
        self.assertEqual(report["available"], 2)
        self.assertEqual(report["missing"], 0)
        details.assert_called_once()
        show.assert_called_once()
        movie = catalog(kind="movies")["items"][0]
        self.assertEqual(movie["genres"], ["Horror"])
        self.assertEqual(movie["rating"], 8.2)
        self.assertEqual(movie["runtime"], 109)
        series = catalog(kind="tv")["items"][0]
        self.assertEqual(series["genres"], ["Drama"])
        self.assertEqual(series["rating"], 8.6)
        self.assertEqual(series["runtime"], 52)
        # An unchanged second pass is still 100% available.
        with patch.object(movies, "_snapshot", return_value=radarr), \
             patch.object(movies, "_details", return_value={
                 "genres": ["Horror"], "runtime": 109
             }), \
             patch.object(arr, "_settings", return_value={"url": "http://localhost:8989"}), \
             patch.object(arr, "_request", return_value=sonarr), \
             patch.object(tv, "show_metadata", return_value={
                 "genres": ["Mystery"], "runtime": 52
             }):
            report = catalog_metadata.sync_once()
        self.assertEqual(report["updated"], 0)
        self.assertEqual(report["available"], 2)

    def test_auto_refresh_on_changed_library_even_during_cooldown(self):
        # Reset worker state after this test to avoid leaking to other tests.
        before = dict(catalog_metadata._state)
        self.addCleanup(lambda: catalog_metadata._state.update(before))
        catalog_metadata._state.update({
            "running": False, "total": 2, "missing": 0,
            "last_finished": 10**12, "last_signature": (2, 2, 0, 2)
        })
        with patch.object(catalog_metadata, "_library_signature",
                          side_effect=[(2, 2, 0, 2), (3, 3, 0, 2)]), \
             patch.object(catalog_metadata.threading.Thread, "start") as start:
            self.assertFalse(catalog_metadata.start_refresh())
            self.assertTrue(catalog_metadata.start_refresh())
        start.assert_called_once()
        self.assertTrue(catalog_metadata._state["running"])

    def test_genre_filter_is_populated_from_actual_catalog_response(self):
        page = (Path(__file__).resolve().parents[1] / "server/catalog.html").read_text()
        # Defining updateGenreChoices alone did not make the dropdown functional.
        # It must run after every successful catalog fetch, including re-indexing.
        self.assertIn("updateGenreChoices(data.genres);", page)
        self.assertGreaterEqual(page.count("updateGenreChoices("), 2)
        self.assertIn("const items=Array.isArray(genres)?genres.filter(", page)
        self.assertIn("genre: str = Query", (Path(__file__).resolve().parents[1] /
                                            "server/main.py").read_text())

    def test_metadata_state_reports_coverage_not_only_new_updates(self):
        # The worker reports how much of the library has metadata, not only how
        # many titles changed on the last pass...
        state = catalog_metadata.status()
        for field in ("total", "processed", "updated", "available", "missing"):
            self.assertIn(field, state)
        # ...but the library page deliberately keeps it silent: no banner that
        # could move the grid or distract during remote browsing.
        page = (Path(__file__).resolve().parents[1] / "server/catalog.html").read_text()
        self.assertIn("Background metadata status is intentionally silent", page)
        self.assertNotIn("Metadata available for ", page)
        self.assertNotIn("Unmatched titles are retried automatically.", page)

    def test_metadata_retry_starts_at_app_lifespan_and_skips_ffprobe(self):
        main = (Path(__file__).resolve().parents[1] / "server/main.py").read_text()
        worker = (Path(__file__).resolve().parents[1] / "server/catalog_metadata.py").read_text()
        self.assertIn("target=catalog_metadata_refresh_loop", main)
        self.assertIn("metadata_stop.set()", main)
        self.assertIn("include_video_format=False", worker)

    def test_library_ui_does_not_require_manual_refresh(self):
        page = (Path(__file__).resolve().parents[1] / "server/catalog.html").read_text()
        # The refresh control is an optional recovery action; normal library
        # loads still start and poll metadata sync automatically...
        self.assertIn("checkMetadata();", page)
        self.assertIn("fetch('/api/catalog/metadata/status'", page)
        # ...and titles without metadata are retried by the worker itself, sooner
        # than a fully matched library is rescanned.
        self.assertLess(catalog_metadata.MISSING_RETRY_SECONDS,
                        catalog_metadata.RESCAN_SECONDS)
        worker = (Path(__file__).resolve().parents[1] / "server/catalog_metadata.py").read_text()
        self.assertIn('MISSING_RETRY_SECONDS if _state["missing"] else RESCAN_SECONDS', worker)

    def test_older_poster_is_preserved_and_missing_data_never_erases_fields(self):
        identity = ("movies", 1, "the thing:1982")
        image = "/api/artwork/" + "a" * 64
        with library.db() as conn:
            poster_index._table(conn)
            conn.execute(
                "INSERT INTO indexed_posters(kind,library_id,show_key,poster_url,checked_at) "
                "VALUES(?,?,?,?,?)", (*identity, image, 111)
            )
        self.assertTrue(catalog_metadata._persist(*identity, {
            "genres": ["Horror"], "rating": 8.2, "runtime": 109
        }))
        self.assertFalse(catalog_metadata._persist(*identity, {}))
        with library.db() as conn:
            row = conn.execute(
                "SELECT poster_url,metadata_json,checked_at FROM indexed_posters "
                "WHERE kind=? AND library_id=? AND show_key=?", identity
            ).fetchone()
        self.assertEqual(row["poster_url"], image)
        self.assertEqual(row["checked_at"], 111)
        self.assertEqual(json.loads(row["metadata_json"])["genres"], ["Horror"])

    def test_poster_reindex_cannot_overwrite_existing_genre_with_empty_data(self):
        identity = ("movies", 1, "the thing:1982")
        catalog_metadata._persist(*identity, {
            "genres": ["Horror"], "rating": 8.2, "runtime": 109
        })
        with patch.object(poster_index, "_collect", return_value={
            identity: ("The Thing", 1982)}), \
             patch.object(poster_index, "_resolve", return_value=(None, {})):
            poster_index.prepare_batch(2)
        values = catalog(kind="movies")["items"][0]
        self.assertEqual(values["genres"], ["Horror"])
        self.assertEqual(values["rating"], 8.2)
        self.assertEqual(values["runtime"], 109)

    def test_rating_object_and_missing_metadata_handled(self):
        meta = poster_index._safe_metadata({
            "rating": {"value": 8.9, "votes": 1200},
            "genres": ["Drama"], "runtime": "53",
        })
        self.assertEqual(meta, {"rating": 8.9, "genres": ["Drama"], "runtime": 53})
        self.assertFalse(catalog_metadata._has_metadata({
            "rating": None, "genres": [], "runtime": None
        }))


if __name__ == "__main__":
    unittest.main()
