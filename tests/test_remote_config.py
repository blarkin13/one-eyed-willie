import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from server import remote_config as mod


class RemoteConfigTests(unittest.TestCase):
    def test_save_and_load(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(mod, "CONFIG_FILE", Path(directory) / "remote.json"):
                settings = mod.RemoteSettings(
                    public_ip="76.183.183.204",
                    public_url="https://one-eyed-willie.larki-brian.workers.dev",
                )
                response = mod.save_remote_settings(settings)
                self.assertFalse(response["remote_access_ready"])
                self.assertEqual(response["origin_hostname"], "76-183-183-204.sslip.io")
                saved = mod.get_remote_settings()
                self.assertEqual(saved["public_ip"], "76.183.183.204")
                self.assertEqual(saved["public_url"], "https://one-eyed-willie.larki-brian.workers.dev")
                self.assertEqual(json.loads(mod.CONFIG_FILE.read_text())["public_ip"], "76.183.183.204")

    def test_reject_private_ip(self):
        with self.assertRaises(HTTPException):
            mod.normalized(mod.RemoteSettings(public_ip="192.168.86.29"))

    def test_reject_http_url(self):
        with self.assertRaises(HTTPException):
            mod.normalized(mod.RemoteSettings(public_url="http://example.org"))

    def test_reject_url_with_credentials(self):
        with self.assertRaises(HTTPException):
            mod.normalized(mod.RemoteSettings(public_url="https://name:secret@example.org"))

    def test_reject_malformed_port(self):
        with self.assertRaises(HTTPException):
            mod.normalized(mod.RemoteSettings(public_url="https://example.org:bad"))

    def test_default_empty_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(mod, "CONFIG_FILE", Path(directory) / "remote.json"):
                response = mod.get_remote_settings()
                self.assertEqual(response["public_ip"], "")
                self.assertEqual(response["origin_hostname"], "")
                self.assertFalse(response["remote_access_ready"])


if __name__ == "__main__":
    unittest.main()
