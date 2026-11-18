"""Configured-only library routes/sidebar and private Lidarr integration."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from server import library, sidebar_settings, lidarr, main

class ConfiguredLibrariesTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        media=self.root/"media"
        media.mkdir()
        for obj,name,value in ((library,"DB_PATH",self.root/"library.sqlite3"),
                               (library,"MEDIA_ROOT",media)):
            p=patch.object(obj,name,value);p.start();self.addCleanup(p.stop)
        self.media=media

    def test_no_unconfigured_sidebar_destinations_or_browse_pages(self):
        with library.db() as conn:
            available={entry["id"] for entry in sidebar_settings._available(conn)}
        self.assertNotIn("movies", available)
        self.assertNotIn("tv", available)
        self.assertNotIn("music", available)
        self.assertIn("settings", available)
        for page in (main.movies_page,main.tv_page,main.music_page):
            with self.assertRaises(HTTPException) as captured:
                page(library_id=None)
            self.assertEqual(captured.exception.status_code,404)

    def test_only_configured_kind_is_linked(self):
        folder=self.media/"Albums"
        folder.mkdir()
        created=library.create_library(library.LibraryRequest(
            name="Music",kind="music",path=str(folder),icon="music"
        ))
        with library.db() as conn:
            available={entry["id"] for entry in sidebar_settings._available(conn)}
        self.assertIn("music",available)
        self.assertNotIn("movies",available)
        self.assertNotIn("tv",available)
        self.assertEqual(main.music_page(library_id=created["id"]).media_type,"text/html")
        with self.assertRaises(HTTPException):
            main.movies_page(library_id=None)
        with self.assertRaises(HTTPException):
            main.music_page(library_id=created["id"]+1)

class LidarrConnectionTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        p=patch.object(lidarr,"SETTINGS_FILE",self.root/"lidarr.json")
        p.start();self.addCleanup(p.stop)
        # Env-managed connections cannot be overwritten or disconnected.
        for var in ("LIDARR_URL","LIDARR_API_KEY"):
            p=patch.dict("os.environ",{var:""})
            p.start();self.addCleanup(p.stop)

    def test_connect_does_not_return_api_key_and_disconnect_removes_file(self):
        with patch.object(lidarr,"_probe") as probe:
            result=lidarr.connect(lidarr.LidarrInput(
                url="http://192.168.86.29:8686",
                api_key="test-key-that-is-long-enough"
            ))
        probe.assert_called_once()
        self.assertTrue(result["connected"])
        self.assertNotIn("api_key",result)
        status=lidarr.connection_status()
        self.assertTrue(status["connected"])
        self.assertEqual(status["address"],"http://192.168.86.29:8686")
        self.assertNotIn("api_key",status)
        lidarr.disconnect()
        self.assertFalse(lidarr.connection_status()["connected"])

    def test_rejects_public_host_and_invalid_credentials(self):
        for url in ("https://example.com:8686","http://127.0.0.1:8686",
                    "http://192.168.86.29:8686/path"):
            with self.assertRaises(HTTPException):
                lidarr._base_url(url)
        with patch.object(lidarr,"_probe",side_effect=HTTPException(422,"Bad API key")):
            with self.assertRaises(HTTPException):
                lidarr.connect(lidarr.LidarrInput(
                    url="http://192.168.86.29:8686",
                    api_key="bad-key-but-long-enough"
                ))
        self.assertFalse(lidarr.connection_status()["connected"])
