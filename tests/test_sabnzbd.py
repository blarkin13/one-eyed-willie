import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from server import sabnzbd

class SABnzbdTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        setting = patch.object(sabnzbd, "CONFIG", Path(self.temp.name) / "sab.json")
        setting.start()
        self.addCleanup(setting.stop)

    def test_local_addresses_only(self):
        self.assertEqual(sabnzbd.normalize_url("http://192.168.86.29:8080"),
                         "http://192.168.86.29:8080")
        self.assertEqual(sabnzbd.normalize_url("http://host.docker.internal:8080/"),
                         "http://host.docker.internal:8080")
        for url in ("https://example.com:8080", "http://8.8.8.8:8080",
                    "http://localhost:8080/admin", "http://localhost:8080?apikey=a",
                    "http://localhost:8080@evil.example.com:8080"):
            with self.assertRaises(HTTPException):
                sabnzbd.normalize_url(url)

    def test_key_never_leaked_and_limited_actions(self):
        with patch.object(sabnzbd, "request", return_value={"queue": {"slots": [], "paused": False}}):
            state = sabnzbd.save_settings(
                sabnzbd.ConnectionRequest(url="http://192.168.86.29:8080", api_key="verysecretapikey")
            )
            self.assertEqual(state["address"], "http://192.168.86.29:8080")
            self.assertNotIn("verysecretapikey", str(state))
            self.assertNotIn("verysecretapikey", str(sabnzbd.get_settings()))
        with self.assertRaises(HTTPException):
            sabnzbd.control_queue(sabnzbd.QueueAction(action="delete"))
        with patch.object(sabnzbd, "request", return_value={"status": True}) as call:
            value = sabnzbd.control_queue(sabnzbd.QueueAction(action="pause"))
            self.assertTrue(value["ok"])
            self.assertEqual(call.call_args.args[2], "pause")
        self.assertFalse(sabnzbd.disconnect()["connected"])

    def test_read_only_queue_history_response(self):
        with patch.object(sabnzbd, "saved", return_value={"url": "http://localhost:8080", "api_key": "secret"}), \
             patch.object(sabnzbd, "request", side_effect=[
                 {"queue": {"paused": False, "noofslots": 1, "speed": "3M", "slots": [
                     {"filename": "Movie", "percentage": "42", "status": "Downloading"}]}},
                 {"history": {"slots": [{"name": "Completed Movie", "status": "Completed"}]}}
             ]):
            result = sabnzbd.status()
        self.assertEqual(result["queue"]["items"][0]["name"], "Movie")
        self.assertEqual(result["history"][0]["status"], "Completed")
        self.assertNotIn("api_key", str(result))

if __name__ == "__main__":
    unittest.main()
