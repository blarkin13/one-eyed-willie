import unittest
from unittest.mock import patch

from fastapi import HTTPException

from server import manager_advanced as advanced


class SonarrDownloadedStatusTests(unittest.TestCase):
    def test_episode_file_id_counts_as_downloaded_even_without_hasfile_flag(self):
        episode = {"id": 2, "seasonNumber": 1, "episodeNumber": 2,
                   "hasFile": False, "episodeFileId": 66, "monitored": True}
        metadata = {66: {"id": 66, "path": r"D:\\TV\\Show\\S01E02.mkv",
                         "size": 5368709120,
                         "quality": {"quality": {"name": "Bluray-1080p"}}}}
        result = advanced._episode(episode, metadata)
        self.assertTrue(result["has_file"])
        self.assertEqual(result["file_name"], "S01E02.mkv")
        self.assertEqual(result["file_quality"], "Bluray-1080p")
        self.assertEqual(result["file_size"], 5368709120)
        self.assertTrue(result["monitored"])

    def test_multi_episode_file_metadata_can_be_shared(self):
        episodes = [
            {"id": 20, "episodeFileId": 88, "episodeNumber": 1},
            {"id": 21, "episodeFileId": 88, "episodeNumber": 2},
        ]
        files = {88: {"id": 88, "size": 2000000000,
                      "relativePath": "S01E01-E02.mkv",
                      "quality": {"quality": {"name": "HDTV-720p"}}}}
        rendered = [advanced._episode(row, files) for row in episodes]
        self.assertTrue(all(row["has_file"] for row in rendered))
        self.assertEqual(rendered[0]["file_name"], rendered[1]["file_name"])
        self.assertEqual(rendered[0]["file_quality"], "HDTV-720p")

    def test_nested_file_metadata_without_file_list(self):
        result = advanced._episode({
            "id": 30,
            "hasFile": True,
            "episodeFile": {"id": 123, "relativePath": "S02E03.mp4",
                            "size": 2000,
                            "quality": {"quality": {"name": "WEBRip-720p"}}},
        })
        self.assertTrue(result["has_file"])
        self.assertEqual(result["file_id"], 123)
        self.assertEqual(result["file_quality"], "WEBRip-720p")
        self.assertEqual(result["file_name"], "S02E03.mp4")

    def test_missing_episode_does_not_claim_to_be_downloaded(self):
        result = advanced._episode({"id": 4, "hasFile": False})
        self.assertFalse(result["has_file"])
        self.assertIsNone(result["file_id"])
        self.assertEqual(result["file_quality"], "")
        self.assertIsNone(result["file_size"])

    def test_file_list_failure_still_returns_available_file_flag(self):
        calls = []
        def fake(name, settings, resource, query=None):
            calls.append((resource, query))
            if resource == "series/33":
                return {"id": 33, "title": "Sample Series",
                        "seasons": [{"seasonNumber": 1, "monitored": True}]}
            if resource == "episode":
                return [{"id": 100, "seasonNumber": 1, "episodeNumber": 1,
                         "hasFile": True, "episodeFileId": 444,
                         "monitored": True}]
            if resource == "episodefile":
                raise HTTPException(status_code=502, detail="File metadata unavailable")
            raise AssertionError(resource)
        with patch.object(advanced, "_provider", return_value={"url": "http://localhost:8989",
                                                                  "api_key": "do-not-show"}), \
             patch.object(advanced, "_request", side_effect=fake):
            data = advanced.title_detail("sonarr", 33)
        self.assertTrue(data["episodes"][0]["has_file"])
        self.assertEqual(data["episodes"][0]["file_id"], 444)
        self.assertEqual(data["episodes"][0]["file_quality"], "")
        self.assertEqual(calls[1][1]["includeEpisodeFile"], "true")
        self.assertNotIn("do-not-show", str(data))


if __name__ == "__main__":
    unittest.main()
