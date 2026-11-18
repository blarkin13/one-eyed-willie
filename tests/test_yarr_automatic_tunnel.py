"""Tests for opt-in Yarr tunnel credential handling and safe startup."""
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from server import yarr_pairing as pairing


class SingleIterationStop:
    def __init__(self):
        self.calls = 0

    def is_set(self):
        self.calls += 1
        return self.calls > 1

    def wait(self, timeout):
        return None


class YarrAutomaticTunnelTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.token_path = Path(self.temp.name) / "token"
        self.bin_path = Path(self.temp.name) / "cloudflared"
        self.bin_path.write_text("#!/bin/sh\nexit 0\n")
        self.bin_path.chmod(0o700)
        self.patches = [
            patch.object(pairing, "TUNNEL_TOKEN_FILE", self.token_path),
            patch.object(pairing, "TUNNEL_BIN", str(self.bin_path)),
            patch.object(pairing, "_tunnel_process", None),
            patch.object(pairing, "_tunnel_message", "Not started"),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def test_token_is_private_and_not_in_process_arguments(self):
        token = "a" * 120
        process = MagicMock()
        process.poll.return_value = None
        with patch.object(pairing, "_read", return_value={"status": "paired", "poll_secret": "x" * 50}), \
             patch.object(pairing, "_cloud", return_value={"status": "ready", "tunnel_token": token}), \
             patch.object(pairing, "get_server_id", return_value="d497ae77-aaca-42ab-90b5-8f7256e3ac36"), \
             patch.object(pairing.subprocess, "Popen", return_value=process) as popen:
            pairing.automatic_tunnel_loop(SingleIterationStop())
        self.assertEqual(self.token_path.read_text().strip(), token)
        self.assertEqual(self.token_path.stat().st_mode & 0o777, 0o600)
        args = popen.call_args.args[0]
        self.assertIn("--token-file", args)
        self.assertNotIn(token, args)
        self.assertNotIn("sudo", args)
        process.terminate.assert_called_once()

    def test_unpaired_install_never_requests_token_or_starts_connector(self):
        with patch.object(pairing, "_read", return_value={}), \
             patch.object(pairing, "_cloud") as remote, \
             patch.object(pairing.subprocess, "Popen") as popen:
            pairing.automatic_tunnel_loop(SingleIterationStop())
        remote.assert_not_called()
        popen.assert_not_called()
        self.assertFalse(self.token_path.exists())

    def test_revoked_credential_does_not_start_tunnel(self):
        from fastapi import HTTPException
        with patch.object(pairing, "_read", return_value={"status": "paired", "poll_secret": "x" * 50}), \
             patch.object(pairing, "_cloud", side_effect=HTTPException(401, "Revoked")), \
             patch.object(pairing, "get_server_id", return_value="d497ae77-aaca-42ab-90b5-8f7256e3ac36"), \
             patch.object(pairing.subprocess, "Popen") as popen:
            pairing.automatic_tunnel_loop(SingleIterationStop())
        popen.assert_not_called()
        self.assertFalse(self.token_path.exists())


if __name__ == "__main__":
    unittest.main()
