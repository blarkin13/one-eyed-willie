"""Music is scanned and served independently from the video catalog."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from server import library, music
from server.catalog import catalog
from server.home import home_shelves

class MusicLibraryTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        self.media=self.root/"media"
        self.musicdir=self.media/"Music"
        self.musicdir.mkdir(parents=True)
        self.song=self.musicdir/"Artist"/"Album"/"01 - Example.mp3"
        self.song.parent.mkdir(parents=True)
        self.song.write_bytes(b"not a real MP3")
        for name,value in (("DB_PATH",self.root/"db.sqlite3"),("MEDIA_ROOT",self.media)):
            patcher=patch.object(library,name,value)
            patcher.start()
            self.addCleanup(patcher.stop)
        music._read_tags.cache_clear()

    def test_music_library_scan_and_separate_catalog(self):
        created=library.create_library(library.LibraryRequest(
            name="Music",kind="music",path=str(self.musicdir),icon="music"))
        scanned=library.scan_library(created["id"])
        self.assertEqual(scanned["found"],1)
        result=music.music_catalog(library_id=created["id"])
        self.assertEqual(result["total"],1)
        self.assertEqual(result["tracks"][0]["title"],"01 - Example")
        self.assertEqual(result["tracks"][0]["album"],"Album")
        self.assertEqual(catalog(kind="movies")["total"],0)
        self.assertEqual(catalog(kind="tv")["total"],0)
        self.assertFalse(home_shelves()["continue_watching"])

    def test_music_stream_requires_indexed_music_track(self):
        created=library.create_library(library.LibraryRequest(
            name="Music",kind="music",path=str(self.musicdir),icon="music"))
        library.scan_library(created["id"])
        track_id=music.music_catalog()["tracks"][0]["id"]
        response=music.music_stream(track_id)
        self.assertEqual(response.path,str(self.song))
        with self.assertRaises(HTTPException):
            music.music_stream(track_id+1000)

    def test_music_scan_rejects_video_and_video_scan_rejects_music(self):
        (self.musicdir/"Not a music file.mkv").write_bytes(b"video")
        created=library.create_library(library.LibraryRequest(
            name="Music",kind="music",path=str(self.musicdir),icon="music"))
        self.assertEqual(library.scan_library(created["id"])["found"],1)
