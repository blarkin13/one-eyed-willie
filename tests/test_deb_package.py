"""The .deb builds, and the signed apt repository it is published into is
accepted by apt (signature verified, package found)."""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = all(shutil.which(t) for t in ("dpkg-deb", "apt-ftparchive", "gpg", "apt-get", "apt-cache"))


@unittest.skipUnless(TOOLS, "dpkg-deb, apt-ftparchive, gpg and apt are required")
class DebPackageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def run_ok(self, *cmd, **kw):
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120, **kw)
        self.assertEqual(r.returncode, 0, " ".join(map(str, cmd)) + "\n" + r.stdout + r.stderr)
        return r.stdout

    def test_package_contents_and_signed_repository(self):
        deb = self.run_ok("bash", str(ROOT / "deploy/deb/build.sh"), "9.8.7", str(self.tmp / "out")).strip()
        info = self.run_ok("dpkg-deb", "-f", deb)
        self.assertIn("Package: yarr-media", info)
        self.assertIn("Version: 9.8.7", info)
        self.assertIn("Architecture: all", info)
        files = self.run_ok("dpkg-deb", "-c", deb)
        self.assertIn("./usr/share/yarr-media/install.sh", files)
        self.assertIn("./usr/sbin/yarr-media-setup", files)
        listing = self.run_ok("dpkg-deb", "-c", deb).splitlines()[0]
        self.assertTrue(listing.startswith("drwxr-xr-x"), "package root must not be private: " + listing)

        gnupg = self.tmp / "gnupg"
        gnupg.mkdir(mode=0o700)
        env = {**os.environ, "GNUPGHOME": str(gnupg)}
        self.run_ok("gpg", "--batch", "--passphrase", "", "--quick-gen-key", "Test <t@example>", "ed25519", "sign", "1d", env=env)
        key = self.run_ok("gpg", "--batch", "--armor", "--export-secret-keys", env=env)
        repo = self.tmp / "repo"
        self.run_ok("bash", str(ROOT / "deploy/deb/publish-apt.sh"), str(repo), deb,
                    env={**os.environ, "APT_SIGNING_KEY": key})
        for path in ("yarr-media.gpg", "dists/stable/InRelease", "dists/stable/Release.gpg",
                     "dists/stable/main/binary-amd64/Packages.gz", "dists/stable/main/binary-arm64/Packages",
                     "pool/main/y/yarr-media/yarr-media_9.8.7_all.deb"):
            self.assertTrue((repo / path).is_file(), path)

        # apt itself verifies the signature and sees the package.
        state = self.tmp / "apt"
        for d in ("lists/partial", "cache/archives/partial", "etc/sources.list.d", "etc/preferences.d"):
            (state / d).mkdir(parents=True, exist_ok=True)
        (state / "etc/sources.list").write_text(
            f"deb [signed-by={repo}/yarr-media.gpg] file:{repo} stable main\n")
        opts = ["-o", f"Dir::State::Lists={state}/lists", "-o", f"Dir::Cache={state}/cache",
                "-o", f"Dir::Etc::SourceList={state}/etc/sources.list",
                "-o", f"Dir::Etc::SourceParts={state}/etc/sources.list.d",
                "-o", f"Dir::Etc::Preferences={state}/etc/preferences",
                "-o", f"Dir::Etc::PreferencesParts={state}/etc/preferences.d",
                "-o", "Debug::NoLocking=1", "-o", "APT::Sandbox::User=root"]
        out = self.run_ok("apt-get", *opts, "update")
        self.assertNotIn("NO_PUBKEY", out)
        policy = self.run_ok("apt-cache", *opts, "policy", "yarr-media")
        self.assertIn("9.8.7", policy)

        # A repository signed by another key is rejected.
        (repo / "yarr-media.gpg").write_bytes(b"")
        shutil.rmtree(state / "lists")
        (state / "lists/partial").mkdir(parents=True)
        bad = subprocess.run(["apt-get", *opts, "update"], capture_output=True, text=True, timeout=120)
        self.assertTrue(bad.returncode != 0 or "NO_PUBKEY" in bad.stdout + bad.stderr
                        or "not signed" in bad.stdout + bad.stderr or "signature" in (bad.stdout + bad.stderr).lower(),
                        bad.stdout + bad.stderr)


if __name__ == "__main__":
    unittest.main()
