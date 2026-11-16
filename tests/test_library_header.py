"""Library masthead defaults, custom PNG uploads, and appearance settings."""
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
from server.library_header_art import default_png

SERVER = Path(__file__).resolve().parents[1] / "server"


def png_bytes(transparent=True):
    output = BytesIO()
    color = (245, 245, 245, 60) if transparent else (245, 245, 245, 255)
    Image.new("RGBA", (300, 150), color).save(output, "PNG")
    return output.getvalue()


def png_request(data, content_type="image/png"):
    sent = False
    async def receive():
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": data, "more_body": False}
        return {"type": "http.request", "body": b"", "more_body": False}
    return Request({"type": "http", "method": "PUT",
                    "headers": [(b"content-type", content_type.encode())]}, receive)


class LibraryHeaderTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name)
        for attr, value in (("DB_PATH", path / "db.sqlite3"),
                            ("HEADER_DIRECTORY", path / "library-headers")):
            p = patch.object(library, attr, value)
            p.start()
            self.addCleanup(p.stop)
        with library.db() as conn:
            conn.execute("INSERT INTO libraries(id,name,kind,path,icon,font) "
                         "VALUES(1,'Movies','movies','/media/movies','film','default')")
            conn.execute("INSERT INTO libraries(id,name,kind,path,icon,font) "
                         "VALUES(2,'TV Shows','tv','/media/tv','tv','default')")

    def test_built_in_movies_and_tv_art_are_transparent_different_pngs(self):
        defaults = []
        for kind in ("movies", "tv"):
            data = default_png(kind)
            self.assertTrue(data.startswith(b"\x89PNG\r\n\x1a\n"))
            with Image.open(BytesIO(data)) as im:
                self.assertEqual(im.size, (900, 360))
                self.assertEqual(im.mode, "RGBA")
                self.assertLess(im.getchannel("A").getextrema()[0], 255)
                self.assertGreater(im.getchannel("A").getextrema()[1], 0)
            defaults.append(data)
        self.assertNotEqual(defaults[0], defaults[1])

    def test_view_returns_default_artwork_and_custom_font(self):
        movies, tv = library.libraries()
        self.assertEqual(movies["header_image_url"], "/assets/library-header-movies.png")
        self.assertEqual(tv["header_image_url"], "/assets/library-header-tv.png")
        self.assertFalse(movies["header_custom"])
        result = library.update_library(1, library.LibraryEdit(
            name="Movies", icon="reel", font="script",
            header_x=82, header_y=31, header_scale=125, header_opacity=38,
        ))
        self.assertEqual(result["font"], "script")
        self.assertEqual(result["icon"], "reel")
        self.assertEqual([result[key] for key in
                          ("header_x", "header_y", "header_scale", "header_opacity")],
                         [82, 31, 125, 38])
        self.assertEqual(library.libraries()[0]["header_scale"], 125)

    def test_upload_replace_revert_and_remount_persist(self):
        result = asyncio.run(library.upload_library_header(1, png_request(png_bytes())))
        self.assertTrue(result["header_custom"])
        self.assertIn("/api/libraries/1/header.png?v=", result["header_image_url"])
        with Image.open(library.HEADER_DIRECTORY / "1.png") as im:
            self.assertEqual(im.size, (300, 150))
        saved = library.libraries()[0]
        self.assertEqual(saved["header_image_url"], result["header_image_url"])
        second = asyncio.run(library.upload_library_header(1, png_request(png_bytes())))
        self.assertGreater(second["header_version"], result["header_version"])
        reverted = library.revert_library_header(1)
        self.assertFalse(reverted["header_custom"])
        self.assertEqual(reverted["header_image_url"], "/assets/library-header-movies.png")
        self.assertFalse((library.HEADER_DIRECTORY / "1.png").exists())

    def test_reject_non_png_nontransparent_and_oversized_upload(self):
        with self.assertRaises(HTTPException) as ctype:
            asyncio.run(library.upload_library_header(1, png_request(b"abc", "image/jpeg")))
        self.assertEqual(ctype.exception.status_code, 415)
        with self.assertRaises(HTTPException) as alpha:
            asyncio.run(library.upload_library_header(1, png_request(png_bytes(False))))
        self.assertEqual(alpha.exception.status_code, 422)
        with self.assertRaises(HTTPException) as too_large:
            asyncio.run(library.upload_library_header(
                1, png_request(b"\x89PNG\r\n\x1a\n" + b"X" * (5 * 1024 * 1024))))
        self.assertEqual(too_large.exception.status_code, 413)

    def test_missing_library_upload_does_not_create_image(self):
        with self.assertRaises(HTTPException) as missing:
            asyncio.run(library.upload_library_header(500, png_request(png_bytes())))
        self.assertEqual(missing.exception.status_code, 404)
        self.assertFalse(library.HEADER_DIRECTORY.exists())

    def test_settings_and_catalog_pages_show_live_preview(self):
        editor = (SERVER / "index.html").read_text()
        catalog = (SERVER / "catalog.html").read_text()
        main = (SERVER / "main.py").read_text()
        for ident in ("art-preview", "art-preview-image", "art-file", "art-default",
                      "art-x", "art-y", "art-scale", "art-opacity"):
            self.assertIn('id="' + ident + '"', editor)
        self.assertIn("resetHeaderControls(lib)", editor)
        self.assertIn("method:'PUT',headers:{'Content-Type':'image/png'}", editor)
        self.assertIn("method:'DELETE'", editor)
        self.assertIn("id=\"library-header-art\"", catalog)
        self.assertIn("id=\"library-title-icon\"", catalog)
        self.assertIn("title.className='library-font--'", catalog)
        self.assertIn("art.src=lib?.header_image_url", catalog)
        self.assertIn("/assets/library-header-{kind}.png", main)


if __name__ == "__main__":
    unittest.main()
