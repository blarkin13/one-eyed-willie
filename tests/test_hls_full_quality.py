"""Full quality passes the original video through untouched (real FFmpeg).

A re-encode would change the decoded pictures, so equal frame hashes prove the
video was copied. Skipped when FFmpeg is not installed.
"""
import hashlib
import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from server import hls, library

FFMPEG = "/usr/bin/ffmpeg"
HAVE_FFMPEG = os.path.isfile(FFMPEG) and os.path.isfile("/usr/bin/ffprobe")


def frame_hashes(source, extra=()):
    """MD5 of every decoded video frame."""
    result = subprocess.run(
        [FFMPEG, "-v", "error", "-nostdin", *extra, "-i", str(source), "-map", "0:v:0",
         "-f", "framemd5", "-"], capture_output=True, text=True, check=True)
    return [line.rsplit(",", 1)[-1].strip() for line in result.stdout.splitlines()
            if line and not line.startswith("#")]


@unittest.skipUnless(HAVE_FFMPEG, "FFmpeg is required")
class FullQualityPassthroughTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.movie = cls.root / "movie.mkv"
        # 12 s of h264 + AC3 (a codec browsers cannot play) in a Matroska container.
        subprocess.run(
            [FFMPEG, "-v", "error", "-nostdin", "-y", "-f", "lavfi", "-i",
             "testsrc2=size=640x360:rate=24", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
             "-t", "12", "-c:v", "libx264", "-preset", "ultrafast", "-g", "24", "-pix_fmt", "yuv420p",
             "-c:a", "ac3", "-ac", "2", str(cls.movie)], check=True)

        # The probe cache lives in the library database: never touch the real one.
        cls.db_patch = patch.object(library, "DB_PATH", cls.root / "library.sqlite3")
        cls.db_patch.start()

    @classmethod
    def tearDownClass(cls):
        cls.db_patch.stop()
        cls.tmp.cleanup()

    def run_session(self, quality, start=0):
        patches = [
            patch.object(hls, "ROOT", self.root / "hls"),
            patch.object(hls, "_item", return_value=({"id": 1}, self.movie)),
            patch.object(hls, "hardware_available", return_value=False),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        info = hls.start_hls(1, start, quality)
        session = hls.ACTIVE[info["session"]]
        session.process.wait(timeout=60)
        self.assertEqual(session.process.returncode, 0, hls._log_tail(session.directory))
        self.addCleanup(lambda: hls.stop_hls(info["session"]))
        return info, session.directory

    def test_video_is_copied_bit_for_bit_and_audio_is_made_browser_safe(self):
        info, folder = self.run_session("full")
        self.assertEqual(info["quality"], "full")
        self.assertEqual(info["engine"], "Original video (no re-encode)")
        playlist = (folder / "index.m3u8").read_text()
        self.assertIn("#EXT-X-ENDLIST", playlist)
        # Decoded pictures are identical to the source: nothing was re-encoded.
        self.assertEqual(frame_hashes(folder / "index.m3u8"), frame_hashes(self.movie))
        probe = subprocess.run(
            ["/usr/bin/ffprobe", "-v", "error", "-show_entries", "stream=codec_name,codec_type,width,height",
             "-of", "csv=p=0", str(folder / "index.m3u8")], capture_output=True, text=True).stdout
        self.assertIn("h264,video,640,360", probe)
        self.assertIn("aac", probe)          # AC3 was converted for the browser
        self.assertNotIn("ac3", probe)

    def test_a_transcode_does_change_the_pictures(self):
        """Guards the test above: a real re-encode must NOT hash the same."""
        _, folder = self.run_session("360p")
        self.assertNotEqual(frame_hashes(folder / "index.m3u8"), frame_hashes(self.movie))

    def test_seeking_starts_at_a_keyframe_at_or_before_the_target(self):
        _, folder = self.run_session("full", start=7)
        frames = frame_hashes(folder / "index.m3u8")
        source = frame_hashes(self.movie)
        # Picture content is a suffix of the source: it begins at a keyframe
        # (every 24 frames) at or before 7 s, never after it.
        offset = len(source) - len(frames)
        self.assertEqual(frames, source[offset:])
        self.assertEqual(offset % 24, 0)
        self.assertLessEqual(offset / 24, 7)
        self.assertGreater(offset / 24, 7 - 1.01)

    def test_unsupported_video_is_refused_with_a_reason(self):
        for profile, expect in (
            ({"video_codec": "hevc", "pixel_format": "yuv420p"}, "HEVC"),
            ({"video_codec": "h264", "pixel_format": "yuv420p10le"}, "colour format"),
            ({"video_codec": "h264", "pixel_format": "yuv420p", "hdr_transfer": "smpte2084"}, "HDR"),
            ({}, "could not be read"),
        ):
            with self.subTest(expect=expect):
                available, reason = hls.full_quality_support(profile)
                self.assertFalse(available)
                self.assertIn(expect, reason)
        self.assertEqual(hls.full_quality_support(
            {"video_codec": "h264", "pixel_format": "yuv420p", "hdr_transfer": "bt709"}), (True, ""))

    def test_start_is_refused_for_unsupported_video(self):
        from fastapi import HTTPException
        with patch.object(hls, "ROOT", self.root / "hls2"), \
             patch.object(hls, "_item", return_value=({"id": 1}, self.movie)), \
             patch.object(hls, "inspect_media", return_value={"video_codec": "hevc"}):
            with self.assertRaises(HTTPException) as error:
                hls.start_hls(1, 0, "full")
        self.assertEqual(error.exception.status_code, 409)
        self.assertIn("HEVC", error.exception.detail)
        self.assertFalse(hls.ACTIVE)

    def test_estimates_report_full_quality_availability_and_size(self):
        with patch.object(hls, "_item", return_value=({"id": 1}, self.movie)), \
             patch.object(hls, "hardware_available", return_value=False):
            result = hls.data_estimates(1)
        self.assertTrue(result["full"]["available"])
        self.assertAlmostEqual(result["full"]["bytes"] / self.movie.stat().st_size,
                               hls.PACKAGING_OVERHEAD, places=2)
        with patch.object(hls, "_item", return_value=({"id": 1}, self.movie)), \
             patch.object(hls, "inspect_media", return_value={"video_codec": "hevc", "duration": 10}), \
             patch.object(hls, "hardware_available", return_value=False):
            result = hls.data_estimates(1)
        self.assertFalse(result["full"]["available"])
        self.assertEqual(result["full"]["bytes"], 0)
        self.assertIn("HEVC", result["full"]["reason"])


if __name__ == "__main__":
    unittest.main()
