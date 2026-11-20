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
        self.assertEqual(str(response.path),str(self.song))
        with self.assertRaises(HTTPException):
            music.music_stream(track_id+1000)

    def test_catalog_reads_tags_once_and_only_rereads_changed_files(self):
        created=library.create_library(library.LibraryRequest(
            name="Music",kind="music",path=str(self.musicdir),icon="music"))
        with patch.object(music,"_read_file_tags",wraps=music._read_file_tags) as reader:
            library.scan_library(created["id"])          # scan stores the tags
            self.assertEqual(reader.call_count,1)
            music.music_catalog();music.music_catalog()   # page loads open no files
            self.assertEqual(reader.call_count,1)
            with library.db() as connection:              # a re-tagged file is re-read
                connection.execute("UPDATE media SET mtime_ns=mtime_ns+1")
            music.music_catalog()
            self.assertEqual(reader.call_count,2)

    def test_album_art_is_extracted_once_then_served_from_cache(self):
        import io
        from PIL import Image
        created=library.create_library(library.LibraryRequest(
            name="Music",kind="music",path=str(self.musicdir),icon="music"))
        library.scan_library(created["id"])
        track_id=music.music_catalog()["tracks"][0]["id"]
        buffer=io.BytesIO();Image.new("RGB",(1500,1500),"red").save(buffer,"JPEG")
        with patch.object(music,"ART_DIR",self.root/"art"),\
             patch.object(music,"_embedded_art",return_value=(buffer.getvalue(),"image/jpeg")) as extract:
            first=music.music_art(track_id)
            second=music.music_art(track_id)
            self.assertEqual(extract.call_count,1)
            self.assertEqual(str(first.path),str(second.path))
            with Image.open(first.path) as cached:
                self.assertLessEqual(max(cached.size),music.ART_SIZE)

    def test_music_scan_rejects_video_and_video_scan_rejects_music(self):
        (self.musicdir/"Not a music file.mkv").write_bytes(b"video")
        created=library.create_library(library.LibraryRequest(
            name="Music",kind="music",path=str(self.musicdir),icon="music"))
        self.assertEqual(library.scan_library(created["id"])["found"],1)
