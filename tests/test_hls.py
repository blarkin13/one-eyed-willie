import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from server import hls


class FakeProcess:
    def __init__(self):
        self.stopped = False
    def poll(self):
        return -15 if self.stopped else None
    def terminate(self):
        self.stopped = True
    def wait(self, timeout=None):
        return -15
    def kill(self):
        self.stopped = True


class HLSTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.video = self.root / "movie.mkv"
        self.video.write_bytes(b"fake")
        self.patch_root = patch.object(hls, "ROOT", self.root / "hls")
        self.patch_root.start()
        self.addCleanup(self.patch_root.stop)
        # CI does not have FFmpeg installed until Docker build; mock process
        # creation while using a known executable for the availability guard.
        executable = patch.object(hls, "FFMPEG", "/bin/true")
        executable.start()
        self.addCleanup(executable.stop)
        with hls.LOCK:
            hls.ACTIVE.clear()
        self.addCleanup(lambda: hls.ACTIVE.clear())

    def test_encoder_command_is_sandboxed_and_contains_hls_settings(self):
        folder = self.root / "temp"
        command = hls._command(self.video, folder, 20)
        self.assertIn("-hls_time", command)
        self.assertIn("4", command)
        self.assertIn("delete_segments+temp_file+independent_segments", command)
        self.assertIn("libx264", command)
        self.assertNotIn("h264_vaapi", command)
        gpu = hls._command(self.video, folder, 20, True)
        self.assertIn("h264_vaapi", gpu)
        self.assertIn("-hwaccel", gpu)
        self.assertEqual(gpu[gpu.index("-hwaccel")+1], "vaapi")
        self.assertIn("-hwaccel_output_format", gpu)
        self.assertIn("scale_vaapi=w=1280:h=720:force_original_aspect_ratio=decrease:force_divisible_by=2:format=nv12", gpu)
        self.assertNotIn("libx264", gpu)

    def test_vaapi_failure_restarts_with_software(self):
        gpu = FakeProcess()
        gpu.stopped = True
        software = FakeProcess()
        with patch.object(hls, "_item", return_value=({"id": 1}, self.video)), \
             patch.object(hls, "hardware_available", return_value=True), \
             patch.object(hls, "probe_duration", return_value=150), \
             patch.object(hls.subprocess, "Popen", side_effect=[gpu, software]) as popen:
            info = hls.start_hls(1, 0)
            self.assertEqual(info["engine"], "Intel VAAPI decode + encode")
            data = hls.stream_status(info["session"])
        self.assertEqual(data["engine"], "CPU fallback")
        self.assertEqual(popen.call_count, 2)
        self.assertIn("libx264", popen.call_args.args[0])

    def test_session_start_status_segment_and_stop(self):
        process = FakeProcess()
        with patch.object(hls, "_item", return_value=({"id": 1}, self.video)), \
             patch.object(hls, "hardware_available", return_value=False), \
             patch.object(hls, "probe_duration", return_value=150), \
             patch.object(hls.subprocess, "Popen", return_value=process):
            info = hls.start_hls(1, 0)
        token = info["session"]
        self.assertEqual(info["engine"], "CPU")
        self.assertTrue(info["playlist"].endswith("/index.m3u8"))
        self.assertFalse(hls.stream_status(token)["ready"])
        folder = self.root / "hls" / token
        (folder / "index.m3u8").write_text("#EXTM3U\n")
        (folder / "segment_000000.ts").write_bytes(b"segment")
        self.assertTrue(hls.stream_status(token)["ready"])
        response = hls.stream_file(token, "segment_000000.ts")
        self.assertEqual(response.media_type, "video/mp2t")
        with self.assertRaises(HTTPException):
            hls.stream_file(token, "../secret")
        with self.assertRaises(HTTPException):
            hls.stream_file(token, "index.m3u8.tmp")
        hls.stop_hls(token)
        self.assertTrue(process.stopped)
        self.assertFalse(folder.exists())

    def test_rejects_more_than_two_concurrent_sessions(self):
        processes = [FakeProcess(), FakeProcess()]
        with patch.object(hls, "_item", return_value=({"id": 1}, self.video)), \
             patch.object(hls, "hardware_available", return_value=False), \
             patch.object(hls, "probe_duration", return_value=150), \
             patch.object(hls.subprocess, "Popen", side_effect=processes):
            hls.start_hls(1, 0)
            hls.start_hls(1, 0)
            with self.assertRaises(HTTPException) as error:
                hls.start_hls(1, 0)
        self.assertEqual(error.exception.status_code, 429)

    def test_idle_sessions_are_cleaned(self):
        process = FakeProcess()
        with patch.object(hls, "_item", return_value=({"id": 1}, self.video)), \
             patch.object(hls, "hardware_available", return_value=False), \
             patch.object(hls, "probe_duration", return_value=150), \
             patch.object(hls.subprocess, "Popen", return_value=process):
            result = hls.start_hls(1, 0)
        session = hls.ACTIVE[result["session"]]
        with hls.LOCK:
            hls._purge(session.last_access+hls.IDLE_SECONDS+1)
        self.assertTrue(process.stopped)
        self.assertFalse(hls.ACTIVE)

    def test_invalid_id_does_not_serve_file(self):
        with self.assertRaises(HTTPException) as err:
            hls.stream_status("bad")
        self.assertEqual(err.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
