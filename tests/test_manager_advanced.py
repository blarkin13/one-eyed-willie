import unittest
from unittest.mock import patch

from fastapi import HTTPException

from server import manager_advanced as advanced
from server import manager_control


class AdvancedManagerTests(unittest.TestCase):
    def setUp(self):
        self.setting={"url":"http://192.168.86.29:8989","api_key":"private-secret",
                      "api_version":"v3"}

    def test_calendar_and_missing_are_sanitized(self):
        def fake(name,setting,resource,**kwargs):
            if resource=="calendar":
                return [{"id":5,"title":"New episode","seriesId":22,"series":{"title":"Test Series"},
                         "seasonNumber":1,"episodeNumber":3,"airDateUtc":"2026-12-01"}]
            return {"records":[{"id":5,"title":"Missing","seriesId":22,
                    "series":{"title":"Test Series"},"seasonNumber":1,"episodeNumber":3}]}
        with patch.object(advanced,"_provider",return_value=self.setting), \
             patch.object(advanced,"_request",side_effect=fake):
            calendar=advanced.view_section("sonarr","calendar",page=1)
            missing=advanced.view_section("sonarr","missing",page=1)
        self.assertEqual(calendar["items"][0]["title"],"Test Series")
        self.assertEqual(missing["items"][0]["item_id"],22)
        self.assertNotIn("private-secret",str(calendar)+str(missing))

    def test_series_details_include_episodes_and_seasons(self):
        def fake(name,setting,resource,**kwargs):
            if resource=="series/22":
                return {"id":22,"title":"Test Series","overview":"Science fiction",
                        "seasons":[{"seasonNumber":1,"monitored":True,"statistics":{"episodeCount":4}}]}
            if resource=="episode":
                return [{"id":50,"seasonNumber":1,"episodeNumber":2,"title":"Episode 2",
                         "monitored":True,"hasFile":False},
                        {"id":49,"seasonNumber":1,"episodeNumber":1,"title":"Episode 1",
                         "monitored":True,"hasFile":True}]
            raise AssertionError(resource)
        with patch.object(advanced,"_provider",return_value=self.setting), \
             patch.object(advanced,"_request",side_effect=fake):
            detail=advanced.title_detail("sonarr",22)
        self.assertEqual(detail["seasons"][0]["number"],1)
        self.assertEqual(detail["episodes"][0]["episode"],1)
        self.assertEqual(detail["episodes"][1]["title"],"Episode 2")

    def test_season_monitor_updates_only_selected_season(self):
        original={"id":22,"title":"Example",
                  "seasons":[{"seasonNumber":1,"monitored":True},
                             {"seasonNumber":2,"monitored":True}]}
        calls=[]
        def fake(name,setting,resource,method="GET",payload=None,**kwargs):
            calls.append((resource,method,payload))
            return payload.copy() if method=="PUT" else {
                **original,"seasons":[x.copy() for x in original["seasons"]]
            }
        with patch.object(advanced,"_provider",return_value=self.setting), \
             patch.object(advanced,"_request",side_effect=fake):
            result=advanced.season_monitor("sonarr",22,1,advanced.SeasonChange(monitored=False))
        self.assertFalse(result["monitored"])
        self.assertTrue(calls[1][2]["seasons"][1]["monitored"])

    def test_episode_search_uses_exact_episode_command(self):
        def fake(name,setting,resource,method="GET",payload=None,**kwargs):
            if resource=="episode/55":
                return {"id":55,"seriesId":22}
            if resource=="command":
                self.assertEqual(payload,{"name":"EpisodeSearch","episodeIds":[55]})
                return {"id":4,"name":"EpisodeSearch"}
            raise AssertionError(resource)
        with patch.object(advanced,"_provider",return_value=self.setting), \
             patch.object(advanced,"_request",side_effect=fake):
            result=advanced.advanced_command("sonarr",
                advanced.ExtendedCommand(action="episode",episode_id=55))
        self.assertTrue(result["queued"])

    def test_manual_grab_revalidates_upstream_release(self):
        seen=[]
        def fake(name,setting,resource,method="GET",payload=None,**kwargs):
            seen.append((resource,method))
            if resource=="movie/7":
                return {"id":7}
            if resource=="release" and method=="GET":
                return [{"guid":"unique-abc","indexerId":9,"title":"Verified release"}]
            if resource=="release" and method=="POST":
                self.assertEqual(payload["guid"],"unique-abc")
                return {"title":"Verified release"}
            raise AssertionError(resource)
        with patch.object(advanced,"_provider",return_value=self.setting), \
             patch.object(advanced,"_request",side_effect=fake):
            result=advanced.grab_release("radarr",advanced.GrabInput(
                item_id=7,guid="unique-abc",indexer_id=9))
            with self.assertRaises(HTTPException):
                advanced.grab_release("radarr",advanced.GrabInput(
                    item_id=7,guid="untrusted",indexer_id=9))
        self.assertTrue(result["submitted"])
        self.assertEqual(sum(1 for resource,method in seen if method=="POST"),1)

    def test_queue_removal_does_not_remove_from_client_by_default(self):
        captured=[]
        def fake(name,setting,resource,method="GET",query=None,**kwargs):
            captured.append((resource,method,query))
            if resource=="queue":
                return {"records":[{"id":10}]}
            return {}
        with patch.object(advanced,"_provider",return_value=self.setting), \
             patch.object(advanced,"_request",side_effect=fake):
            result=advanced.remove_queue_entry("sonarr",10,advanced.QueueRemoveInput())
        self.assertTrue(result["removed"])
        self.assertEqual(captured[-1][2]["removeFromClient"],"false")
        self.assertEqual(captured[-1][2]["blocklist"],"false")

    def test_library_remove_keeps_files(self):
        captured=[]
        def fake(name,setting,resource,method="GET",query=None,**kwargs):
            captured.append((resource,method,query))
            if method=="GET": return {"id":7}
            return {}
        with patch.object(advanced,"_provider",return_value=self.setting), \
             patch.object(advanced,"_request",side_effect=fake):
            result=advanced.remove_title("radarr",7,advanced.LibraryRemoveInput(preserve_files=True))
            with self.assertRaises(HTTPException):
                advanced.remove_title("radarr",7,advanced.LibraryRemoveInput(preserve_files=False))
        self.assertTrue(result["files_preserved"])
        self.assertEqual(captured[1][2],{"deleteFiles":"false"})

    def test_upstream_api_rejects_unknown_paths_and_methods(self):
        for resource in ("system/shutdown","system/backup","downloadclient/23","queue/../../etc/passwd"):
            with self.assertRaises(ValueError):
                manager_control._request("radarr",self.setting,resource)
        with self.assertRaises(ValueError):
            manager_control._request("radarr",self.setting,"queue/10")
        with self.assertRaises(ValueError):
            manager_control._request("sonarr",self.setting,"episode/5",method="DELETE")

if __name__=="__main__":
    unittest.main()
