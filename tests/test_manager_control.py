import unittest
from unittest.mock import patch

from fastapi import HTTPException

from server import manager_control, sabnzbd


class ManagerControlTests(unittest.TestCase):
    def setUp(self):
        self.setting = {"url": "http://192.168.86.29:7878", "api_key": "private-test-key",
                        "api_version": "v3"}

    def test_dashboard_summarizes_library_without_leaking_credentials(self):
        responses = {
            "movie": [
                {"id": 1, "title": "Arrival", "year": 2016, "monitored": True,
                 "qualityProfileId": 3, "hasFile": True},
                {"id": 2, "title": "Alien", "year": 1979, "monitored": False,
                 "qualityProfileId": 3, "hasFile": False},
            ],
            "qualityprofile": [{"id": 3, "name": "HD"}],
            "queue": {"records": [{"title": "Downloading", "status": "downloading"}]},
            "history": {"records": [{"sourceTitle": "Finished", "eventType": "grabbed"}]},
        }
        def fake(name, setting, resource, **kwargs):
            return responses[resource]
        with patch.object(manager_control, "_provider", return_value=self.setting), \
             patch.object(manager_control, "_request", side_effect=fake):
            data = manager_control.dashboard("radarr")
        self.assertEqual(data["total"], 2)
        self.assertEqual(data["monitored"], 1)
        self.assertEqual(data["missing"], 1)
        self.assertEqual(data["items"][0]["title"], "Alien")
        self.assertEqual(data["items"][1]["profile"], "HD")
        self.assertEqual(data["queue"][0]["title"], "Downloading")
        self.assertEqual(data["history"][0]["title"], "Finished")
        self.assertNotIn(self.setting["api_key"], str(data))

    def test_sonarr_series_stats(self):
        data = manager_control._items("sonarr", [{
            "id": 6, "title": "Severance", "year": 2022, "monitored": True,
            "qualityProfileId": 3,
            "statistics": {"episodeFileCount": 4, "episodeCount": 10},
        }], {3: "1080p"})
        self.assertTrue(data[0]["missing"])
        self.assertEqual(data[0]["subtitle"], "4 / 10 episodes")

    def test_update_monitored_preserves_other_fields(self):
        record = {"id": 2, "title": "Alien", "qualityProfileId": 3,
                  "monitored": False, "rootFolderPath": "/movies"}
        calls = []
        def fake(name, setting, resource, method="GET", payload=None, **kwargs):
            calls.append((resource, method, payload))
            if method == "PUT":
                return payload.copy()
            return record.copy()
        with patch.object(manager_control, "_provider", return_value=self.setting), \
             patch.object(manager_control, "_request", side_effect=fake):
            result = manager_control.update_item(
                "radarr", 2, manager_control.ItemChange(monitored=True))
        self.assertTrue(result["monitored"])
        self.assertEqual(calls[1][0], "movie/2")
        self.assertEqual(calls[1][2]["rootFolderPath"], "/movies")
        self.assertEqual(calls[1][2]["qualityProfileId"], 3)

    def test_profile_must_exist_before_update(self):
        record = {"id": 2, "title": "Alien", "qualityProfileId": 3, "monitored": False}
        with patch.object(manager_control, "_provider", return_value=self.setting), \
             patch.object(manager_control, "_request", side_effect=[record, [{"id": 3, "name": "HD"}]]):
            with self.assertRaises(HTTPException) as ctx:
                manager_control.update_item("radarr", 2,
                    manager_control.ItemChange(quality_profile_id=999))
        self.assertEqual(ctx.exception.status_code, 422)

    def test_sonarr_search_and_rss_are_explicit(self):
        calls = []
        def fake(name, setting, resource, method="GET", payload=None, **kwargs):
            calls.append((resource, method, payload))
            return {"id": 4} if resource == "series/4" else {"id": 12}
        with patch.object(manager_control, "_provider", return_value=self.setting), \
             patch.object(manager_control, "_request", side_effect=fake):
            manager_control.run_command("sonarr", manager_control.CommandInput(action="search", item_id=4))
            manager_control.run_command("sonarr", manager_control.CommandInput(action="rss"))
        self.assertEqual(calls[1][2], {"name": "SeriesSearch", "seriesId": 4})
        self.assertEqual(calls[2][2], {"name": "RssSync"})
        with self.assertRaises(HTTPException):
            manager_control.run_command("sonarr", manager_control.CommandInput(action="delete", item_id=4))

    def test_url_resource_allowlist(self):
        for resource in ("system/backup", "settings/metadata", "queue/1", "movie/../settings"):
            with self.assertRaises(ValueError):
                manager_control._request("radarr", self.setting, resource)

    def test_sabnzbd_per_job_pause_and_resume_only(self):
        setting = {"url": "http://192.168.86.29:8080", "api_key": "private-sab-key"}
        with patch.object(sabnzbd, "saved", return_value=setting), \
             patch.object(sabnzbd, "request", return_value={"status": True}) as request:
            result = sabnzbd.control_job("SABnzbd_nzo_test1234", sabnzbd.JobAction(action="pause"))
        self.assertTrue(result["ok"])
        self.assertEqual(request.call_args.args[2], "queue")
        self.assertEqual(request.call_args.kwargs["name"], "pause")
        self.assertEqual(request.call_args.kwargs["value"], "SABnzbd_nzo_test1234")
        with self.assertRaises(HTTPException):
            sabnzbd.control_job("../../etc/passwd", sabnzbd.JobAction(action="pause"))
        with self.assertRaises(HTTPException):
            sabnzbd.control_job("SABnzbd_nzo_test1234", sabnzbd.JobAction(action="delete"))


if __name__ == "__main__":
    unittest.main()
