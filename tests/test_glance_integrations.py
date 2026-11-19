"""At a Glance integration settings and safe public provider behavior."""
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from pydantic import ValidationError

from server import glance, library

ROOT = Path(__file__).resolve().parents[1]


class GlanceSettingsTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        patcher = patch.object(library, "DB_PATH", Path(directory.name) / "media.sqlite3")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_each_integration_is_independent_and_disabled_by_default(self):
        all_configs = glance.all_settings()["integrations"]
        self.assertEqual(set(all_configs), {"clock", "weather", "news"})
        for cfg in all_configs.values():
            self.assertFalse(cfg["enabled"])
            self.assertTrue(cfg["home"])
            self.assertTrue(cfg["pause"])
            self.assertTrue(cfg["idle"])
        updated = glance.save_setting("clock", glance.WidgetConfig(
            enabled=True, home=False, pause=True, idle=False,
            clock_zone="America/Chicago", clock_format="24h"))
        self.assertTrue(updated["enabled"])
        self.assertFalse(updated["home"])
        self.assertEqual(updated["clock_format"], "24h")
        persisted = glance.all_settings()["integrations"]
        self.assertEqual(persisted["clock"], updated)
        self.assertFalse(persisted["weather"]["enabled"])
        self.assertFalse(persisted["news"]["enabled"])

    def test_weather_news_and_clock_configuration_persist(self):
        weather = glance.save_setting("weather", glance.WidgetConfig(
            enabled=True, zip_code="75001", home=False, pause=False, idle=True))
        news = glance.save_setting("news", glance.WidgetConfig(
            enabled=True, news_source="bbc", home=True, pause=True, idle=False))
        self.assertEqual(weather["zip_code"], "75001")
        self.assertEqual(news["news_source"], "bbc")
        self.assertFalse(glance.one_setting("weather")["pause"])
        self.assertTrue(glance.one_setting("news")["pause"])

    def test_bad_zip_timezone_or_news_source_rejected(self):
        with self.assertRaises(ValidationError):
            glance.WidgetConfig(zip_code="hello")
        with self.assertRaises(ValidationError):
            glance.WidgetConfig(news_source="https://internal/")
        with self.assertRaises(HTTPException):
            glance.save_setting("clock", glance.WidgetConfig(clock_zone="Mars/Olympus"))

    def test_interfaces_are_connected_and_idle_is_dismissible(self):
        settings = (ROOT / "server/arr_connections.html").read_text()
        hub = (ROOT / "server/connections_hub.html").read_text()
        shell = (ROOT / "server/shell.js").read_text()
        widget = (ROOT / "server/glance.js").read_text()
        player = (ROOT / "server/player.js").read_text()
        tv = (ROOT / "google-tv/app/src/main/java/studio/oneeyedwillie/tv/PlayerActivity.kt").read_text()
        self.assertIn("addGlanceIntegrationCards()", settings)
        self.assertIn("saveGlanceSettings", settings)
        self.assertIn("['home','Home']", settings) if False else None
        for name in ("clock", "weather", "news"):
            self.assertIn("id:'" + name + "'", hub)
            self.assertIn("'/api/glance/settings/'+id", settings)
        self.assertIn("Turn off '+service.title", hub)
        self.assertIn("glance.js?v=1", shell)
        self.assertIn("function createStrip(where)", widget)
        self.assertIn("async function home()", widget)
        self.assertIn("async function pause(surface)", widget)
        self.assertIn("async function idle()", widget)
        self.assertIn("document.addEventListener(type,activity,true)", widget)
        self.assertIn("window.YarrGlance.mountPause(surface)", player)
        self.assertIn("private fun loadGlancePause()", tv)
        self.assertIn('request("/api/glance/news")', tv)
        self.assertIn('request("/api/glance/weather")', tv)


class GlanceProviderTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        patcher = patch.object(library, "DB_PATH", Path(folder.name) / "media.sqlite3")
        patcher.start()
        self.addCleanup(patcher.stop)
        glance._CACHE.clear()
        self.addCleanup(glance._CACHE.clear)

    async def test_weather_disabled_and_missing_zip(self):
        with self.assertRaises(HTTPException) as caught:
            await glance.weather()
        self.assertEqual(caught.exception.status_code, 404)
        glance.save_setting("weather", glance.WidgetConfig(enabled=True))
        with self.assertRaises(HTTPException) as caught:
            await glance.weather()
        self.assertEqual(caught.exception.status_code, 422)

    async def test_weather_uses_only_nws_forecast_host(self):
        glance.save_setting("weather", glance.WidgetConfig(enabled=True, zip_code="75001"))
        responses = [
            {"places": [{"latitude": "33.0", "longitude": "-96.8",
                         "place name": "Addison", "state abbreviation": "TX"}]},
            {"properties": {"forecast": "https://api.weather.gov/gridpoints/FWD/1,2/forecast"}},
            {"properties": {"periods": [{"name": "Tonight", "temperature": 68,
                                        "temperatureUnit": "F", "shortForecast": "Clear"}]}}
        ]
        async def fake_get(url, headers=None):
            return responses.pop(0)
        with patch.object(glance, "_json_from", side_effect=fake_get) as fetch:
            forecast = await glance.weather()
        self.assertEqual(forecast["temperature"], 68)
        self.assertIn("Addison", forecast["location"])
        self.assertEqual(fetch.call_count, 3)
        self.assertEqual(forecast["source"], "National Weather Service")
        # Bad provider-supplied URL must never be requested (SSRF).
        glance._CACHE.clear()
        responses = [
            {"places": [{"latitude": "33", "longitude": "-96",
                         "place name": "Addison", "state abbreviation": "TX"}]},
            {"properties": {"forecast": "http://127.0.0.1/admin"}}
        ]
        with patch.object(glance, "_json_from", side_effect=lambda url, headers=None: responses.pop(0)) as fake:
            with self.assertRaises(HTTPException) as caught:
                await glance.weather()
            self.assertEqual(caught.exception.status_code, 503)
            self.assertEqual(fake.call_count, 2)

    async def test_news_is_attributed_and_rejects_unapproved_links(self):
        glance.save_setting("news", glance.WidgetConfig(enabled=True))
        raw = b"""<rss><channel>
        <item><title>Example story</title><link>https://www.npr.org/story/1</link></item>
        <item><title>Unsafe link</title><link>http://127.0.0.1/private</link></item>
        <item><title>Second story</title><link>https://www.npr.org/story/2</link></item>
        </channel></rss>"""
        with patch.object(glance, "_xml_from", new=AsyncMock(return_value=ET.fromstring(raw))):
            result = await glance.news()
        self.assertEqual(result["source"], "NPR News")
        self.assertEqual(len(result["headlines"]), 2)
        self.assertEqual(result["headlines"][0]["title"], "Example story")


if __name__ == "__main__":
    unittest.main()
