"""Downloads for offline use: Pro only, phone-ready MP4s, resumable, shared viewers limited."""
import json
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from server import barnacle_access, downloads, hls, library, yarr_pairing
from server.viewer import Viewer, use, reset

FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")


def make_video(path, codec="libx264", audio="aac", seconds=2):
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([FFMPEG, "-loglevel", "error", "-y", "-f", "lavfi", "-i", f"testsrc=size=640x360:rate=24:duration={seconds}",
                    "-f", "lavfi", "-i", f"sine=duration={seconds}", "-c:v", codec, "-pix_fmt", "yuv420p",
                    "-c:a", audio, "-shortest", str(path)], check=True)


@unittest.skipUnless(FFMPEG and FFPROBE, "ffmpeg required")
class DownloadsTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        media = root / "media"
        self.movies = media / "Movies"
        self.mp4 = self.movies / "Easy (2020)" / "Easy (2020).mp4"
        self.mkv = self.movies / "Remux (2021)" / "Remux (2021).mkv"
        make_video(self.mp4)
        make_video(self.mkv, audio="ac3")
        patches = [patch.object(library, "DB_PATH", root / "db.sqlite3"), patch.object(library, "MEDIA_ROOT", media),
                   patch("server.playback.MEDIA_ROOT", media), patch.object(downloads, "ROOT", root / "downloads"),
                   patch.object(hls, "FFMPEG", FFMPEG), patch.object(hls, "hardware_available", return_value=False),
                   patch.object(yarr_pairing, "pro_state", side_effect=lambda: dict(self.pro))]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        (root / "downloads").mkdir()
        self.pro = {"paired": True, "owner_pro": True}
        created = library.create_library(library.LibraryRequest(name="Movies", kind="movies", path=str(self.movies), icon="reel"))
        library.scan_library(created["id"])
        self.library_id = created["id"]
        with library.db() as conn:
            ids = {Path(r["path"]).suffix: r["id"] for r in conn.execute("SELECT id,path FROM media")}
        self.mp4_id, self.mkv_id = ids[".mp4"], ids[".mkv"]
        app = FastAPI()
        app.include_router(downloads.router)
        self.client = TestClient(app)

    def run_queue(self):
        with library.db() as conn:
            for row in conn.execute("SELECT id FROM download_jobs WHERE status='queued'").fetchall():
                downloads._run(row["id"])

    def test_pro_is_required(self):
        self.pro = {"paired": False, "owner_pro": False}
        self.assertEqual(self.client.get("/api/downloads/status").json(), {"allowed": False, "reason": "not_connected"})
        self.pro = {"paired": True, "owner_pro": False}
        self.assertEqual(self.client.get("/api/downloads/status").json()["reason"], "pro_required")
        self.assertEqual(self.client.post(f"/api/downloads/prepare/{self.mp4_id}?quality=original").status_code, 403)
        options = self.client.get(f"/api/downloads/options/{self.mp4_id}").json()
        self.assertEqual((options["allowed"], options["reason"]), (False, "pro_required"))

    def test_original_phone_ready_file_is_served_as_is_and_resumes(self):
        job = self.client.post(f"/api/downloads/prepare/{self.mp4_id}?quality=original").json()
        self.assertEqual(job["status"], "ready")
        self.assertEqual(job["bytes"], self.mp4.stat().st_size)
        whole = self.client.get(job["file_url"])
        self.assertEqual(whole.content, self.mp4.read_bytes())
        part = self.client.get(job["file_url"], headers={"Range": "bytes=100-"})
        self.assertEqual(part.status_code, 206)
        self.assertEqual(part.content, self.mp4.read_bytes()[100:])
        self.assertEqual(self.client.post(f"/api/downloads/prepare/{self.mp4_id}?quality=original").json()["id"], job["id"],
                         "the same title and quality reuse one prepared file")

    def probe(self, path):
        out = subprocess.run([FFPROBE, "-v", "error", "-show_entries", "stream=codec_type,codec_name,height",
                              "-of", "json", str(path)], capture_output=True, text=True, check=True).stdout
        return {s["codec_type"]: s for s in json.loads(out)["streams"]}

    def test_original_mkv_is_remuxed_with_phone_audio(self):
        job = self.client.post(f"/api/downloads/prepare/{self.mkv_id}?quality=original").json()
        self.assertEqual(job["status"], "queued")
        self.assertEqual(self.client.get(f"/api/downloads/jobs/{job['id']}/file").status_code, 409)
        self.run_queue()
        done = self.client.get(f"/api/downloads/jobs/{job['id']}").json()
        self.assertEqual((done["status"], done["progress"]), ("ready", 1))
        streams = self.probe(downloads._done(job["id"]))
        self.assertEqual((streams["video"]["codec_name"], streams["audio"]["codec_name"]), ("h264", "aac"))
        self.assertTrue(self.mkv.is_file(), "the original is never changed")

    def test_smaller_quality_is_converted(self):
        job = self.client.post(f"/api/downloads/prepare/{self.mp4_id}?quality=240p").json()
        self.assertEqual(self.client.post(f"/api/downloads/prepare/{self.mp4_id}?quality=240p").status_code, 422)
        job = self.client.post(f"/api/downloads/prepare/{self.mp4_id}?quality=360p").json()
        self.run_queue()
        self.assertEqual(self.client.get(f"/api/downloads/jobs/{job['id']}").json()["status"], "ready")
        self.assertEqual(self.probe(downloads._done(job["id"]))["video"]["height"], 360)
        options = self.client.get(f"/api/downloads/options/{self.mp4_id}").json()
        self.assertEqual([o["quality"] for o in options["options"]], ["original", "1080p", "720p", "480p", "360p"])
        self.assertTrue(all(o["bytes"] > 0 for o in options["options"]))

    def test_shared_viewers_only_get_their_libraries(self):
        job = self.client.post(f"/api/downloads/prepare/{self.mp4_id}?quality=original").json()
        stranger = Viewer(id="u:x", role="barnacle", name="X", libraries=(self.library_id + 99,))
        token = use(stranger)
        try:
            self.assertEqual(self.client.get(f"/api/downloads/jobs/{job['id']}").status_code, 404)
        finally:
            reset(token)
        friend = Viewer(id="u:y", role="barnacle", name="Y", libraries=(self.library_id,))
        self.assertTrue(barnacle_access.allowed(friend, "POST", f"/api/downloads/prepare/{self.mp4_id}", {"quality": ["720p"]}))
        self.assertTrue(barnacle_access.allowed(friend, "GET", f"/api/downloads/jobs/{job['id']}/file", {}))
        self.assertFalse(barnacle_access.allowed(friend, "DELETE", f"/api/downloads/jobs/{job['id']}", {}))

    def test_old_prepared_copies_are_removed(self):
        job = self.client.post(f"/api/downloads/prepare/{self.mkv_id}?quality=original").json()
        self.run_queue()
        self.assertTrue(downloads._done(job["id"]).is_file())
        self.assertEqual(downloads.cleanup(now=time.time() + downloads.KEEP_SECONDS + 10), 1)
        self.assertFalse(downloads._done(job["id"]).exists())
        self.assertTrue(self.mkv.is_file())


class ProStatusFromHeartbeatTests(unittest.TestCase):
    def test_heartbeat_reply_sets_owner_pro(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        state = {"status": "paired", "poll_secret": "s" * 40}
        with patch.object(yarr_pairing, "_read", side_effect=lambda: dict(state)), \
             patch.object(yarr_pairing, "_save", side_effect=state.update), \
             patch.object(yarr_pairing, "_library_list", return_value=[]), \
             patch.object(yarr_pairing, "_cloud", return_value={"status": "accepted", "owner_pro": True}):
            yarr_pairing.report_heartbeat()
            self.assertEqual(yarr_pairing.pro_state(), {"paired": True, "owner_pro": True})
        with patch.object(yarr_pairing, "_read", side_effect=lambda: dict(state)), \
             patch.object(yarr_pairing, "_save", side_effect=state.update), \
             patch.object(yarr_pairing, "_library_list", return_value=[]), \
             patch.object(yarr_pairing, "_cloud", return_value={"status": "accepted", "owner_pro": False}):
            yarr_pairing.report_heartbeat()
            self.assertEqual(yarr_pairing.pro_state()["owner_pro"], False)


if __name__ == "__main__":
    unittest.main()
