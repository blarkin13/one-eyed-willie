"""The permanent app signing key: script, Gradle and CI wiring.

Every TV/phone build must be signed with the same key, or Android refuses to
install it over the previous build and the user has to uninstall (losing
their server address and Yarr sign-in).
"""
import base64
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "google-tv/create-signing-key.sh"


class GradleAndCiTests(unittest.TestCase):
    def test_both_apps_sign_with_the_key_when_ci_provides_it(self):
        for module in ("app", "phone"):
            gradle = (ROOT / f"google-tv/{module}/build.gradle.kts").read_text()
            self.assertIn('System.getenv("YARR_KEYSTORE")', gradle, module)
            self.assertIn('keyAlias = "yarr-media"', gradle, module)
            self.assertEqual(gradle.count('signingConfig = signingConfigs.getByName("yarr")'), 2, module)

    def test_ci_and_release_pass_the_key_and_show_fingerprints(self):
        for name in ("google-tv.yml", "release.yml"):
            workflow = (ROOT / ".github/workflows" / name).read_text()
            self.assertIn("secrets.ANDROID_KEYSTORE_BASE64", workflow, name)
            self.assertIn('echo "YARR_KEYSTORE=', workflow, name)
            self.assertLess(workflow.index("Use the permanent app signing key"), workflow.index("assembleLean"), name)
        self.assertIn("apksigner", (ROOT / ".github/workflows/google-tv.yml").read_text())


@unittest.skipUnless(shutil.which("keytool") and shutil.which("openssl"), "keytool and openssl required")
class ScriptTests(unittest.TestCase):
    def run_script(self, tmp, env_extra=None):
        bindir = Path(tmp) / "bin"; bindir.mkdir(exist_ok=True)
        gh = bindir / "gh"
        gh.write_text('#!/usr/bin/env bash\ncat > "$FAKE_GH_DIR/secret-$3"\n')
        gh.chmod(0o755)
        env = dict(os.environ, PATH=f"{bindir}:{os.environ['PATH']}", FAKE_GH_DIR=tmp,
                   YARR_KEYSTORE_OUT=f"{tmp}/key.p12", **(env_extra or {}))
        return subprocess.run(["bash", str(SCRIPT)], env=env, capture_output=True, text=True, timeout=120)

    def fingerprint(self, tmp):
        password = Path(tmp, "key-password.txt").read_text().strip()
        out = subprocess.run(["keytool", "-list", "-v", "-keystore", f"{tmp}/key.p12", "-storetype", "PKCS12",
                              "-storepass", password, "-alias", "yarr-media"], capture_output=True, text=True).stdout
        return next(line for line in out.splitlines() if "SHA256:" in line)

    def test_creates_key_stores_secrets_and_never_replaces_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = self.run_script(tmp)
            self.assertEqual(first.returncode, 0, first.stderr)
            for name in ("key.p12", "key-password.txt"):
                self.assertEqual(os.stat(Path(tmp, name)).st_mode & 0o777, 0o600, name)
            secret = base64.b64decode(Path(tmp, "secret-ANDROID_KEYSTORE_BASE64").read_text())
            self.assertEqual(secret, Path(tmp, "key.p12").read_bytes())
            self.assertEqual(Path(tmp, "secret-ANDROID_KEYSTORE_PASSWORD").read_text(),
                             Path(tmp, "key-password.txt").read_text().strip())
            before = self.fingerprint(tmp)
            again = self.run_script(tmp)
            self.assertEqual(again.returncode, 0, again.stderr)
            self.assertIn("never replaced", again.stdout)
            self.assertEqual(self.fingerprint(tmp), before)

    def test_refuses_when_the_password_file_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(self.run_script(tmp).returncode, 0)
            Path(tmp, "key-password.txt").unlink()
            result = self.run_script(tmp)
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue(Path(tmp, "key.p12").exists())


if __name__ == "__main__":
    unittest.main()
