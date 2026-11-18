"""Action / Adventure is an optional complete six-destination icon theme."""
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from fastapi import HTTPException
from server.main import action_adventure_theme_icon

ROOT = Path(__file__).resolve().parents[1] / "server"
NAMES = ("home", "movies", "tv-shows", "music", "connections", "settings")


class AdventureIconThemeTests(unittest.TestCase):
    def test_all_six_icons_are_local_transparent_vector_assets(self):
        for name in NAMES:
            with self.subTest(name=name):
                path = ROOT / "theme_icons" / "action-adventure" / (name + ".svg")
                self.assertTrue(path.is_file())
                root = ET.parse(path).getroot()
                self.assertEqual(root.attrib.get("viewBox"), "0 0 512 512")
                self.assertTrue(any(tag.tag.endswith("path") for tag in root.iter()))
                self.assertFalse(any(tag.tag.endswith("image") for tag in root.iter()))
                response = action_adventure_theme_icon(name)
                self.assertEqual(response.media_type, "image/svg+xml")

    def test_route_rejects_unknown_or_unsafe_names(self):
        for name in ("unknown", "../secrets", "..", "music.png"):
            with self.subTest(name=name), self.assertRaises(HTTPException) as raised:
                action_adventure_theme_icon(name)
            self.assertEqual(raised.exception.status_code, 404)

    def test_theme_selector_remains_optional_with_clean_default(self):
        settings = (ROOT / "appearance_settings.html").read_text()
        shell = (ROOT / "shell.js").read_text()
        library = (ROOT / "library_appearance.js").read_text()
        self.assertIn('<option value="clean">Clean (default)</option>', settings)
        self.assertIn('<option value="pirate">Pirate (original icons)</option>', settings)
        self.assertIn('<option value="adventure">Action / Adventure</option>', settings)
        self.assertIn("WillieActionIcons.create(safe,26)", shell)
        self.assertIn("value==='pirate'||value==='adventure'", library)
        # Direct SVG images work when a browser does not support CSS masking.
        self.assertIn("image.src='/assets/themes/action-adventure/'+asset+'.svg?v=2'", shell)
        self.assertIn("image.addEventListener('error'", shell)
        self.assertIn("image.src='/assets/themes/action-adventure/'+asset+'.svg?v=2'", library)
        self.assertNotIn("glyph.style.setProperty('--adventure-icon'", shell)
        self.assertNotIn("glyph.style.setProperty('--adventure-icon'", library)

if __name__ == "__main__":
    unittest.main()
