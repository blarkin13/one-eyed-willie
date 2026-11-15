import unittest
from unittest.mock import patch

from fastapi import HTTPException

from server import manager_advanced, manager_control


class SonarrEpisodeDrilldownTests(unittest.TestCase):
    def setUp(self):
        self.setting = {"url": "http://192.168.86.29:8989",
                        "api_key": "private-test-secret", "api_version": "v3"}
        self.series = {"id": 22, "title": "Example Series"}
        self.episodes = [
            {"id": 101, "seriesId": 22, "title": "Pilot",
             "seasonNumber": 1, "episodeNumber": 1, "monitored": False},
            {"id": 102, "seriesId": 22, "title": "Second Episode",
             "seasonNumber": 1, "episodeNumber": 2, "monitored": False},
        ]

    def test_bulk_monitor_updates_only_chosen_episodes(self):
        calls = []
        def fake_request(name, setting, resource, method="GET", payload=None, query=None):
            calls.append((resource, method, payload, query))
            if resource == "series/22":
                return self.series
            if resource == "episode" and method == "GET":
                return [row.copy() for row in self.episodes]
            if resource == "episode/monitor" and method == "PUT":
                for episode in self.episodes:
                    if episode["id"] in payload["episodeIds"]:
                        episode["monitored"] = payload["monitored"]
                return []
            raise AssertionError((resource, method))
        with patch.object(manager_advanced, "_provider", return_value=self.setting), \
             patch.object(manager_advanced, "_request", side_effect=fake_request):
            result = manager_advanced.bulk_episodes(
                22, manager_advanced.EpisodeBulkChange(action="monitor", episode_ids=[102]))
        self.assertEqual(result, {"action": "monitor", "count": 1, "monitored": True})
        self.assertFalse(self.episodes[0]["monitored"])
        self.assertTrue(self.episodes[1]["monitored"])
        self.assertEqual(calls[2][0], "episode/monitor")
        self.assertEqual(calls[2][2], {"episodeIds": [102], "monitored": True})

    def test_bulk_search_uses_selected_ids(self):
        calls = []
        def fake_request(name, setting, resource, method="GET", payload=None, query=None):
            calls.append((resource, method, payload))
            if resource == "series/22":return self.series
            if resource == "episode":return self.episodes
            if resource == "command" and method == "POST":return {"id": 77}
            raise AssertionError(resource)
        with patch.object(manager_advanced, "_provider", return_value=self.setting), \
             patch.object(manager_advanced, "_request", side_effect=fake_request):
            result = manager_advanced.bulk_episodes(
                22, manager_advanced.EpisodeBulkChange(action="search", episode_ids=[101, 102]))
        self.assertTrue(result["queued"])
        self.assertEqual(result["count"], 2)
        self.assertEqual(calls[-1][2], {"name": "EpisodeSearch", "episodeIds": [101, 102]})

    def test_other_series_episode_rejected_before_mutation(self):
        with patch.object(manager_advanced, "_provider", return_value=self.setting), \
             patch.object(manager_advanced, "_request", side_effect=[self.series, self.episodes]) as req:
            with self.assertRaises(HTTPException) as result:
                manager_advanced.bulk_episodes(
                    22, manager_advanced.EpisodeBulkChange(action="unmonitor", episode_ids=[999]))
        self.assertEqual(result.exception.status_code, 422)
        self.assertEqual(req.call_count, 2)

    def test_invalid_action_and_duplicate_ids_rejected(self):
        with self.assertRaises(HTTPException):
            manager_advanced.bulk_episodes(
                22, manager_advanced.EpisodeBulkChange(action="delete", episode_ids=[101]))
        with self.assertRaises(HTTPException):
            manager_advanced.bulk_episodes(
                22, manager_advanced.EpisodeBulkChange(action="monitor", episode_ids=[101,101]))

    def test_bulk_monitor_allowlist_only_for_sonarr(self):
        with self.assertRaises(ValueError):
            manager_control._request("radarr", self.setting, "episode/monitor",
                                     method="PUT", payload={"episodeIds":[101],"monitored":True})
        with self.assertRaises(ValueError):
            manager_control._request("sonarr", self.setting, "episode/monitor",
                                     method="POST", payload={"episodeIds":[101],"monitored":True})
        with self.assertRaises(ValueError):
            manager_control._request("sonarr", self.setting, "episode/monitor", method="GET")

    def test_drilldown_route_is_registered(self):
        from server.main import app
        matches=[route for route in app.routes if getattr(route,"path","")=="/sonarr/series/{series_id}"]
        self.assertEqual(len(matches), 1)


if __name__ == "__main__":
    unittest.main()
