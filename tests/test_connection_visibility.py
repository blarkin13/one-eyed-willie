"""Connections visibility is presentation only; hiding does not disconnect."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pydantic import ValidationError
from server import library, sidebar_settings


class ConnectionVisibilityTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        p = patch.object(library, "DB_PATH", Path(folder.name) / "library.sqlite")
        p.start()
        self.addCleanup(p.stop)

    def test_defaults_all_visible_and_persisted_independently(self):
        visible = sidebar_settings.get_connection_visibility()["visible"]
        self.assertEqual(set(visible), set(sidebar_settings.CONNECTION_SERVICE_IDS))
        self.assertTrue(all(visible.values()))

        saved = sidebar_settings.save_connection_visibility(
            sidebar_settings.ConnectionVisibilityRequest(service="opensubtitles", visible=False))
        self.assertFalse(saved["visible"]["opensubtitles"])
        self.assertTrue(saved["visible"]["plex"])

        # Simulate a fresh request from a separate TV/browser session.
        fresh = sidebar_settings.get_connection_visibility()["visible"]
        self.assertFalse(fresh["opensubtitles"])
        with library.db() as conn:
            row = conn.execute(
                "SELECT value FROM app_settings WHERE key='connections_hub_hidden'"
            ).fetchone()
        self.assertEqual(row["value"], '["opensubtitles"]')

        restored = sidebar_settings.save_connection_visibility(
            sidebar_settings.ConnectionVisibilityRequest(service="opensubtitles", visible=True))
        self.assertTrue(restored["visible"]["opensubtitles"])

    def test_visibility_does_not_touch_connection_config(self):
        sidebar_settings.save_connection_visibility(
            sidebar_settings.ConnectionVisibilityRequest(service="plex", visible=False))
        with library.db() as conn:
            rows = conn.execute("SELECT key FROM app_settings").fetchall()
        self.assertEqual([row["key"] for row in rows], ["connections_hub_hidden"])

    def test_reject_unlisted_service(self):
        with self.assertRaises(ValidationError):
            sidebar_settings.ConnectionVisibilityRequest(service="not-a-service", visible=False)


class ConnectionUiTests(unittest.TestCase):
    def test_every_service_has_switch_and_card_focus_uses_saved_color(self):
        root = Path(__file__).resolve().parents[1]
        form = (root / "server/arr_connections.html").read_text()
        hub = (root / "server/connections_hub.html").read_text()
        css = (root / "server/ui.css").read_text()
        self.assertIn("visibilityControls.set(serviceId,{input,feedback})", form)
        self.assertIn("'/api/settings/connections/visibility'", form)
        self.assertIn("visibility.visible?.[service.id]===false", hub)
        self.assertIn("service.dashboard?'a':'button'", hub)
        self.assertNotIn("#a78bfa", hub)
        self.assertNotIn("#b59aff", form)
        self.assertIn("var(--oew-tv-select-color,#A61E1E)", hub)
        self.assertIn("appearance:none!important", css)
        self.assertIn("background-image:url(\"data:image/svg+xml,", css)
        self.assertIn("select:not([multiple]):is(:focus,:focus-visible)", css)

    def test_plex_clone_is_preview_first_and_confirmation_required(self):
        root = Path(__file__).resolve().parents[1]
        hub = (root / "server/connections_hub.html").read_text()
        form = (root / "server/arr_connections.html").read_text()
        self.assertIn("id=\"connection-plex-clone\"", hub)
        self.assertIn("status('/api/plex/import/preview')", hub)
        self.assertIn("statusPost('/api/plex/import',{confirm:true})", hub)
        self.assertIn("Confirm clone to Yarr Media", form)
        self.assertIn("id=\"plex-import\" hidden", form)


if __name__ == "__main__":
    unittest.main()
