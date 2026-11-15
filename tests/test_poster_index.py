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
        with patch.object(poster_index, "_collect", return_value={identity: ("Test Show", None)}), \\
             patch.object(poster_index, "_resolve", return_value="/api/artwork/" + "b" * 64) as resolve, \\
             patch.object(poster_index, "_prepare") as prepare:
            self.assertEqual(poster_index.prepare_batch(8), 1)
            self.assertEqual(poster_index.prepare_batch(8), 0)
            prepare.assert_called_once()
        resolve.assert_called_once()
        items = [{"kind": "tv", "library_id": 2, "key": "test show:"}]
        poster_index.attach_posters(items)
        self.assertTrue(items[0]["poster_url"].endswith("b" * 64))

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
