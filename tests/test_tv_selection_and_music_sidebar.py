"""Regressions for TV selection colors and unconfigured sidebar destinations."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pydantic import ValidationError

from server import library, sidebar_settings


class TvSelectionColorTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        patcher = patch.object(library, "DB_PATH", Path(temporary.name) / "library.sqlite3")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_crimson_is_valid_default_and_persists(self):
        self.assertEqual(sidebar_settings.get_tv_appearance()["selection_color"], "#A61E1E")
        request = sidebar_settings.TvAppearanceRequest(selection_color="#A61E1E")
        self.assertEqual(sidebar_settings.save_tv_appearance(request),
                         {"selection_color": "#A61E1E"})
        self.assertEqual(sidebar_settings.get_tv_appearance()["selection_color"], "#A61E1E")
        with library.db() as connection:
            row = connection.execute(
                "SELECT value FROM app_settings WHERE key='tv_selection_color'"
            ).fetchone()
        self.assertEqual(row["value"], "#A61E1E")

    def test_switching_from_purple_to_crimson(self):
        for color in ("#8B5CF6", "#A61E1E"):
            response = sidebar_settings.save_tv_appearance(
                sidebar_settings.TvAppearanceRequest(selection_color=color)
            )
            self.assertEqual(response["selection_color"], color)
            self.assertEqual(sidebar_settings.get_tv_appearance()["selection_color"], color)

    def test_invalid_color_is_rejected(self):
        with self.assertRaises(ValidationError):
            sidebar_settings.TvAppearanceRequest(selection_color="#123456")


class SidebarLibraryVisibilityTests(unittest.TestCase):
    def test_server_lists_only_configured_library_types(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(
            library, "DB_PATH", Path(temporary) / "library.sqlite3"
        ):
            no_libraries = sidebar_settings.get_sidebar()
            self.assertNotIn("music", no_libraries["order"])
            with library.db() as connection:
                connection.execute(
                    "INSERT INTO libraries(id,name,kind,path) VALUES(1,'Movies','movies','/media/Movies')"
                )
            movies_only = sidebar_settings.get_sidebar()
            self.assertIn("movies", movies_only["order"])
            self.assertNotIn("music", movies_only["order"])
            self.assertEqual(movies_only["order"][-1], "settings")

    def test_client_removes_unconfigured_navigation_links_before_sorting(self):
        script = (Path(__file__).resolve().parents[1] / "server" / "shell.js").read_text()
        self.assertIn("if(!configured.has(kind)){", script)
        self.assertIn("link.remove();", script)
        self.assertLess(script.index("link.remove();"),
                        script.index("const links=new Map([...nav.querySelectorAll"))


if __name__ == "__main__":
    unittest.main()
