import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from server import arr, library, movies, tv


class ArrConnectionTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        patches = [
            patch.object(library, "DB_PATH", self.root / "test.db"),
            patch.object(arr, "SONARR_FILE", self.root / "sonarr.json"),
            patch.object(movies, "SETTINGS_PATH", self.root / "radarr.json"),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def test_status_does_not_expose_keys(self):
        arr.SONARR_FILE.write_text(json.dumps({
            "url": "http://192.168.86.29:8989", "api_key": "private-sonarr-key",
            "api_version": "v3",
        }))
        response = arr.connection_status()
        self.assertTrue(response["sonarr"]["connected"])
        self.assertFalse(response["radarr"]["connected"])
        self.assertNotIn("private-sonarr-key", str(response))

    def test_sonarr_connection_verified_and_saved(self):
        with patch.object(arr, "_request", return_value=[]) as request:
            value = arr.connect("sonarr", arr.ConnectInput(
                url="http://192.168.86.29:8989",
                api_key="test-sonarr-secret-1234",
            ))
        self.assertTrue(value["connected"])
        self.assertEqual(arr._sonarr_settings()["api_version"], "v3")
        self.assertEqual(request.call_args.args[2], "series")
        self.assertNotIn("test-sonarr-secret-1234", str(arr.connection_status()))

    def test_sonarr_v5_fallback(self):
        def fake(name, settings, resource, **kwargs):
            if settings["api_version"] == "v3":
                raise HTTPException(502, "not found")
            return []
        with patch.object(arr, "_request", side_effect=fake):
            arr.connect("sonarr", arr.ConnectInput(
                url="http://192.168.86.29:8989",
                api_key="test-sonarr-secret-1234",
            ))
        self.assertEqual(arr._sonarr_settings()["api_version"], "v5")

    def test_only_lan_addresses_supported(self):
        for addr in ("https://example.org:8989", "http://127.0.0.1:8989",
                     "http://8.8.8.8:8989", "http://evil.invalid:8989"):
            with self.assertRaises(HTTPException):
                arr._base_url(addr)
        self.assertEqual(arr._base_url("http://192.168.86.29:8989"),
                         "http://192.168.86.29:8989")

    def test_lookup_matches_exact_ids_without_credentials(self):
        with patch.object(arr, "_get", side_effect=[
            [{"title": "Severance", "tvdbId": 379481, "year": 2022,
              "overview": "Office drama."}],
            [{"title": "Existing", "tvdbId": 12345}],
        ]):
            result = arr.lookup("sonarr", "Severance")
        self.assertEqual(result["items"][0]["id"], 379481)
        self.assertEqual(result["items"][0]["provider"], "sonarr")
        self.assertFalse(result["items"][0]["already_added"])
        self.assertNotIn("api_key", str(result))

    def test_add_to_sonarr_requires_folder_profile_and_never_searches_unasked(self):
        setting = {"url": "http://192.168.86.29:8989", "api_key": "secret",
                   "api_version": "v3"}
        option_data = {
            "folders": [{"path": "/tv", "label": "/tv"}],
            "profiles": [{"id": 4, "name": "HD"}],
        }
        requests = []
        def fake_request(name, settings, resource, **kwargs):
            requests.append((resource, kwargs))
            return {"id": 900, "title": "Severance"}
        def fake_get(name, resource, query=None):
            if resource == "series":
                return []
            if resource == "series/lookup":
                return [{"tvdbId": 379481, "title": "Severance", "seasons": [],
                         "seriesType": "standard"}]
            raise AssertionError(resource)
        with patch.object(arr, "_settings", return_value=setting), \
             patch.object(arr, "options", return_value=option_data), \
             patch.object(arr, "_get", side_effect=fake_get), \
             patch.object(arr, "_request", side_effect=fake_request):
            result = arr.add("sonarr", arr.AddInput(
                external_id=379481, root_folder="/tv", quality_profile_id=4
            ))
        self.assertTrue(result["added"])
        payload = requests[0][1]["payload"]
        self.assertFalse(payload["addOptions"]["searchForMissingEpisodes"])
        self.assertEqual(payload["tvdbId"], 379481)
        self.assertEqual(payload["rootFolderPath"], "/tv")
        self.assertTrue(payload["monitored"])

    def test_add_movie_requests_search_only_when_checked(self):
        setting = {"url": "http://192.168.86.29:7878", "api_key": "secret"}
        options = {"folders": [{"path": "/movies", "label": "/movies"}],
                   "profiles": [{"id": 2, "name": "HD"}]}
        sent = []
        def fake_get(name, resource, query=None):
            return [] if resource == "movie" else [{"tmdbId": 603, "title": "The Matrix"}]
        def fake_request(name, settings, resource, **kwargs):
            sent.append(kwargs["payload"])
            return {"title": "The Matrix", "id": 100}
        with patch.object(arr, "_settings", return_value=setting), \
             patch.object(arr, "_get", side_effect=fake_get), \
             patch.object(arr, "options", return_value=options), \
             patch.object(arr, "_request", side_effect=fake_request):
            arr.add("radarr", arr.AddInput(external_id=603,
                root_folder="/movies",quality_profile_id=2,search_now=True))
        self.assertTrue(sent[0]["addOptions"]["searchForMovie"])
        self.assertEqual(sent[0]["tmdbId"], 603)

    def test_unknown_profile_cannot_add(self):
        with patch.object(arr, "_settings", return_value={"url": "http://192.168.86.29:8989"}), \
             patch.object(arr, "options", return_value={"folders": [], "profiles": []}):
            with self.assertRaises(HTTPException):
                arr.add("sonarr", arr.AddInput(external_id=33,
                    root_folder="/tmp",quality_profile_id=1))

    def test_duplicate_prevented(self):
        settings = {"url": "http://192.168.86.29:7878", "api_key": "secret"}
        options = {"folders": [{"path": "/movies", "label": "/movies"}],
                   "profiles": [{"id": 1, "name": "HD"}]}
        with patch.object(arr, "_settings", return_value=settings), \
             patch.object(arr, "options", return_value=options), \
             patch.object(arr, "_get", return_value=[{"tmdbId": 603}]):
            with self.assertRaises(HTTPException) as error:
                arr.add("radarr", arr.AddInput(external_id=603,
                    root_folder="/movies",quality_profile_id=1))
        self.assertEqual(error.exception.status_code, 409)

    def test_sonarr_info_caches_snapshot_without_paths(self):
        arr.SONARR_FILE.write_text(json.dumps({"url": "http://192.168.86.29:8989",
            "api_key": "private-sonarr-key", "api_version": "v3"}))
        records = [{"title": "Severance", "year": 2022,
                    "overview": "A strange workplace.", "tvdbId": 379481,
                    "path": "/private/tv", "images": [],
                    "seasons": [{"seasonNumber": 1}]}]
        with patch.object(arr, "_request", return_value=records) as get:
            first = arr.sonarr_metadata("Severance", 2022)
            second = arr.sonarr_metadata("Severance", 2022)
        self.assertEqual(get.call_count, 1)
        self.assertEqual(first["overview"], "A strange workplace.")
        self.assertEqual(second["source"], "Sonarr")
        self.assertNotIn("/private/tv", str(first))
        self.assertNotIn("private-sonarr-key", str(second))


if __name__ == "__main__":
    unittest.main()
