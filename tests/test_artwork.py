import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from server import artwork, library


class ArtworkCacheTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.folder = Path(temp.name)
        self.patch_db = patch.object(library, "DB_PATH", self.folder / "library.db")
        self.patch_cache = patch.object(artwork, "CACHE_DIR", self.folder / "artwork")
        self.patch_media = patch.object(artwork, "MEDIA_ROOT", self.folder / "media")
        for modifier in (self.patch_db, self.patch_cache, self.patch_media):
            modifier.start()
            self.addCleanup(modifier.stop)

    def test_download_once_and_serve_local_file(self):
        url = "https://static.tvmaze.com/uploads/images/medium_portrait/32.jpg"
        local = artwork.register_remote(url)
        self.assertRegex(local, r"^/api/artwork/[0-9a-f]{64}$")
        key = local.rsplit("/", 1)[-1]
        with patch.object(artwork, "_download", return_value=(b"fake_jpeg", "image/jpeg")) as download:
            first = artwork.artwork(key)
            second = artwork.artwork(key)
        self.assertEqual(download.call_count, 1)
        self.assertTrue(Path(first.path).exists())
        self.assertEqual(first.headers["cache-control"], "private, max-age=604800")
        self.assertEqual(second.media_type, "image/jpeg")

    def test_unregistered_id_returns_404_without_network(self):
        with self.assertRaises(HTTPException):
            artwork.artwork("a" * 64)

    def test_untrusted_image_sources_not_registered(self):
        for source in (
            "http://static.tvmaze.com/uploads/images/poster.jpg",
            "https://evil.example/poster.jpg",
            "https://static.tvmaze.com@127.0.0.1/poster.jpg",
            "https://static.tvmaze.com/other/place.jpg",
            "https://image.tmdb.org/t/p/w342/../../private.jpg",
            "http://127.0.0.1:8080/poster.jpg",
        ):
            self.assertIsNone(artwork.register_remote(source))

    def test_nested_metadata_uses_same_origin_links(self):
        url = "https://image.tmdb.org/t/p/w342/poster.jpg"
        response = artwork.localize({
            "title": "Severance", "poster_url": url,
            "seasons": [{"number": 1, "poster_url": url}],
        })
        self.assertTrue(response["poster_url"].startswith("/api/artwork/"))
        self.assertEqual(response["poster_url"], response["seasons"][0]["poster_url"])
        self.assertEqual(response["title"], "Severance")

    def test_poster_jpg_next_to_show_file_is_used(self):
        folder = self.folder / "media" / "TV" / "Severance"
        folder.mkdir(parents=True)
        poster = folder / "poster.jpg"
        poster.write_bytes(b"local poster")
        with library.db() as conn:
            conn.execute(
                "INSERT INTO libraries (id,name,kind,path) VALUES (1,'TV','tv',?)",
                (str(folder.parent),),
            )
            conn.execute(
                "INSERT INTO media (id,library_id,path,title,size,mtime_ns,added_at) "
                "VALUES (1,1,?,'S01E01',10,0,CURRENT_TIMESTAMP)",
                (str(folder / "Severance.S01E01.mkv"),),
            )
        link = artwork.local_show_poster(1, "severance:")
        self.assertTrue(link.startswith("/api/artwork/"))
        key = link.rsplit("/", 1)[-1]
        self.assertEqual(Path(artwork.artwork(key).path).read_bytes(), b"local poster")

    def test_local_poster_changes_generate_new_url(self):
        folder = self.folder / "media"
        folder.mkdir()
        path = folder / "poster.jpg"
        path.write_bytes(b"v1")
        first = artwork.register_local(path)
        path.write_bytes(b"v2")
        import os
        old = path.stat().st_mtime_ns
        os.utime(path, ns=(old + 1000000000, old + 1000000000))
        second = artwork.register_local(path)
        self.assertNotEqual(first, second)


if __name__ == "__main__":
    unittest.main()
