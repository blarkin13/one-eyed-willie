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
        self.assertIn("temp_file+independent_segments", command)
        self.assertIn("-hls_playlist_type", command)
        self.assertEqual(command[command.index("-hls_playlist_type") + 1], "event")
        self.assertEqual(command[command.index("-hls_list_size") + 1], "0")
        self.assertIn("-readrate", command)
        self.assertNotIn("-re", command)
        self.assertIn("libx264", command)
        self.assertNotIn("h264_vaapi", command)
        gpu = hls._command(self.video, folder, 20, True)
        self.assertIn("h264_vaapi", gpu)
        self.assertIn("-vaapi_device", gpu)
        self.assertIn("pad=1280:720:(ow-iw)/2:(oh-ih)/2,format=nv12,hwupload",
                      gpu[gpu.index("-vf") + 1])
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
            self.assertEqual(info["engine"], "Intel VAAPI encode")
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

    def test_quality_presets_change_resolution_and_bitrate_only(self):
        folder = self.root / "temp"
        base = hls._command(self.video, folder, 0)
        self.assertEqual(base, hls._command(self.video, folder, 0, False, "720p"))
        high = hls._command(self.video, folder, 0, False, "1080p")
        low = hls._command(self.video, folder, 0, False, "480p")
        self.assertIn("pad=1920:1080", high[high.index("-vf") + 1])
        self.assertIn("pad=854:480", low[low.index("-vf") + 1])
        self.assertEqual(high[high.index("-maxrate") + 1], "8000k")
        self.assertEqual(low[low.index("-maxrate") + 1], "1600k")
        self.assertEqual(high[high.index("-crf") + 1], "23")
        # Segmenting and seekability settings must not vary with quality.
        for command in (high, low):
            self.assertEqual(command[command.index("-hls_time") + 1], "4")
            self.assertEqual(command[command.index("-hls_playlist_type") + 1], "event")
        gpu = hls._command(self.video, folder, 0, True, "1080p")
        self.assertEqual(gpu[gpu.index("-b:v") + 1], "6000k")
        self.assertIn("pad=1920:1080", gpu[gpu.index("-vf") + 1])

    def test_unknown_quality_falls_back_and_session_reports_quality(self):
        self.assertEqual(hls.normalize_quality("4k; rm -rf /"), "720p")
        self.assertEqual(hls.normalize_quality(None), "720p")
        self.assertEqual(hls.normalize_quality("480p"), "480p")
        with patch.object(hls, "_item", return_value=({"id": 1}, self.video)), \
             patch.object(hls, "hardware_available", return_value=False), \
             patch.object(hls, "probe_duration", return_value=150), \
             patch.object(hls.subprocess, "Popen", return_value=FakeProcess()) as popen:
            info = hls.start_hls(1, 0, "480p")
            self.assertEqual(info["quality"], "480p")
            self.assertEqual(hls.stream_status(info["session"])["quality"], "480p")
            self.assertIn("pad=854:480", popen.call_args.args[0][popen.call_args.args[0].index("-vf") + 1])
        self.assertEqual(hls.list_qualities()["default"], "720p")
        self.assertEqual([q["id"] for q in hls.list_qualities()["qualities"]],
                         ["1080p", "720p", "480p", "360p"])

    def test_fallback_keeps_the_selected_quality(self):
        gpu = FakeProcess()
        gpu.stopped = True
        with patch.object(hls, "_item", return_value=({"id": 1}, self.video)), \
             patch.object(hls, "hardware_available", return_value=True), \
             patch.object(hls, "probe_duration", return_value=150), \
             patch.object(hls.subprocess, "Popen", side_effect=[gpu, FakeProcess()]) as popen:
            info = hls.start_hls(1, 0, "1080p")
            hls.stream_status(info["session"])
        command = popen.call_args.args[0]
        self.assertIn("libx264", command)
        self.assertIn("pad=1920:1080", command[command.index("-vf") + 1])

    def test_stale_session_is_reclaimed_but_busy_ones_are_not(self):
        processes = [FakeProcess(), FakeProcess(), FakeProcess()]
        with patch.object(hls, "_item", return_value=({"id": 1}, self.video)), \
             patch.object(hls, "hardware_available", return_value=False), \
             patch.object(hls, "probe_duration", return_value=150), \
             patch.object(hls.subprocess, "Popen", side_effect=processes):
            first = hls.start_hls(1, 0)["session"]
            second = hls.start_hls(1, 0)["session"]
            with self.assertRaises(HTTPException) as busy:
                hls.start_hls(1, 0)          # both sessions are fresh
            self.assertEqual(busy.exception.status_code, 429)
            hls.ACTIVE[first].last_access -= hls.RECLAIM_IDLE_SECONDS + 5   # abandoned
            third = hls.start_hls(1, 0)["session"]
        self.assertNotIn(first, hls.ACTIVE)
        self.assertTrue(processes[0].stopped)
        self.assertIn(second, hls.ACTIVE)
        self.assertIn(third, hls.ACTIVE)
        self.assertFalse(processes[1].stopped)

    def test_transcoder_failure_reports_ffmpeg_reason(self):
        dead = FakeProcess()
        dead.stopped = True
        with patch.object(hls, "_item", return_value=({"id": 1}, self.video)), \
             patch.object(hls, "hardware_available", return_value=False), \
             patch.object(hls, "probe_duration", return_value=150), \
             patch.object(hls.subprocess, "Popen", return_value=dead):
            token = hls.start_hls(1, 0)["session"]
        (self.root / "hls" / token / hls.LOG_NAME).write_text(
            "noise\nUnsupported codec: truehd in this build\n")
        with self.assertRaises(HTTPException) as error:
            hls.stream_status(token)
        self.assertEqual(error.exception.status_code, 422)
        self.assertIn("Unsupported codec: truehd", error.exception.detail)
        # The log is never served as a stream file.
        with self.assertRaises(HTTPException):
            hls.stream_file(token, hls.LOG_NAME)

    def test_invalid_id_does_not_serve_file(self):
        with self.assertRaises(HTTPException) as err:
            hls.stream_status("bad")
        self.assertEqual(err.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
