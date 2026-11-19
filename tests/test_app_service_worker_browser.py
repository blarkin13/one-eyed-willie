"""app.yarr.media end to end: the real Worker (starter page + service worker) on
one origin, a real server with the remote-pass gate on another. The page must
load from the server through the service worker, keep its own address, and get
partial video ranges straight from the server."""
import json
import os
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
try:  # pragma: no cover - environment dependent
    from playwright.sync_api import sync_playwright
except Exception:  # pragma: no cover
    sync_playwright = None
CHROME = next((p for p in (
    os.environ.get("CHROME_BIN"), shutil.which("google-chrome"),
    shutil.which("google-chrome-stable"), shutil.which("chromium"),
    shutil.which("chromium-browser")) if p), None)
IDENTITY = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
VIDEO = bytes(range(256)) * 64


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def home_server(keys_doc, app_origin):
    from fastapi import FastAPI, Request
    from fastapi.responses import HTMLResponse, Response
    from server import remote_access as ra

    app = FastAPI()
    seen = {"auth": []}

    @app.get("/", response_class=HTMLResponse)
    def index():
        return ("<!doctype html><title>Home server</title><h1 id='h'>Your library</h1><p id='data'>loading</p>"
                "<script>fetch('/api/data').then(r=>r.json()).then(j=>document.getElementById('data').textContent=j.title)</script>")

    @app.get("/api/data")
    def data(request: Request):
        seen["auth"].append(request.headers.get("authorization", "")[:10])
        return {"title": "Sealab 2021"}

    @app.get("/api/watch/1/stream")
    def stream(request: Request):
        start, end = 0, len(VIDEO) - 1
        rng = request.headers.get("range", "")
        if rng.startswith("bytes="):
            a, _, b = rng[6:].partition("-")
            start, end = int(a), int(b or end)
            return Response(VIDEO[start:end + 1], status_code=206, media_type="video/mp4",
                            headers={"content-range": f"bytes {start}-{end}/{len(VIDEO)}", "accept-ranges": "bytes"})
        return Response(VIDEO, media_type="video/mp4", headers={"accept-ranges": "bytes"})

    keys = ra.KeyStore(path=Path(tempfile.mkdtemp()) / "keys.json", fetch=lambda: keys_doc)
    keys.refresh()
    app.add_middleware(ra.RemotePassMiddleware, keys=keys, server_id=IDENTITY)
    return app, seen


@unittest.skipUnless(sync_playwright and CHROME and shutil.which("node"), "Playwright, Chrome and node are required")
class AppServiceWorkerBrowserTests(unittest.TestCase):
    def test_app_loads_from_the_owners_server_through_the_service_worker(self):
        import uvicorn
        from server import remote_access as ra

        app_port, server_port = free_port(), free_port()
        app_origin = f"http://localhost:{app_port}"
        server_origin = f"http://127.0.0.1:{server_port}"
        worker = subprocess.Popen(["node", "--no-warnings", str(ROOT / "cloudflare/yarr/test/serve-app.mjs"),
                                   str(app_port), server_origin, IDENTITY],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.addCleanup(lambda: (worker.kill(), worker.wait(5), worker.stdout.close(), worker.stderr.close()))
        ready = json.loads(worker.stdout.readline())

        app, seen = home_server(ready["keys"], app_origin)
        config = uvicorn.Config(app, host="127.0.0.1", port=server_port, log_level="warning")
        server = uvicorn.Server(config)
        thread = threading.Thread(target=server.run, daemon=True)
        env = patch.dict(os.environ, {"YARR_REMOTE_HOSTS": "127.0.0.1"})
        origins = patch.object(ra, "APP_ORIGINS", {app_origin})
        env.start(); origins.start()
        self.addCleanup(env.stop); self.addCleanup(origins.stop)
        thread.start()
        self.addCleanup(lambda: setattr(server, "should_exit", True))
        for _ in range(100):
            if server.started:
                break
            time.sleep(0.05)

        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
            context = browser.new_context()
            context.add_cookies([{"name": "__Secure-yarr_session", "value": ready["cookie"],
                                  "domain": "localhost", "path": "/", "secure": True, "httpOnly": True}])
            page = context.new_page()
            page.goto(app_origin + "/")
            page.wait_for_selector("#data:has-text('Sealab 2021')", timeout=15000)
            self.assertEqual(page.title(), "Home server")
            self.assertTrue(page.url.startswith(app_origin), "the address stays on the app site")

            ranged = page.evaluate("""async () => {
                const r = await fetch('/api/watch/1/stream', {headers: {Range: 'bytes=10-19'}});
                const b = new Uint8Array(await r.arrayBuffer());
                return {status: r.status, range: r.headers.get('content-range'), bytes: Array.from(b)};
            }""")
            self.assertEqual(ranged["status"], 206)
            self.assertEqual(ranged["range"], f"bytes 10-19/{len(VIDEO)}")
            self.assertEqual(ranged["bytes"], list(range(10, 20)))

            # A later navigation inside the app is served from the server as well.
            page.goto(app_origin + "/")
            page.wait_for_selector("#data:has-text('Sealab 2021')", timeout=15000)
            browser.close()
        self.assertTrue(seen["auth"] and all(a == "Yarr-Pass " for a in seen["auth"]),
                        "every request reached the server with a pass")


if __name__ == "__main__":
    unittest.main()
