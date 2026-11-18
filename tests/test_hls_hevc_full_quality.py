"""HEVC and 10-bit video passed straight through for browsers that can decode it (real FFmpeg).

Equal decoded-frame hashes prove nothing was re-encoded. Skipped without FFmpeg
or its x265 encoder.
"""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from server import hls, library
from tests.test_hls_full_quality import frame_hashes

FFMPEG = "/usr/bin/ffmpeg"


def have_x265():
    if not (os.path.isfile(FFMPEG) and os.path.isfile("/usr/bin/ffprobe")):
        return False
    out = subprocess.run([FFMPEG, "-hide_banner", "-encoders"], capture_output=True, text=True).stdout
    return "libx265" in out


def make(path, pix_fmt, x265=""):
    subprocess.run(
        [FFMPEG, "-v", "error", "-nostdin", "-y", "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=24",
         "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000", "-t", "10",
         "-c:v", "libx265", "-preset", "ultrafast",
         "-x265-params", "keyint=24:min-keyint=24:log-level=error" + x265,
         "-pix_fmt", pix_fmt, "-c:a", "ac3", "-ac", "2", str(path)], check=True)


@unittest.skipUnless(have_x265(), "FFmpeg with x265 is required")
class HevcFullQualityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.main = cls.root / "main.mkv"
        cls.main10 = cls.root / "main10.mkv"
        cls.hdr = cls.root / "hdr.mkv"
        make(cls.main, "yuv420p")
        make(cls.main10, "yuv420p10le")
        # HDR10 signalling written by the encoder itself, so it does not depend on how
        # this FFmpeg build passes colour flags through.
        make(cls.hdr, "yuv420p10le", ":colorprim=bt2020:transfer=smpte2084:colormatrix=bt2020nc")
        cls.db_patch = patch.object(library, "DB_PATH", cls.root / "library.sqlite3")
        cls.db_patch.start()

    @classmethod
    def tearDownClass(cls):
        cls.db_patch.stop()
        cls.tmp.cleanup()

    def setUp(self):
        self.movie = self.main
        for p in (patch.object(hls, "ROOT", self.root / "hls"),
                  patch.object(hls, "_item", side_effect=lambda _id: ({"id": 1}, self.movie)),
                  patch.object(hls, "hardware_available", return_value=False)):
            p.start()
            self.addCleanup(p.stop)

    def run_session(self, movie, hevc, start=0):
        self.movie = movie
        info = hls.start_hls(1, start, "full", hevc=hevc)
        session = hls.ACTIVE[info["session"]]
        session.process.wait(timeout=90)
        self.assertEqual(session.process.returncode, 0, hls._log_tail(session.directory))
        self.addCleanup(lambda: hls.stop_hls(info["session"]))
        return session.directory

    def probe(self, source):
        out = subprocess.run(
            ["/usr/bin/ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
             "stream=codec_name,codec_tag_string,pix_fmt", "-of", "csv=p=0", str(source)],
            capture_output=True, text=True).stdout
        return " ".join(sorted(set(out.split())))     # fragmented MP4 lists the stream once per file

    def test_8_bit_hevc_is_copied_in_fragmented_mp4_tagged_for_browsers(self):
        folder = self.run_session(self.main, 8)
        playlist = (folder / "index.m3u8").read_text()
        self.assertIn('#EXT-X-MAP:URI="init.mp4"', playlist)
        self.assertTrue((folder / "init.mp4").is_file())
        self.assertTrue(list(folder.glob("segment_*.m4s")))
        self.assertFalse(list(folder.glob("*.ts")))
        self.assertEqual(self.probe(folder / "index.m3u8"), "hevc,hvc1,yuv420p")
        self.assertEqual(frame_hashes(folder / "index.m3u8"), frame_hashes(self.main))

    def test_10_bit_hevc_is_copied_untouched(self):
        folder = self.run_session(self.main10, 10)
        self.assertEqual(self.probe(folder / "index.m3u8"), "hevc,hvc1,yuv420p10le")
        self.assertEqual(frame_hashes(folder / "index.m3u8"), frame_hashes(self.main10))

    def test_audio_is_still_made_browser_safe(self):
        folder = self.run_session(self.main, 8)
        codecs = subprocess.run(
            ["/usr/bin/ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=codec_name",
             "-of", "csv=p=0", str(folder / "index.m3u8")], capture_output=True, text=True).stdout.split()
        self.assertEqual(set(codecs), {"aac"})

    def test_seeking_starts_at_a_keyframe_at_or_before_the_target(self):
        folder = self.run_session(self.main, 8, start=7)
        frames, source = frame_hashes(folder / "index.m3u8"), frame_hashes(self.main)
        offset = len(source) - len(frames)
        self.assertEqual(frames, source[offset:])
        self.assertEqual(offset % 24, 0)
        self.assertLessEqual(offset / 24, 7)

    def test_a_browser_that_cannot_decode_hevc_is_refused(self):
        self.movie = self.main
        for hevc in (0, None):
            with self.subTest(hevc=hevc), self.assertRaises(HTTPException) as error:
                hls.start_hls(1, 0, "full", hevc=hevc)
            self.assertEqual(error.exception.status_code, 409)
            self.assertIn("HEVC", error.exception.detail)

    def test_10_bit_needs_a_browser_that_says_it_can_decode_10_bit(self):
        self.movie = self.main10
        with self.assertRaises(HTTPException) as error:
            hls.start_hls(1, 0, "full", hevc=8)
        self.assertIn("10-bit", error.exception.detail)

    def test_hdr_is_never_passed_through(self):
        self.movie = self.hdr
        # Guard the fixture: it must really be signalled as HDR10.
        self.assertEqual(hls.inspect_media(self.hdr).get("hdr_transfer"), "smpte2084")
        with self.assertRaises(HTTPException) as error:
            hls.start_hls(1, 0, "full", hevc=10)
        self.assertIn("HDR", error.exception.detail)

    def test_dolby_vision_is_never_passed_through(self):
        profile = {"video_codec": "hevc", "pixel_format": "yuv420p10le", "dolby_vision": True}
        available, reason = hls.full_quality_support(profile, 10)
        self.assertFalse(available)
        self.assertIn("Dolby Vision", reason)

    def test_other_codecs_and_formats_are_still_refused(self):
        for profile in ({"video_codec": "h264", "pixel_format": "yuv420p10le"},
                        {"video_codec": "hevc", "pixel_format": "yuv444p"},
                        {"video_codec": "vp9", "pixel_format": "yuv420p"},
                        {"video_codec": "av1", "pixel_format": "yuv420p"}):
            with self.subTest(profile=profile):
                self.assertFalse(hls.full_quality_support(profile, 10)[0])

    def test_estimates_follow_what_the_browser_can_decode(self):
        self.movie = self.main10
        none = hls.data_estimates(1, hevc=0)["full"]
        main = hls.data_estimates(1, hevc=8)["full"]
        deep = hls.data_estimates(1, hevc=10)["full"]
        self.assertFalse(none["available"])
        self.assertFalse(main["available"])
        self.assertTrue(deep["available"])
        self.assertGreater(deep["bytes"], 0)

    def test_the_depth_claim_is_sanitised(self):
        self.assertEqual([hls.hevc_depth(v) for v in (0, 8, 10, 12, -1, None, "10")], [0, 8, 10, 0, 0, 0, 0])

    def test_init_and_fragment_files_are_servable_with_the_right_types(self):
        self.assertTrue(hls.SEGMENT.fullmatch("init.mp4"))
        self.assertTrue(hls.SEGMENT.fullmatch("segment_000012.m4s"))
        self.assertTrue(hls.SEGMENT.fullmatch("segment_000012.ts"))
        for bad in ("../init.mp4", "segment_12.m4s", "evil.mp4", "init.mp4.exe", "segment_000012.mp4"):
            self.assertFalse(hls.SEGMENT.fullmatch(bad), bad)
        self.assertEqual(hls.CONTENT_TYPES[".m4s"], "video/iso.segment")


if __name__ == "__main__":
    unittest.main()
