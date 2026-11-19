"""Remote requests need a valid Yarr pass; LAN requests are unchanged."""
import base64
import json
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient

from server import remote_access as ra

ROOT = Path(__file__).resolve().parents[1]
SERVER = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def b64(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


class Keys:
    def __init__(self, mapping):
        self._keys = mapping
        self.refreshed = 0

    def get(self, kid):
        return self._keys.get(kid)

    def refresh(self):
        self.refreshed += 1


def make_pass(key, kid="k1", **overrides):
    now = int(time.time())
    claims = {"v": 1, "iss": ra.ACCOUNT_SITE, "aud": SERVER, "sub": "user-1", "role": "owner",
              "dev": None, "iat": now, "exp": now + 3600, "jti": "x"}
    claims.update(overrides)
    head = b64(json.dumps({"alg": "EdDSA", "typ": "yarr-pass", "kid": kid}).encode())
    body = b64(json.dumps(claims).encode())
    return head + "." + body + "." + b64(key.sign((head + "." + body).encode()))


def app_with(keys):
    app = FastAPI()

    @app.get("/")
    def home():
        return {"page": "home"}

    @app.get("/api/watch/1/stream")
    def stream():
        return StreamingResponse(iter([b"abc", b"def"]), media_type="video/mp4")

    @app.get("/health")
    def health():
        return {"status": "ok"}

    app.add_middleware(ra.RemotePassMiddleware, keys=keys, server_id=SERVER)
    return TestClient(app, base_url="https://home.example.net")


REMOTE = {"X-Yarr-Remote": "1"}


class VerifyTests(unittest.TestCase):
    def setUp(self):
        self.key = Ed25519PrivateKey.generate()
        self.keys = Keys({"k1": self.key.public_key()})

    def check(self, token):
        return ra.verify_pass(token, keys=self.keys, server_id=SERVER)

    def test_valid_pass(self):
        self.assertEqual(self.check(make_pass(self.key))["sub"], "user-1")

    def test_refusals(self):
        other = Ed25519PrivateKey.generate()
        cases = {
            "bad_signature": make_pass(other),
            "unknown_key": make_pass(self.key, kid="nope"),
            "expired": make_pass(self.key, exp=int(time.time()) - 1),
            "wrong_server": make_pass(self.key, aud="another-server"),
            "wrong_issuer": make_pass(self.key, iss="https://evil.example"),
            "not_allowed": make_pass(self.key, role="guest"),
            "bad_lifetime": make_pass(self.key, exp=int(time.time()) + 3 * 86400),
            "malformed": "a.b",
        }
        for reason, token in cases.items():
            with self.subTest(reason=reason), self.assertRaises(ra.PassError) as raised:
                self.check(token)
            self.assertEqual(str(raised.exception), reason)
        # Tampering with the claims breaks the signature.
        head, body, sig = make_pass(self.key).split(".")
        forged = json.loads(base64.urlsafe_b64decode(body + "=="))
        forged["aud"] = SERVER
        forged["sub"] = "attacker"
        with self.assertRaises(ra.PassError):
            self.check(head + "." + b64(json.dumps(forged).encode()) + "." + sig)


class MiddlewareTests(unittest.TestCase):
    def setUp(self):
        self.key = Ed25519PrivateKey.generate()
        self.keys = Keys({"k1": self.key.public_key()})
        self.client = app_with(self.keys)

    def test_lan_requests_are_untouched(self):
        self.assertEqual(self.client.get("/").json(), {"page": "home"})
        self.assertEqual(self.client.get("/api/watch/1/stream").content, b"abcdef")

    def test_remote_without_pass_is_refused(self):
        api = self.client.get("/api/watch/1/stream", headers=REMOTE)
        self.assertEqual(api.status_code, 401)
        self.assertEqual(api.json()["error"], "remote_pass_required")
        page = self.client.get("/movies?x=1", headers={**REMOTE, "Accept": "text/html"}, follow_redirects=False)
        self.assertEqual(page.status_code, 303)
        self.assertEqual(page.headers["location"],
                         "https://accounts.yarr.media/remote/open?server=" + SERVER + "&return=%2Fmovies%3Fx%3D1")
        self.assertEqual(self.client.get("/health", headers=REMOTE).status_code, 200)

    def test_header_pass_streams(self):
        r = self.client.get("/api/watch/1/stream", headers={**REMOTE, "Authorization": "Yarr-Pass " + make_pass(self.key)})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.content, b"abcdef")

    def test_start_sets_cookie_then_cookie_works(self):
        r = self.client.get("/remote/start", params={"pass": make_pass(self.key), "return": "/movies"},
                            headers=REMOTE, follow_redirects=False)
        self.assertEqual(r.status_code, 303)
        self.assertEqual(r.headers["location"], "/movies")
        cookie = r.headers["set-cookie"]
        for part in ("yarr_pass=", "HttpOnly", "Secure", "SameSite=Lax", "Max-Age="):
            self.assertIn(part, cookie)
        self.assertEqual(self.client.get("/", headers=REMOTE).json(), {"page": "home"})

    def test_start_refuses_bad_pass_and_open_redirects(self):
        bad = self.client.get("/remote/start", params={"pass": "x.y.z"}, headers=REMOTE, follow_redirects=False)
        self.assertEqual(bad.status_code, 403)
        r = self.client.get("/remote/start", params={"pass": make_pass(self.key), "return": "//evil.example"},
                            headers=REMOTE, follow_redirects=False)
        self.assertEqual(r.headers["location"], "/")

    def test_unknown_key_triggers_one_refresh(self):
        token = make_pass(self.key, kid="rotated")
        r = self.client.get("/", headers={**REMOTE, "Authorization": "Yarr-Pass " + token})
        self.assertEqual(r.status_code, 401)
        self.assertEqual(self.keys.refreshed, 1)

    def test_remote_hosts_setting(self):
        with patch.dict("os.environ", {"YARR_REMOTE_HOSTS": "home.example.net"}):
            self.assertEqual(self.client.get("/").status_code, 401)


class KeyStoreTests(unittest.TestCase):
    def test_downloaded_keys_are_cached_on_disk(self):
        key = Ed25519PrivateKey.generate().public_key()
        raw = key.public_bytes_raw()
        doc = {"keys": [{"kty": "OKP", "crv": "Ed25519", "x": b64(raw), "kid": "k9"},
                        {"kty": "RSA", "kid": "ignored"}]}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "keys.json"
            store = ra.KeyStore(path=path, fetch=lambda: doc)
            self.assertIsNotNone(store.get("k9"))
            self.assertIsNone(store._keys.get("ignored"))
            reloaded = ra.KeyStore(path=path, fetch=lambda: (_ for _ in ()).throw(OSError("offline")))
            self.assertEqual(reloaded._keys["k9"].public_bytes_raw(), raw)


APP = "https://app.yarr.media"


class AppCorsTests(unittest.TestCase):
    """app.yarr.media runs in the browser and talks to this server directly."""

    def setUp(self):
        self.key = Ed25519PrivateKey.generate()
        self.client = app_with(Keys({"k1": self.key.public_key()}))

    def test_preflight_is_answered_without_a_pass(self):
        r = self.client.options("/api/watch/1/stream", headers={**REMOTE, "Origin": APP,
                                "Access-Control-Request-Method": "GET",
                                "Access-Control-Request-Headers": "authorization, range"})
        self.assertEqual(r.status_code, 204)
        self.assertEqual(r.headers["access-control-allow-origin"], APP)
        self.assertIn("authorization", r.headers["access-control-allow-headers"])
        self.assertIn("range", r.headers["access-control-allow-headers"])

    def test_responses_and_refusals_carry_cors_headers_for_the_app_only(self):
        ok = self.client.get("/api/watch/1/stream", headers={**REMOTE, "Origin": APP,
                             "Authorization": "Yarr-Pass " + make_pass(self.key)})
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.content, b"abcdef")
        self.assertEqual(ok.headers["access-control-allow-origin"], APP)
        self.assertIn("content-range", ok.headers["access-control-expose-headers"])
        refused = self.client.get("/", headers={**REMOTE, "Origin": APP, "Accept": "text/html"}, follow_redirects=False)
        self.assertEqual(refused.status_code, 401, "the app gets a status it can read, not a redirect")
        self.assertEqual(refused.headers["access-control-allow-origin"], APP)
        other = self.client.options("/", headers={**REMOTE, "Origin": "https://evil.example",
                                    "Access-Control-Request-Method": "GET"})
        self.assertNotIn("access-control-allow-origin", other.headers)
        self.assertEqual(other.status_code, 401, "other sites still need a pass and get no CORS")


class KeyRefreshRaceTests(unittest.TestCase):
    def test_a_pass_on_first_visit_waits_for_the_running_download(self):
        """A fresh server starts a background key download; the pass check that
        arrives meanwhile must wait for it rather than report unknown_key."""
        import threading
        key = Ed25519PrivateKey.generate()
        raw = key.public_key().public_bytes_raw()
        started = threading.Event()

        def slow_fetch():
            started.set()
            time.sleep(0.3)
            return {"keys": [{"kty": "OKP", "crv": "Ed25519", "x": b64(raw), "kid": "k1"}]}

        with tempfile.TemporaryDirectory() as folder:
            store = ra.KeyStore(path=Path(folder) / "keys.json", fetch=slow_fetch)
            background = threading.Thread(target=store.refresh)
            background.start()
            started.wait(2)
            store.refresh()  # throttled, but must not return before the download lands
            claims = ra.verify_pass(make_pass(key), keys=ra._NonBlocking(store), server_id=SERVER)
            background.join()
        self.assertEqual(claims["aud"], SERVER)


class WiringTests(unittest.TestCase):
    def test_real_app_installs_the_gate_and_caddy_marks_remote(self):
        from server.main import app
        self.assertIn(ra.RemotePassMiddleware, [m.cls for m in app.user_middleware])
        caddy = (ROOT / "deploy/Caddyfile.remote").read_text()
        self.assertIn("header_up X-Yarr-Remote 1", caddy)
        self.assertNotIn("basic_auth", caddy, "the Yarr pass replaces the setup password")
        self.assertNotIn("app.yarr.media", "".join(l for l in caddy.splitlines() if not l.strip().startswith("#")))


@unittest.skipUnless(shutil.which("node"), "node is needed to run the account Worker")
class WorkerInteropTests(unittest.TestCase):
    def test_a_pass_from_the_real_worker_is_accepted(self):
        out = subprocess.run(["node", "--no-warnings", str(ROOT / "cloudflare/yarr/test/issue-pass-cli.mjs"), SERVER],
                             capture_output=True, text=True, timeout=60, check=True)
        data = json.loads(out.stdout)
        keys = ra.KeyStore(path=Path(tempfile.mkdtemp()) / "k.json", fetch=lambda: data["keys"])
        keys.refresh()
        claims = ra.verify_pass(data["pass"], keys=keys, server_id=SERVER)
        self.assertEqual(claims["aud"], SERVER)
        with self.assertRaises(ra.PassError):
            ra.verify_pass(data["pass"], keys=keys, server_id="different-server")


if __name__ == "__main__":
    unittest.main()
