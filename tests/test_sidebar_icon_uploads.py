"""Uploaded sidebar icon defaults and per-library storage lifecycle."""
import asyncio
from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from PIL import Image
from starlette.requests import Request

from server import library
from server.sidebar_default_icons import ICONS, default_icon_png

ROOT = Path(__file__).resolve().parents[1]


def request_for(data, content_type="image/png"):
    sent = False
    async def receive():
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": data, "more_body": False}
        return {"type": "http.request", "body": b"", "more_body": False}
    return Request({"type": "http", "method": "PUT",
                    "headers": [(b"content-type", content_type.encode())]}, receive)


def sample_png(size=(120, 80)):
    buffer = BytesIO()
    Image.new("RGBA", size, (30, 170, 220, 180)).save(buffer, "PNG")
    return buffer.getvalue()


class SidebarIconTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name)
        for attr, val in (("DB_PATH", path / "library.sqlite3"),
                          ("ICON_DIRECTORY", path / "icons")):
            p = patch.object(library, attr, val)
            p.start()
            self.addCleanup(p.stop)
        with library.db() as conn:
            conn.execute("INSERT INTO libraries(id,name,kind,path,icon,font) "
                         "VALUES(1,'Movies','movies','/media/movies','film','default')")

    def test_uploaded_defaults_are_valid_distinct_png_images(self):
        self.assertEqual(set(ICONS), {"home", "movies", "tv", "settings"})
        images = [default_icon_png(name) for name in ICONS]
        self.assertEqual(len(set(images)), 4)
        for data in images:
            self.assertTrue(data.startswith(b"\x89PNG\r\n\x1a\n"))
            with Image.open(BytesIO(data)) as image:
                self.assertEqual(image.size, (96, 96))
                self.assertIn(image.mode, ("P", "RGBA"))

    def test_upload_replace_revert_survives_database_reopen(self):
        self.assertIsNone(library.libraries()[0]["icon_image_url"])
        first = asyncio.run(library.upload_library_icon(1, request_for(sample_png())))
        self.assertTrue(first["icon_custom"])
        self.assertIn("/api/libraries/1/icon.png?v=", first["icon_image_url"])
        with Image.open(library.ICON_DIRECTORY / "1.png") as img:
            self.assertEqual(img.size, (256, 256))
            self.assertEqual(img.mode, "RGBA")
        self.assertEqual(library.libraries()[0]["icon_image_url"], first["icon_image_url"])
        newer = asyncio.run(library.upload_library_icon(1, request_for(sample_png((80, 150)))))
        self.assertGreater(newer["icon_version"], first["icon_version"])
        reset = library.revert_library_icon(1)
        self.assertFalse(reset["icon_custom"])
        self.assertIsNone(reset["icon_image_url"])
        self.assertFalse((library.ICON_DIRECTORY / "1.png").exists())

    def test_invalid_and_oversized_uploads_are_rejected(self):
        for data,ctype,code in ((b"garbage", "image/jpeg", 415),
                                (b"not png", "image/png", 415),
                                (b"x" * (library.ICON_MAX_BYTES + 1), "image/png", 413)):
            with self.subTest(code=code), self.assertRaises(HTTPException) as fail:
                asyncio.run(library.upload_library_icon(1, request_for(data,ctype)))
            self.assertEqual(fail.exception.status_code, code)

    def test_missing_library_and_library_deletion_clean_up_icon(self):
        with self.assertRaises(HTTPException) as fail:
            asyncio.run(library.upload_library_icon(99, request_for(sample_png())))
        self.assertEqual(fail.exception.status_code, 404)
        asyncio.run(library.upload_library_icon(1, request_for(sample_png())))
        library.delete_library(1)
        self.assertFalse((library.ICON_DIRECTORY / "1.png").exists())

    def test_settings_and_sidebar_support_uploaded_icons(self):
        page = (ROOT / "server/index.html").read_text()
        shell = (ROOT / "server/shell.js").read_text()
        catalog = (ROOT / "server/catalog.html").read_text()
        for widget in ('icon-upload', 'icon-reset', 'icon-file', 'icon-upload-status'):
            self.assertIn('id="' + widget + '"', page)
        self.assertIn('resetIconControls(lib)', page)
        self.assertIn("stagedIcon", page)
        self.assertIn('library.icon_image_url', shell)
        self.assertIn("sidebar-icon-"+ "home", shell)
        self.assertIn("sidebar_default_icon", (ROOT / "server/main.py").read_text())
        self.assertIn('lib?.icon_image_url', catalog)


if __name__ == "__main__":
    unittest.main()
