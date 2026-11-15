"""Regression tests for safe LAN streaming and movie ID resolution."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi import HTTPException
from server import playback
from server.library import db, scan_library

class PlaybackTests(unittest.TestCase):
    def test_stream_and_movie_lookup(self):
        with tempfile.TemporaryDirectory() as root:
            media_root = Path(root) / "media"
            movie_folder = media_root / "Movies"
            movie_folder.mkdir(parents=True)
            video = movie_folder / "Example (2024).mp4"
            video.write_bytes(b"not-a-real-video")
            database = Path(root) / "data.sqlite3"
            with patch("server.library.DB_PATH", database), patch("server.library.MEDIA_ROOT", media_root), patch("server.playback.MEDIA_ROOT", media_root):
                with db() as conn:
                    lib_id = conn.execute("INSERT INTO libraries (name,kind,path) VALUES (?,?,?)",
                                          ("Movies", "movies", str(movie_folder))).lastrowid
                scan_library(lib_id)
                resolved = playback.resolve_movie(lib_id, "example:2024")
                self.assertEqual(playback.media_file(resolved["media_id"]), video)
                self.assertEqual(playback.stream(resolved["media_id"]).media_type, "video/mp4")
                with self.assertRaises(HTTPException):
                    playback.media_file(999999)

    def test_indexed_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            media_root = Path(root) / "media"
            media_root.mkdir()
            outside = Path(root) / "outside.mp4"
            outside.write_bytes(b"private")
            link = media_root / "link.mp4"
            link.symlink_to(outside)
            database = Path(root) / "data.sqlite3"
            with patch("server.library.DB_PATH", database), patch("server.playback.MEDIA_ROOT", media_root):
                with db() as conn:
                    lib_id = conn.execute("INSERT INTO libraries (name,kind,path) VALUES (?,?,?)",
                                           ("Movies", "movies", str(media_root))).lastrowid
                    media_id = conn.execute(
                        "INSERT INTO media (library_id,path,title,size,mtime_ns) VALUES (?,?,?,?,?)",
                        (lib_id, str(link), "link", 7, 0)).lastrowid
                with self.assertRaises(HTTPException):
                    playback.media_file(media_id)
if __name__ == "__main__":
    unittest.main()
