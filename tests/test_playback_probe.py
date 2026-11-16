"""Playback capability probing remains read-only and cache-safe."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock

from server.media_probe import inspect_media, _inspect
from server.hardware import hardware_supported


class PlaybackProbeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.file = Path(self.tmp.name) / "episode.mkv"
        self.file.write_bytes(b"first")
        _inspect.cache_clear()

    def test_actual_video_and_audio_codecs_are_cached_per_file_revision(self):
        payload = {
            "format": {"duration": "2411.12", "bit_rate": "8200000"},
            "streams": [
                {"codec_type": "video", "codec_name": "hevc", "width": 3840,
                 "height": 2160, "pix_fmt": "yuv420p10le"},
                {"codec_type": "audio", "codec_name": "eac3", "channels": 6},
            ],
        }
        completed = Mock(returncode=0, stdout=json.dumps(payload))
        with patch("server.media_probe.subprocess.run", return_value=completed) as run:
            first = inspect_media(self.file)
            self.assertEqual(first["container"], "mkv")
            self.assertEqual(first["video_codec"], "hevc")
            self.assertEqual(first["audio_codec"], "eac3")
            self.assertEqual(first["width"], 3840)
            self.assertEqual(first["bitrate"], 8200000)
            self.assertEqual(inspect_media(self.file), first)
            self.assertEqual(run.call_count, 1)
            self.file.write_bytes(b"second file content")
            inspect_media(self.file)
            self.assertEqual(run.call_count, 2)

    def test_invalid_or_missing_media_reports_unknown_capabilities(self):
        self.assertEqual(inspect_media(self.file.with_name("not-there.mp4")), {})
        with patch("server.media_probe.subprocess.run",
                   return_value=Mock(returncode=1, stdout="")):
            self.assertEqual(inspect_media(self.file), {})

    def test_encoder_must_be_tested_not_only_detected(self):
        hardware_supported.cache_clear()
        self.addCleanup(hardware_supported.cache_clear)
        with patch("server.hardware.Path.is_char_device", return_value=True), \
             patch("server.hardware.os.access", return_value=True), \
             patch("server.hardware.subprocess.run", return_value=Mock(returncode=1)) as run:
            self.assertFalse(hardware_supported())
            self.assertEqual(run.call_count, 1)
        hardware_supported.cache_clear()
        with patch("server.hardware.Path.is_char_device", return_value=True), \
             patch("server.hardware.os.access", return_value=True), \
             patch("server.hardware.subprocess.run", return_value=Mock(returncode=0)):
            self.assertTrue(hardware_supported())


if __name__ == "__main__":
    unittest.main()
