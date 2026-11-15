"""Static regressions for the content-first One-Eyed Willie layout."""
import shutil
import subprocess
import unittest
from html.parser import HTMLParser
from pathlib import Path

SERVER = Path(__file__).resolve().parents[1] / "server"


class Scripts(HTMLParser):
    def __init__(self):
        super().__init__()
        self.inside = False
        self.scripts = []
    def handle_starttag(self, tag, attrs):
        if tag == "script" and not dict(attrs).get("src"):
            self.inside = True
            self.scripts.append("")
    def handle_endtag(self, tag):
        if tag == "script":
            self.inside = False
    def handle_data(self, data):
        if self.inside:
            self.scripts[-1] += data


class CompactLayoutTests(unittest.TestCase):
    def test_home_has_only_media_shelves_not_hero(self):
        page = (SERVER / "dashboard.html").read_text()
        for heading in ("Continue Watching", "Recently Added Movies",
                        "Recently Added TV Shows"):
            self.assertIn(heading, page)
        self.assertNotIn("Your movies and shows, all in one place", page)
        self.assertNotIn('id="movie-count"', page)
        self.assertNotIn('id="show-count"', page)
        self.assertNotIn('class="page-head"', page)
        self.assertIn('class="sr-only">Home', page)

    def test_totals_in_libraries_settings(self):
        page = (SERVER / "index.html").read_text()
        self.assertIn('id="overview-movies"', page)
        self.assertIn('id="overview-tv"', page)
        self.assertIn("loadOverview()", page)

    def test_uploaded_logo_and_favicon_are_served(self):
        for filename in ("logo.png", "favicon.png"):
            file = SERVER / filename
            self.assertTrue(file.is_file())
            self.assertEqual(file.read_bytes()[:8], bytes([137,80,78,71,13,10,26,10]))
            self.assertIn("/assets/" + filename, (SERVER / "shell.js").read_text())
            self.assertIn("/assets/" + filename, (SERVER / "main.py").read_text())

    def test_there_is_no_top_header_or_magnifier(self):
        for page in ("dashboard.html", "catalog.html", "index.html",
                     "remote_settings.html", "metadata_settings.html",
                     "arr_connections.html", "explore.html", "tv_detail.html"):
            text = (SERVER / page).read_text()
            self.assertNotIn('class="topbar"', text, page)
            self.assertNotIn('id="breadcrumbs"', text, page)
        shell = (SERVER / "shell.js").read_text()
        self.assertNotIn("fa-magnifying-glass", shell)
        self.assertNotIn("topbar-actions", shell)
        self.assertNotIn("topbar-action", shell)
        self.assertIn(".topbar,.app-topbar{display:none!important}",
                      (SERVER / "ui.css").read_text())

    def test_icon_nav_has_all_required_links_and_labels(self):
        js = (SERVER / "shell.js").read_text()
        for path in ("/movies", "/tv", "/explore", "/settings/libraries"):
            self.assertIn(path, js)
        for name in ("fa-house", "fa-film", "fa-tv", "fa-compass", "fa-gear"):
            self.assertIn(name, js)
        self.assertIn("aria-label", js)
        self.assertIn("fa-fallback", js)
        css = (SERVER / "ui.css").read_text()
        self.assertIn("@media(max-width:700px)", css)
        self.assertIn("safe-area-inset-bottom", css)

    @unittest.skipUnless(shutil.which("node"), "Node.js not installed")
    def test_ui_javascript_syntax(self):
        source_files = [SERVER / "shell.js"]
        for path in (SERVER / "dashboard.html", SERVER / "catalog.html", SERVER / "index.html"):
            parser = Scripts()
            parser.feed(path.read_text())
            for script in parser.scripts:
                result = subprocess.run(
                    ["node", "--check"], input=script, text=True,
                    capture_output=True, timeout=10
                )
                self.assertEqual(result.returncode, 0, f"{path.name}: {result.stderr}")
        for path in source_files:
            result = subprocess.run(["node", "--check", str(path)],
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, f"{path.name}: {result.stderr}")


if __name__ == "__main__":
    unittest.main()
