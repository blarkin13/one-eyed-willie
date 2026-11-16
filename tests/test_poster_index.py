import io
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from server import artwork, library, poster_index


class PosterIndexTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        for obj, name, value in [
            (library, "DB_PATH", root / "library.sqlite3"),
            (artwork, "CACHE_DIR", root / "artwork"),
            (artwork, "THUMB_DIR", root / "artwork/thumbs"),
        ]:
            p = patch.object(obj, name, value)
            p.start()
            self.addCleanup(p.stop)

    def test_catalog_attach_never_contacts_metadata_provider(self):
        identity = ("tv", 2, "different title:")
        with library.db() as conn:
            poster_index._table(conn)
            conn.execute(
                "INSERT INTO indexed_posters(kind,library_id,show_key,poster_url,checked_at) "
                "VALUES(?,?,?,?,?)", (*identity, "/api/artwork/" + "a" * 64, int(time.time()))
            )
        items = [{"kind": "tv", "library_id": 2, "key": "different title:", "title": "Different title"}]
        with patch.object(poster_index, "_resolve", side_effect=AssertionError("network call")):
            poster_index.attach_posters(items)
        self.assertEqual(items[0]["poster_url"], "/api/artwork/thumb/" + "a" * 64)

    def test_batch_prefetch_saves_validated_index_and_respects_retry(self):
        identity = ("tv", 2, "test show:")
        with patch.object(poster_index, "_collect", return_value={identity: ("Test Show", None)}), \
             patch.object(poster_index, "_resolve", return_value="/api/artwork/" + "b" * 64) as resolve, \
             patch.object(poster_index, "_prepare") as prepare:
            self.assertEqual(poster_index.prepare_batch(8), 1)
            self.assertEqual(poster_index.prepare_batch(8), 0)
            prepare.assert_called_once()
        resolve.assert_called_once()
        items = [{"kind": "tv", "library_id": 2, "key": "test show:"}]
        poster_index.attach_posters(items)
        self.assertTrue(items[0]["poster_url"].endswith("b" * 64))

    def test_tv_posters_are_prioritized_before_movies(self):
        movie=("movies", 1, "movie:2023")
        show=("tv", 2, "series:")
        work={movie: ("Movie", 2023), show: ("Series", None)}
        calls=[]
        with patch.object(poster_index, "_collect", return_value=work), \
             patch.object(poster_index, "_resolve", side_effect=lambda kind, lib, key, title, year: (
                 calls.append(kind) or "/api/artwork/" + "d"*64
             )), patch.object(poster_index, "_prepare"):
            poster_index.prepare_batch(1)
        self.assertEqual(calls, ["tv"])

    def test_detail_page_poster_is_reused_by_home(self):
        digest="e"*64
        poster_index.remember("tv", 2, "series:", "/api/artwork/"+digest)
        entries=[{"kind":"tv","library_id":2,"key":"series:"}]
        with patch.object(poster_index, "_resolve", side_effect=AssertionError("must not search provider")):
            poster_index.attach_posters(entries)
        self.assertEqual(entries[0]["poster_url"], "/api/artwork/thumb/"+digest)

    def test_invalidate_only_targeted_record(self):
        identities = [("tv", 2, "one:"), ("tv", 2, "two:")]
        with library.db() as conn:
            poster_index._table(conn)
            conn.executemany(
                "INSERT INTO indexed_posters(kind,library_id,show_key,poster_url,checked_at) "
                "VALUES(?,?,?,?,?)",
                [(*identity, "/api/artwork/" + "b" * 64, int(time.time())) for identity in identities],
            )
        poster_index.invalidate("tv", 2, "one:")
        entries = [{"kind": kind, "library_id": lib, "key": key} for kind, lib, key in identities]
        poster_index.attach_posters(entries)
        self.assertIsNone(entries[0]["poster_url"])
        self.assertIsNotNone(entries[1]["poster_url"])

    def test_existing_poster_gets_sortable_metadata_in_background(self):
        import json
        identity = ("movies", 1, "the batman:2022")
        with library.db() as conn:
            poster_index._table(conn)
            conn.execute(
                "INSERT INTO indexed_posters(kind,library_id,show_key,poster_url,checked_at) "
                "VALUES(?,?,?,?,?)",
                (*identity, "/api/artwork/" + "a" * 64, int(time.time()))
            )
        metadata = {"genres": ["Action", "Drama"], "rating": 7.8, "runtime": 176}
        with patch.object(poster_index, "_collect", return_value={identity: ("The Batman", 2022)}), \
             patch.object(poster_index, "_resolve", return_value=(None, metadata)) as resolve:
            self.assertEqual(poster_index.prepare_batch(4), 1)
            self.assertEqual(poster_index.prepare_batch(4), 0)
        resolve.assert_called_once()
        with library.db() as conn:
            row = conn.execute(
                "SELECT poster_url,metadata_json FROM indexed_posters "
                "WHERE kind='movies' AND library_id=1 AND show_key='the batman:2022'"
            ).fetchone()
        self.assertEqual(row["poster_url"], "/api/artwork/" + "a" * 64)
        self.assertEqual(json.loads(row["metadata_json"]), metadata)

    def test_only_valid_sort_metadata_is_saved(self):
        self.assertEqual(poster_index._safe_metadata({
            "genres": ["Horror", "Drama", 9],
            "ratings": {"tmdb": {"value": 7.9}},
            "runtime": 120,
        }), {"genres": ["Horror", "Drama"], "rating": 7.9, "runtime": 120})
        invalid = poster_index._safe_metadata({"rating": "nan", "runtime": 0})
        self.assertIsNone(invalid["rating"])
        self.assertIsNone(invalid["runtime"])

    def test_real_image_is_resized_and_kept_privately(self):
        digest = "c" * 64
        artwork.CACHE_DIR.mkdir(parents=True)
        picture = Image.new("RGB", (750, 1100), (30, 60, 90))
        picture.save(artwork.CACHE_DIR / digest, "JPEG")
        with library.db() as conn:
            artwork._table(conn)
            conn.execute(
                "INSERT INTO artwork_assets(digest,source,kind,mime) VALUES(?,?,?,?)",
                (digest, "https://image.tmdb.org/t/p/w342/abc.jpg", "remote", "image/jpeg"),
            )
        self.assertTrue(artwork.warm_thumbnail(digest))
        target = artwork.THUMB_DIR / (digest + ".jpg")
        with Image.open(target) as image:
            self.assertLessEqual(image.width, 360)
            self.assertLessEqual(image.height, 540)
        self.assertTrue(artwork.warm_thumbnail(digest))


if __name__ == "__main__":
    unittest.main()
