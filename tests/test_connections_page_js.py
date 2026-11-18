"""Regression checks for the Connections settings directory.

A JavaScript syntax error previously prevented the dynamically generated
Radarr/Sonarr/Lidarr forms and all connection statuses from initializing.
"""
from pathlib import Path
import re
import shutil
import subprocess
import unittest

PAGE = Path(__file__).resolve().parents[1] / "server" / "arr_connections.html"


class ConnectionsPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = PAGE.read_text(encoding="utf-8")
        match = re.search(r"<script>([\\s\\S]*?)</script>", cls.html)
        assert match, "Connections page must include its initialization script"
        cls.script = match.group(1)

    def test_all_six_connection_services_present(self):
        for service in ("radarr", "sonarr", "lidarr"):
            with self.subTest(service=service):
                self.assertIn("id:'" + service + "'", self.script)
        for service in ("sab-form", "plex-form", "os-form"):
            with self.subTest(service=service):
                self.assertIn('id="' + service + '"', self.html)
        self.assertIn("build();initConnectionDirectory();refresh();", self.script)

    def test_search_and_expand_controls_present(self):
        for control in ("connection-search", "connections-expand",
                        "connections-collapse", "connections-count"):
            self.assertIn('id="' + control + '"', self.html)
        self.assertIn("search.addEventListener('input',filter)", self.script)

    def test_arr_and_lidarr_status_fail_independently(self):
        self.assertIn("Promise.allSettled", self.script)
        self.assertIn("/api/arr/connections", self.script)
        self.assertIn("/api/lidarr/connection", self.script)
        self.assertIn("Status unavailable", self.script)

    @unittest.skipUnless(shutil.which("node"), "Node.js unavailable for syntax validation")
    def test_connections_javascript_parses(self):
        result = subprocess.run(
            ["node", "--check", "-"],
            input=self.script, text=True, capture_output=True, check=False
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
