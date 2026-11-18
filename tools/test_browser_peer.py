"""Run Yarr's isolated WebRTC transfer in a real Chromium browser.

This checks the actual JavaScript test page, signaling request, encrypted
data channel, integrity verification and teardown. Only localhost is used.
"""
import os
import secrets
import socket
import subprocess
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

PORT = 18979
URL = f"http://127.0.0.1:{PORT}/probe"


def await_ready(process):
    for _ in range(80):
        if process.poll() is not None:
            raise RuntimeError("Probe server exited before startup")
        try:
            with urllib.request.urlopen(URL, timeout=0.3) as response:
                if response.status == 200:
                    return
        except OSError:
            time.sleep(0.125)
    raise TimeoutError("Probe server did not start")


def main():
    token = secrets.token_urlsafe(48)
    env = {**os.environ, "YARR_DIRECT_PROBE_TOKEN": token}
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "tools.direct_peer_probe:app",
         "--host", "127.0.0.1", "--port", str(PORT), "--no-access-log"],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )
    try:
        await_ready(process)
        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--use-fake-ui-for-media-stream"],
            )
            try:
                page = browser.new_page()
                failures = []
                page.on("pageerror", lambda error: failures.append(str(error)))
                page.goto(URL, wait_until="domcontentloaded")
                page.locator("#token").fill(token)
                page.locator("#start").click()
                try:
                    page.wait_for_function(
                        "() => { const text = document.querySelector('#result').textContent; "
                        "return text.includes('Verified:') || text.includes('FAILED:'); }",
                        timeout=45000,
                    )
                except Exception:
                    print("Browser output at timeout:", page.locator("#result").inner_text(), flush=True)
                    print("Browser JS errors:", failures, flush=True)
                    raise
                result = page.locator("#result").inner_text()
                print("Browser output:", result, flush=True)
                assert "Verified: 1048576 bytes of correct data." in result, result
                assert "SHA-256:" in result, result
                assert "ICE candidate types:" in result or "candidate pair not available" in result, result
                assert "FAILED:" not in result, result
                assert not failures, failures
                print("PASS: Chromium negotiated WebRTC and validated 1 MiB RTCDataChannel transfer")
                print("ICE information:", next(
                    (line for line in result.splitlines() if line.startswith("ICE ")),
                    "not reported"
                ))
            finally:
                browser.close()
    finally:
        process.terminate()
        try:
            process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()


if __name__ == "__main__":
    main()
