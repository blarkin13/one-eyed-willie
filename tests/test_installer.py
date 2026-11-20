"""The one-line installer, run for real against stub docker/systemctl/curl."""
import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "deploy/install.sh"
STUBS = {
    "docker": 'echo "docker $*" >> "$STUB_LOG"; exit 0',
    "systemctl": 'echo "systemctl $*" >> "$STUB_LOG"; exit 0',
    "curl": 'echo "curl $*" >> "$STUB_LOG"; exit 0',
    "upnpc": 'echo "upnpc $*" >> "$STUB_LOG"; exit 0',
    "ip": 'echo "1.1.1.1 via 192.168.1.1 dev eth0 src 192.168.1.50 uid 0"',
    "apt-get": 'exit 0',
}


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        bin_dir = self.tmp / "bin"
        bin_dir.mkdir()
        for name, body in STUBS.items():
            path = bin_dir / name
            path.write_text("#!/usr/bin/env bash\n" + body + "\n")
            path.chmod(path.stat().st_mode | stat.S_IEXEC)
        self.media = self.tmp / "My Media"
        self.media.mkdir()
        self.log = self.tmp / "calls.log"
        self.env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "STUB_LOG": str(self.log),
                    "YARR_TEST_MODE": "1", "YARR_MEDIA_DIR": str(self.media),
                    "YARR_INSTALL_DIR": str(self.tmp / "opt"), "YARR_DATA_DIR": str(self.tmp / "var"),
                    "YARR_SBIN_DIR": str(self.tmp / "sbin"), "YARR_SYSTEMD_DIR": str(self.tmp / "systemd")}
        (self.tmp / "sbin").mkdir()
        (self.tmp / "systemd").mkdir()

    def run_installer(self, **extra):
        result = subprocess.run(["bash", str(SCRIPT)], env={**self.env, **extra}, stdin=subprocess.DEVNULL,
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        return result

    def test_installs_server_https_front_door_and_daily_updates(self):
        out = self.run_installer().stdout
        compose = yaml.safe_load((self.tmp / "opt/compose.yaml").read_text())
        yarr = compose["services"]["yarr"]
        self.assertEqual(yarr["image"], "ghcr.io/blarkin13/yarr-media:stable")
        self.assertIn(f"{self.media}:/media:ro", yarr["volumes"], "paths with spaces survive")
        self.assertIn("8787:8787", yarr["ports"])
        https = compose["services"]["https"]
        self.assertIn("443:443", https["ports"])
        caddy = (self.tmp / "opt/Caddyfile").read_text()
        self.assertIn("ask http://yarr:8787/api/remote/tls-check", caddy)
        self.assertIn("on_demand", caddy)
        self.assertIn("header_up X-Yarr-Remote 1", caddy)
        service = (self.tmp / "systemd/yarr-media-update.service").read_text()
        self.assertIn(f"ExecStart={self.tmp}/sbin/yarr-media-update", service)
        self.assertIn("OnCalendar=", (self.tmp / "systemd/yarr-media-update.timer").read_text())
        calls = self.log.read_text()
        self.assertIn("docker compose up -d --remove-orphans", calls)
        self.assertIn("systemctl enable --now yarr-media-update.timer", calls)
        self.assertIn("upnpc -e Yarr Media -a 192.168.1.50 443 443 TCP 0", calls)
        self.assertIn("http://192.168.1.50:8787", out)
        self.assertIn("accepted the port 443 forward", out)

    def test_rerun_keeps_the_media_folder_and_remote_can_be_skipped(self):
        self.run_installer()
        env_file = (self.tmp / "opt/.env").read_text()
        self.assertIn(f"YARR_MEDIA_DIR={self.media}", env_file)
        self.env.pop("YARR_MEDIA_DIR")
        self.run_installer(YARR_NO_REMOTE="1", YARR_CHANNEL="edge")
        compose = yaml.safe_load((self.tmp / "opt/compose.yaml").read_text())
        self.assertNotIn("https", compose["services"])
        self.assertEqual(compose["services"]["yarr"]["image"], "ghcr.io/blarkin13/yarr-media:edge")
        self.assertIn(f"{self.media}:/media:ro", compose["services"]["yarr"]["volumes"])

    def test_refuses_a_missing_media_folder(self):
        result = subprocess.run(["bash", str(SCRIPT)], env={**self.env, "YARR_MEDIA_DIR": "/does/not/exist"},
                                stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("does not exist", result.stderr)

    @unittest.skipUnless(shutil.which("caddy"), "caddy binary not installed")
    def test_caddyfiles_are_valid(self):
        self.run_installer()
        for path in (self.tmp / "opt/Caddyfile", ROOT / "deploy/Caddyfile.remote"):
            env = {**os.environ, "WILLIE_HOSTNAME": "1-2-3-4.sslip.io"}
            r = subprocess.run(["caddy", "adapt", "--config", str(path), "--adapter", "caddyfile"],
                               capture_output=True, text=True, env=env)
            self.assertEqual(r.returncode, 0, path.name + ": " + r.stderr)


if __name__ == "__main__":
    unittest.main()
