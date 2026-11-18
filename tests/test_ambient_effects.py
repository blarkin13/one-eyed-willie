"""Ambient effects are opt-in and persisted across connections."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pydantic import ValidationError
from server import library
from server.ambient_settings import AmbientPreferences, get_ambient, save_ambient


class AmbientSettingsTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        patcher=patch.object(library,"DB_PATH",Path(temp.name)/"ambient.sqlite3")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_default_off_and_low_intensity(self):
        self.assertEqual(get_ambient(),{"effect":"off","intensity":10,
                                        "speed":"normal","layer":"foreground"})

    def test_all_effects_save_and_reload(self):
        for name in ("snow","rain","leaves","fireflies","off"):
            setting=AmbientPreferences(effect=name,intensity=65,speed="slow",
                                       layer="background")
            saved=save_ambient(setting)
            self.assertEqual(saved,get_ambient())
        with library.db() as conn:
            stored=conn.execute("SELECT value FROM app_settings "
                                "WHERE key='ambient_effect'").fetchone()[0]
        self.assertEqual(stored,"off")

    def test_rejects_bad_mode_and_intensity(self):
        for bad in ({"effect":"fireworks"},{"effect":"snow","intensity":101},
                    {"effect":"rain","intensity":0},{"speed":"extreme"},
                    {"layer":"over-player"}):
            with self.assertRaises(ValidationError):
                AmbientPreferences(**bad)

    def test_invalid_legacy_setting_falls_back_to_off(self):
        with library.db() as conn:
            conn.execute("CREATE TABLE app_settings(key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            conn.execute("INSERT INTO app_settings VALUES('ambient_effect','broken')")
        self.assertEqual(get_ambient()["effect"],"off")

    def test_saved_setting_survives_separate_get_requests(self):
        save_ambient(AmbientPreferences(effect="rain", intensity=85,
                                        speed="fast", layer="foreground"))
        self.assertEqual(get_ambient()["effect"], "rain")
        self.assertEqual(get_ambient()["intensity"], 85)

    def test_choice_changes_autosave_on_web_and_tv(self):
        root=Path(__file__).resolve().parents[1]/"server"
        web=(root/"appearance_settings.html").read_text()
        tv=(root/"tv_settings.html").read_text()
        ambient=(root/"ambient.js").read_text()
        self.assertIn("control.addEventListener('change',saveAmbient)", web)
        self.assertIn("saveAmbientOnTv();", tv)
        self.assertIn("tv-ambient-intensity').onchange=saveAmbientOnTv", tv)
        self.assertIn("sessionStorage.setItem(cacheKey", ambient)
        self.assertIn("canvas.style.display=show?'block':'none'", ambient)
        self.assertIn("settings.layer==='background'?'35':'700'", ambient)

    def test_static_script_in_every_browsing_page(self):
        root=Path(__file__).resolve().parents[1]/"server"
        for name in ("dashboard.html","catalog.html","movie_detail.html",
                     "tv_detail.html","explore.html","person.html",
                     "credit_detail.html","appearance_settings.html","tv_settings.html"):
            self.assertIn('/assets/ambient.js', (root/name).read_text(), name)
        js=(root/"ambient.js").read_text()
        for marker in ("prefers-reduced-motion", "document.hidden",
                       ".willie-player", "pointer-events:none", "cancelAnimationFrame"):
            self.assertIn(marker,js)


if __name__=="__main__":
    unittest.main()
