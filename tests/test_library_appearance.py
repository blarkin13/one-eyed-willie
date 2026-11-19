"""Regressions for library icon gallery, font previews and saved sidebar style."""
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree

from fastapi import HTTPException
from server import library
from server.main import library_appearance_js

SERVER = Path(__file__).resolve().parents[1] / "server"


def definitions():
    source = (SERVER / "library_appearance.js").read_text()
    icon_block = source.split("const icons={", 1)[1].split("};\nconst fonts=", 1)[0]
    font_block = source.split("const fonts={", 1)[1].split("};\nfunction createIcon", 1)[0]
    icons = re.findall(r"^\s*([a-z][a-z0-9_]*):\['([^']+)','([^']+)','([^']*)'\],?$",
                       icon_block, flags=re.MULTILINE)
    fonts = re.findall(r"^\s*([a-z][a-z0-9_]*):\['([^']+)','([^']+)'\],?$",
                       font_block, flags=re.MULTILINE)
    return icons, fonts


class LibraryAppearanceTests(unittest.TestCase):
    def test_all_icons_are_real_valid_svg_paths_and_api_values(self):
        icons, _ = definitions()
        keys = [key for key, _, _, _ in icons]
        self.assertGreaterEqual(len(keys), 50)
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(set(keys), set(library.LIBRARY_ICONS))
        self.assertTrue({"film", "tv", "folder", "ghost", "skull", "ship",
                         "popcorn", "rocket", "trophy", "snowflake"}.issubset(keys))
        for key, label, group, shape in icons:
            with self.subTest(icon=key):
                self.assertIn(group, {"Media", "Genres", "Collections", "Themes"})
                self.assertTrue(label)
                svg = ElementTree.fromstring("<svg>" + shape + "</svg>")
                self.assertTrue(list(svg))
                library._validate_style(key, "default")

    def test_font_options_match_backend_and_have_a_real_css_preview(self):
        _, fonts = definitions()
        css = (SERVER / "ui.css").read_text()
        keys = [key for key, _, _ in fonts]
        self.assertGreaterEqual(len(keys), 10)
        self.assertEqual(set(keys), set(library.LIBRARY_FONTS))
        for font, label, description in fonts:
            with self.subTest(font=font):
                self.assertTrue(label and description)
                self.assertIn(".library-font--" + font + "{--lib-font:", css)
                library._validate_style("film", font)
        self.assertIn('.library-font-card[class*="library-font--"] .font-sample', css)
        self.assertIn('.sidebar .nav-link[class*="library-font--"] .nav-text', css)

    def test_icon_and_font_gallery_initialize_on_add_and_edit(self):
        page = (SERVER / "index.html").read_text()
        nav = (SERVER / "shell.js").read_text()
        self.assertIn('/assets/library-appearance.js', page)
        self.assertIn('id="library-icon-search"', page)
        self.assertIn('id="library-icon-grid"', page)
        self.assertIn('id="library-font-grid"', page)
        self.assertIn('id="library-preview-icon"', page)
        self.assertIn('id="library-preview-name"', page)
        self.assertIn('renderIcons()', page)
        self.assertIn('renderFonts()', page)
        self.assertEqual(page.count("iconCategory='All';refreshAppearance()"), 2)
        self.assertIn("sidebarPreviewIcon(35)", page)
        # The gallery follows the chosen icon theme (pirate icons or the black-glass set).
        self.assertIn("appearance.createThemeIcon(id,28)", page)
        self.assertIn("appearance.createIcon(library.icon,28)", nav)
        self.assertIn("if(library.sidebar_hidden)link.classList.add('sidebar-hidden')", nav)
        self.assertNotIn("For standard Movies and TV Shows libraries", page)
        self.assertIn('aria-pressed', page)

    def test_saved_style_and_visibility_persist(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        config = patch.object(library, "DB_PATH", Path(folder.name) / "db.sqlite3")
        config.start()
        self.addCleanup(config.stop)
        with library.db() as conn:
            conn.execute(
                "INSERT INTO libraries(id,name,kind,path,icon,font) "
                "VALUES (1,'Movies','movies','/media/Movies','film','default')"
            )
        changed = library.update_library(
            1, library.LibraryEdit(
                name="Movies", icon="ship", font="cinematic", sidebar_hidden=True
            )
        )
        self.assertEqual(changed["icon"], "ship")
        self.assertEqual(changed["font"], "cinematic")
        self.assertTrue(changed["sidebar_hidden"])
        with library.db() as conn:
            row = conn.execute("SELECT icon,font,sidebar_hidden FROM libraries WHERE id=1").fetchone()
        self.assertEqual(tuple(row), ("ship", "cinematic", 1))
        with self.assertRaises(HTTPException):
            library._validate_style("script>alert(1)", "modern")

    def test_asset_is_served_from_local_application(self):
        response = library_appearance_js()
        self.assertEqual(Path(response.path), SERVER / "library_appearance.js")
        self.assertTrue((SERVER / "library_appearance.js").is_file())
        self.assertIn("application/javascript", response.media_type)


if __name__ == "__main__":
    unittest.main()
