"""Regression checks for server auto-deployment configuration."""
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UPDATE = ROOT / "deploy" / "update.sh"
REMOTE_SETUP = ROOT / "scripts" / "enable-remote.sh"


class AutomaticUpdateTests(unittest.TestCase):
    def test_remote_mode_loads_the_private_setup_env_file(self):
        script = UPDATE.read_text()
        setup = REMOTE_SETUP.read_text()
        self.assertIn('ENV_FILE="$ROOT/.env.remote"', setup)
        self.assertIn('compose_files=(-f compose.remote.yaml)', script)
        self.assertIn('compose_env=(--env-file "$APP_DIR/.env.remote")', script)
        self.assertIn('compose() { docker compose "${compose_env[@]}" "${compose_files[@]}" "$@"; }', script)
        self.assertIn('if [[ ! -f "$APP_DIR/.env.remote" ]]; then', script)
        self.assertIn("compose config --quiet", script)
        self.assertIn("compose up -d --no-build", script)
        self.assertNotIn("cat .env.remote", script)

    @unittest.skipUnless(shutil.which("bash"), "bash unavailable")
    def test_update_shell_script_syntax(self):
        check = subprocess.run(["bash", "-n", str(UPDATE)],
                               capture_output=True, text=True, timeout=5)
        self.assertEqual(check.returncode, 0, check.stderr)


if __name__ == "__main__":
    unittest.main()
