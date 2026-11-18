"""Pages and scripts are served gzipped, validated by ETag, and never stale."""
import asyncio
import gzip
import tempfile
import unittest
from pathlib import Path

from server.static_text import TextFileResponse


def fetch(response, headers=None, method="GET"):
    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": method,
             "scheme": "http", "path": "/x", "raw_path": b"/x", "query_string": b"",
             "root_path": "", "client": ("127.0.0.1", 1), "server": ("testserver", 80),
             "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]}
    sent = []

    async def run():
        done, first = asyncio.Event(), []

        async def receive():
            if not first:
                first.append(1)
                return {"type": "http.request", "body": b"", "more_body": False}
            await done.wait()
            return {"type": "http.disconnect"}

        async def send(message):
            sent.append(message)
        await response(scope, receive, send)
        done.set()

    asyncio.run(run())
    start = next(m for m in sent if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    return start["status"], {k.decode().lower(): v.decode() for k, v in start["headers"]}, body


class TextFileResponseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "page.js"
        self.text = ("const answer = 42; // " + "x" * 30 + "\n") * 400
        self.path.write_text(self.text)

    def get(self, request_headers=None, **kwargs):
        return fetch(TextFileResponse(self.path, media_type="text/javascript", **kwargs),
                     request_headers)

    def test_gzip_when_the_browser_accepts_it(self):
        status, headers, body = self.get({"Accept-Encoding": "gzip, deflate, br"})
        self.assertEqual(status, 200)
        self.assertEqual(headers["content-encoding"], "gzip")
        self.assertLess(len(body), len(self.text) / 4)
        self.assertEqual(gzip.decompress(body).decode(), self.text)
        self.assertIn("Accept-Encoding", headers["vary"])
        self.assertEqual(headers["content-type"].split(";")[0], "text/javascript")

    def test_plain_when_gzip_is_refused_or_not_offered(self):
        for accept in ({}, {"Accept-Encoding": "identity"}, {"Accept-Encoding": "gzip;q=0"}):
            status, headers, body = self.get(accept)
            self.assertEqual(status, 200)
            self.assertNotIn("content-encoding", headers)
            self.assertEqual(body.decode(), self.text)

    def test_unchanged_file_answers_304_without_a_body(self):
        _, headers, _ = self.get({"Accept-Encoding": "gzip"})
        etag = headers["etag"]
        status, again, body = self.get({"Accept-Encoding": "gzip", "If-None-Match": etag})
        self.assertEqual((status, body), (304, b""))
        self.assertEqual(again["etag"], etag)
        self.assertEqual(again["cache-control"], "no-cache")
        for validator in (f"W/{etag}", f'"nope", {etag}', "*"):
            self.assertEqual(self.get({"If-None-Match": validator})[0], 304, validator)

    def test_an_edited_file_is_never_served_stale(self):
        _, headers, _ = self.get()
        old = headers["etag"]
        self.path.write_text("const answer = 43;\n" * 200)
        status, fresh, body = self.get({"If-None-Match": old, "Accept-Encoding": "gzip"})
        self.assertEqual(status, 200)
        self.assertNotEqual(fresh["etag"], old)
        self.assertEqual(gzip.decompress(body).decode(), "const answer = 43;\n" * 200)

    def test_same_size_edit_is_noticed(self):
        _, headers, _ = self.get()
        old = headers["etag"]
        self.path.write_text(self.text.replace("42", "43"))  # identical length
        import os
        stat = self.path.stat()
        os.utime(self.path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 5_000_000))
        status, fresh, body = self.get({"If-None-Match": old})
        self.assertEqual(status, 200)
        self.assertIn("43", body.decode())

    def test_small_files_are_not_compressed(self):
        self.path.write_text("tiny")
        status, headers, body = self.get({"Accept-Encoding": "gzip"})
        self.assertEqual((status, body), (200, b"tiny"))
        self.assertNotIn("content-encoding", headers)

    def test_callers_own_headers_win_and_vary_merges(self):
        _, headers, _ = self.get({"Accept-Encoding": "gzip"}, headers={
            "Cache-Control": "public, max-age=31536000, immutable", "Vary": "User-Agent"})
        self.assertEqual(headers["cache-control"], "public, max-age=31536000, immutable")
        self.assertEqual(sorted(v.strip() for v in headers["vary"].split(",")),
                         ["Accept-Encoding", "User-Agent"])

    def test_missing_file_is_a_normal_error_not_a_crash(self):
        gone = TextFileResponse(Path(self.tmp.name) / "gone.js", media_type="text/javascript")
        with self.assertRaises(RuntimeError):
            fetch(gone)


class RealRoutesTests(unittest.TestCase):
    def test_site_scripts_and_pages_use_validators_instead_of_no_store(self):
        from server.main import app
        for path in ("/assets/shell.js", "/assets/player.js", "/assets/ui.css",
                     "/assets/ambient.js", "/assets/media-context.js"):
            status, headers, body = fetch_app(app, path, {"Accept-Encoding": "gzip"})
            self.assertEqual(status, 200, path)
            self.assertEqual(headers["content-encoding"], "gzip", path)
            self.assertEqual(headers["cache-control"], "no-cache", path)
            self.assertTrue(headers["etag"].startswith('"'), path)
            source = Path(__file__).resolve().parents[1] / "server" / {
                "/assets/shell.js": "shell.js", "/assets/player.js": "player.js",
                "/assets/ui.css": "ui.css", "/assets/ambient.js": "ambient.js",
                "/assets/media-context.js": "media_context.js"}[path]
            self.assertEqual(gzip.decompress(body), source.read_bytes(), path)
            self.assertEqual(fetch_app(app, path, {"If-None-Match": headers["etag"]})[0], 304, path)

    def test_the_tv_stylesheet_is_still_built_per_request(self):
        from server.main import app
        status, headers, body = fetch_app(app, "/assets/ui.css",
                                          {"User-Agent": "OneEyedWillieTV/1"})
        self.assertEqual(status, 200)
        self.assertEqual(headers["cache-control"], "no-store")


def fetch_app(app, path, headers=None):
    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "GET",
             "scheme": "http", "path": path, "raw_path": path.encode(), "query_string": b"",
             "root_path": "", "client": ("127.0.0.1", 1), "server": ("testserver", 80),
             "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]}
    sent = []

    async def run():
        done, first = asyncio.Event(), []

        async def receive():
            if not first:
                first.append(1)
                return {"type": "http.request", "body": b"", "more_body": False}
            await done.wait()
            return {"type": "http.disconnect"}

        async def send(message):
            sent.append(message)
        await app(scope, receive, send)
        done.set()

    asyncio.run(run())
    start = next(m for m in sent if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    return start["status"], {k.decode().lower(): v.decode() for k, v in start["headers"]}, body


if __name__ == "__main__":
    unittest.main()
