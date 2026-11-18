"""Choosing an audio track for a transcoded stream (real FFmpeg).

The test movie carries two audio tracks that differ by pitch (440 Hz English,
880 Hz French, 5.1-labelled commentary is not needed), so the pitch of the
decoded stream shows which track was really used.
"""
import array
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from server import hls, library

FFMPEG = "/usr/bin/ffmpeg"
HAVE_FFMPEG = os.path.isfile(FFMPEG) and os.path.isfile("/usr/bin/ffprobe")


def pitch_hz(source):
    """Dominant pitch of a stream's audio by counting zero crossings."""
    run = subprocess.run(
        [FFMPEG, "-v", "error", "-nostdin", "-i", str(source), "-map", "0:a:0", "-ac", "1", "-ar", "8000",
         "-f", "s16le", "-"], capture_output=True,
        # Never route a localhost stream through a proxy.
        env={k: v for k, v in os.environ.items() if "proxy" not in k.lower()})
    if not run.stdout:
        raise AssertionError("ffmpeg decoded no audio from %s: %s" % (source, run.stderr.decode(errors="replace")))
    samples = array.array("h")
    samples.frombytes(run.stdout[: len(run.stdout) // 2 * 2])
    crossings = sum(1 for a, b in zip(samples, samples[1:]) if (a < 0) != (b < 0))
    return crossings / 2 / (len(samples) / 8000)


@unittest.skipUnless(HAVE_FFMPEG, "FFmpeg is required")
class AudioTrackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.movie = cls.root / "movie.mkv"
        subprocess.run(
            [FFMPEG, "-v", "error", "-nostdin", "-y",
             "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=24",
             "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
             "-f", "lavfi", "-i", "sine=frequency=880:sample_rate=48000",
             "-t", "8", "-map", "0:v", "-map", "1:a", "-map", "2:a",
             "-c:v", "libx264", "-preset", "ultrafast", "-g", "24", "-pix_fmt", "yuv420p",
             "-c:a", "ac3", "-ac", "2",
             "-metadata:s:a:0", "language=eng", "-metadata:s:a:1", "language=fre",
             "-metadata:s:a:1", "title=Doublage", "-disposition:a:0", "default",
             str(cls.movie)], check=True)
        cls.db_patch = patch.object(library, "DB_PATH", cls.root / "library.sqlite3")
        cls.db_patch.start()

    @classmethod
    def tearDownClass(cls):
        cls.db_patch.stop()
        cls.tmp.cleanup()

    def setUp(self):
        for p in (patch.object(hls, "ROOT", self.root / "hls"),
                  patch.object(hls, "_item", return_value=({"id": 1}, self.movie)),
                  patch.object(hls, "hardware_available", return_value=False)):
            p.start()
            self.addCleanup(p.stop)

    def run_session(self, quality, audio=None):
        kwargs = {} if audio is None else {"audio": audio}
        info = hls.start_hls(1, 0, quality, **kwargs)
        session = hls.ACTIVE[info["session"]]
        session.process.wait(timeout=60)
        self.assertEqual(session.process.returncode, 0, hls._log_tail(session.directory))
        self.addCleanup(lambda: hls.stop_hls(info["session"]))
        return session.directory / "index.m3u8"

    def test_tracks_are_listed_with_readable_labels(self):
        tracks = hls.audio_tracks(1)["tracks"]
        self.assertEqual([t["id"] for t in tracks], [0, 1])
        self.assertEqual(tracks[0]["label"], "English · Stereo · AC3")
        self.assertEqual(tracks[1]["label"], "French · Doublage · Stereo · AC3")
        self.assertEqual([t["language"] for t in tracks], ["eng", "fre"])
        self.assertEqual([t["default"] for t in tracks], [True, False])

    def test_the_first_track_is_used_unless_another_is_chosen(self):
        self.assertAlmostEqual(pitch_hz(self.run_session("360p")), 440, delta=15)

    def test_a_chosen_track_is_what_gets_transcoded(self):
        self.assertAlmostEqual(pitch_hz(self.run_session("360p", audio=1)), 880, delta=25)

    def test_full_quality_also_honours_the_choice(self):
        playlist = self.run_session("full", audio=1)
        self.assertAlmostEqual(pitch_hz(playlist), 880, delta=25)

    def test_a_track_that_does_not_exist_is_refused(self):
        with self.assertRaises(HTTPException) as error:
            hls.start_hls(1, 0, "360p", audio=2)
        self.assertEqual(error.exception.status_code, 400)

    def test_a_video_without_audio_lists_nothing(self):
        silent = self.root / "silent.mp4"
        subprocess.run([FFMPEG, "-v", "error", "-nostdin", "-y", "-f", "lavfi", "-i", "testsrc2=size=160x90:rate=24",
                        "-t", "1", "-c:v", "libx264", str(silent)], check=True)
        self.assertEqual(hls.list_audio_tracks(silent), [])

    def test_a_missing_file_lists_nothing(self):
        self.assertEqual(hls.list_audio_tracks(self.root / "nope.mkv"), [])


if __name__ == "__main__":
    unittest.main()
