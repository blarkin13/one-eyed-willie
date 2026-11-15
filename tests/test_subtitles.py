import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from server import subtitles


class SubtitlesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.video = self.root / "Example Movie.mkv"
        self.video.write_bytes(b"fake video")
        self.sidecar = self.root / "Example Movie.en.srt"
        self.sidecar.write_text("1\n00:00:01,000 --> 00:00:02,000\nHello\n")
        self.cache_patch = patch.object(subtitles, "CACHE", self.root / "cache")
        self.cache_patch.start()
        self.addCleanup(self.cache_patch.stop)
        self.item_patch = patch.object(subtitles, "_item",
                                       return_value=({"id": 1}, self.video))
        self.item_patch.start()
        self.addCleanup(self.item_patch.stop)

    def test_discovers_external_subtitle_without_exposing_path(self):
        with patch.object(subtitles, "_embedded", return_value=[]):
            result = subtitles.subtitle_list(1)
        self.assertEqual(len(result["tracks"]), 1)
        self.assertEqual(result["tracks"][0]["id"], "external-0")
        self.assertEqual(result["tracks"][0]["label"], "en")
        self.assertNotIn(str(self.root), str(result))

    def test_does_not_include_other_movies_or_symlinks(self):
        (self.root / "Other Movie.srt").write_text("other")
        outside = self.root.parent / "not-a-track.srt"
        # Symlink may exist, but must never appear among safe tracks.
        link = self.root / "Example Movie.forced.srt"
        link.symlink_to(outside)
        with patch.object(subtitles, "_embedded", return_value=[]):
            result = subtitles.subtitle_list(1)
        self.assertEqual([x["id"] for x in result["tracks"]], ["external-0"])

    def test_embedded_text_tracks_are_listed_not_images(self):
        streams = {"streams": [
            {"index": 2, "codec_name": "subrip", "tags": {"language": "eng"}},
            {"index": 3, "codec_name": "hdmv_pgs_subtitle", "tags": {}},
        ]}
        with patch.object(subtitles.subprocess, "run",
                          return_value=SimpleNamespace(stdout=__import__("json").dumps(streams))):
            result = subtitles.subtitle_list(1)
        self.assertEqual([t["id"] for t in result["tracks"]], ["external-0", "embedded-0"])
        self.assertEqual(result["tracks"][1]["label"], "eng")

    def test_safe_vtt_conversion_and_cache(self):
        calls = []
        def ffmpeg(args, **kwargs):
            calls.append(args)
            Path(args[-1]).write_text("WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nHello\n")
            return SimpleNamespace(returncode=0)
        with patch.object(subtitles.subprocess, "run", side_effect=ffmpeg), \
             patch.object(subtitles, "_embedded", return_value=[]):
            result = subtitles.subtitle_file(1, "external-0", 0)
            cached = subtitles.subtitle_file(1, "external-0", 0)
        self.assertEqual(result.media_type, "text/vtt")
        self.assertEqual(Path(result.path), Path(cached.path))
        self.assertEqual(len(calls), 1)
        self.assertTrue(Path(result.path).read_text().startswith("WEBVTT"))

    def test_start_offset_is_applied_on_resume(self):
        def ffmpeg(args, **kwargs):
            self.assertIn("-ss", args)
            self.assertIn(str(120), args)
            Path(args[-1]).write_text("WEBVTT\n")
            return SimpleNamespace(returncode=0)
        with patch.object(subtitles.subprocess, "run", side_effect=ffmpeg), \
             patch.object(subtitles, "_embedded", return_value=[]):
            result = subtitles.subtitle_file(1, "external-0", 120)
        self.assertTrue(Path(result.path).exists())

    def test_invalid_track_cannot_access_files(self):
        for value in ("../../movie", "external-9999", "embedded-0", "foo-1"):
            with patch.object(subtitles, "_embedded", return_value=[]):
                with self.assertRaises(HTTPException):
                    subtitles.subtitle_file(1, value, 0)


if __name__ == "__main__":
    unittest.main()
