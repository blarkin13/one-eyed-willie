"""Full-screen music player: audio details and lyrics from the user's own files."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from server import barnacle_access, library, music
from server.viewer import Viewer

FFMPEG = shutil.which("ffmpeg")


class LyricsParsingTests(unittest.TestCase):
    def test_synced_lrc_with_offset_and_repeated_lines(self):
        parsed = music.parse_lyrics("[ar:Louis]\n[offset:+500]\n[00:12.50]I see trees\n[00:15.00][01:00.00]of green\n")
        self.assertEqual(parsed["synced"], [{"time": 12.0, "text": "I see trees"},
                                            {"time": 14.5, "text": "of green"}, {"time": 59.5, "text": "of green"}])
        self.assertEqual(parsed["plain"], "I see trees\nof green")

    def test_plain_text_and_empty(self):
        self.assertEqual(music.parse_lyrics("Line one\r\nLine two"), {"synced": None, "plain": "Line one\nLine two"})
        self.assertIsNone(music.parse_lyrics("  \n"))
        self.assertIsNone(music.parse_lyrics(None))
        self.assertLessEqual(len(music.parse_lyrics("x" * 200000)["plain"]), music.LYRICS_MAX)

    def test_shared_viewers_may_read_details_of_tracks_they_can_see(self):
        rule = [r for r in barnacle_access._RULES if "music/tracks" in r[1]][0]
        self.assertIn("details", rule[1])


@unittest.skipUnless(FFMPEG, "ffmpeg required")
class TrackDetailsTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.musicdir = root / "media" / "Music"
        self.song = self.musicdir / "Louis Armstrong" / "What a Wonderful World" / "01 - The Home Fire.flac"
        self.song.parent.mkdir(parents=True)
        subprocess.run([FFMPEG, "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
                        "-ar", "44100", "-ac", "2", "-sample_fmt", "s16",
                        "-metadata", "title=The Home Fire", "-metadata", "composer=Someone",
                        "-metadata", "LYRICS=Embedded line one\nEmbedded line two", str(self.song)], check=True)
        for name, value in (("DB_PATH", root / "db.sqlite3"), ("MEDIA_ROOT", root / "media")):
            patcher = patch.object(library, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        music._read_tags.cache_clear()
        created = library.create_library(library.LibraryRequest(name="Music", kind="music",
                                                                 path=str(self.musicdir), icon="music"))
        library.scan_library(created["id"])
        self.track_id = music.music_catalog()["tracks"][0]["id"]

    def test_audio_details_and_embedded_lyrics(self):
        details = music.music_track_details(self.track_id)
        self.assertEqual(details["format"], "FLAC")
        self.assertEqual(details["sample_rate"], 44100)
        self.assertEqual(details["bit_depth"], 16)
        self.assertEqual(details["channels"], 2)
        self.assertEqual(details["composer"], "Someone")
        self.assertEqual(details["lyrics"]["source"], "embedded")
        self.assertEqual(details["lyrics"]["plain"], "Embedded line one\nEmbedded line two")
        self.assertIsNone(details["lyrics"]["synced"])

    def test_a_sidecar_lrc_wins_and_is_synced(self):
        self.song.with_suffix(".lrc").write_text("[00:01.00]Synced one\n[00:02.00]Synced two\n", encoding="utf-8")
        lyrics = music.music_track_details(self.track_id)["lyrics"]
        self.assertEqual(lyrics["source"], "lrc")
        self.assertEqual([x["text"] for x in lyrics["synced"]], ["Synced one", "Synced two"])

    def test_no_lyrics(self):
        subprocess.run([FFMPEG, "-loglevel", "error", "-y", "-f", "lavfi", "-i", "sine=duration=1",
                        str(self.song)], check=True)
        self.assertIsNone(music.music_track_details(self.track_id)["lyrics"])


if __name__ == "__main__":
    unittest.main()
