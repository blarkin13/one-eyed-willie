"""Lyrics (LRCLIB): off by default, owner-only settings, cached lookups, local lyrics first."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
from pydantic import ValidationError

from server import barnacle_access, library, lyrics_online, music
from server.viewer import Viewer

FFMPEG = shutil.which("ffmpeg")


def reply(status, body=None):
    response = MagicMock()
    response.status_code = status
    response.json.return_value = body
    return response


class OnlineLyricsTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        patcher = patch.object(library, "DB_PATH", Path(temp.name) / "db.sqlite3")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_off_by_default_and_saved(self):
        self.assertEqual(lyrics_online.get_settings()["enabled"], False)
        self.assertEqual(lyrics_online.get_settings()["server"], "https://lrclib.net")
        with patch.object(lyrics_online.httpx, "get") as get:
            self.assertIsNone(lyrics_online.lookup(1, 1, "A", "T", "B", 100))
            get.assert_not_called()
        saved = lyrics_online.save_settings(lyrics_online.OnlineLyricsSettings(enabled=True, server="http://lrclib:3300/"))
        self.assertEqual((saved["enabled"], saved["server"]), (True, "http://lrclib:3300"))

    def test_bad_addresses_are_refused(self):
        for bad in ("ftp://x", "lrclib.net", "https://user:pw@x.example", "https://x.example/?q=1"):
            with self.subTest(bad=bad), self.assertRaises(ValidationError):
                lyrics_online.OnlineLyricsSettings(enabled=True, server=bad)

    def test_shared_viewers_cannot_change_it(self):
        barnacle = Viewer(id="u:x", role="barnacle", name="Friend", libraries=(1,))
        self.assertFalse(barnacle_access.allowed(barnacle, "PUT", "/api/lyrics-online/settings", ""))
        self.assertFalse(barnacle_access.allowed(barnacle, "GET", "/api/lyrics-online/settings", ""))

    def test_lookup_asks_once_and_remembers_answers_and_misses(self):
        lyrics_online.save_settings(lyrics_online.OnlineLyricsSettings(enabled=True))
        found = reply(200, {"syncedLyrics": "[00:01.00]Hi\n[00:02.00]There", "plainLyrics": "Hi\nThere"})
        with patch.object(lyrics_online.httpx, "get", return_value=found) as get:
            self.assertEqual(lyrics_online.lookup(7, 5, "Louis Armstrong", "The Home Fire", "WaWW", 197.4)["text"][:12], "[00:01.00]Hi")
            lyrics_online.lookup(7, 5, "Louis Armstrong", "The Home Fire", "WaWW", 197.4)
            self.assertEqual(get.call_count, 1)
            url, = get.call_args.args
            self.assertEqual(url, "https://lrclib.net/api/get")
            self.assertEqual(get.call_args.kwargs["params"], {"artist_name": "Louis Armstrong", "track_name": "The Home Fire",
                                                              "album_name": "WaWW", "duration": "197"})
        with patch.object(lyrics_online.httpx, "get", return_value=reply(404)) as get:
            self.assertIsNone(lyrics_online.lookup(8, 5, "A", "T", None, None))
            self.assertIsNone(lyrics_online.lookup(8, 5, "A", "T", None, None))
            self.assertEqual(get.call_count, 1, "a miss is remembered")
        with patch.object(lyrics_online.httpx, "get", side_effect=httpx.ConnectError("down")) as get:
            lyrics_online.lookup(9, 5, "A", "T", None, None)
            lyrics_online.lookup(9, 5, "A", "T", None, None)
            self.assertEqual(get.call_count, 2, "network trouble is not remembered")
        with patch.object(lyrics_online.httpx, "get", return_value=reply(200, {"instrumental": True})):
            self.assertEqual(lyrics_online.lookup(10, 5, "A", "Theme", None, None), {"instrumental": True})
        # A changed file is asked about again; so are misses after changing the server address.
        with patch.object(lyrics_online.httpx, "get", return_value=reply(404)) as get:
            lyrics_online.lookup(7, 6, "Louis Armstrong", "The Home Fire", "WaWW", 197.4)
            self.assertEqual(get.call_count, 1)
        lyrics_online.save_settings(lyrics_online.OnlineLyricsSettings(enabled=True, server="http://lrclib:3300"))
        with patch.object(lyrics_online.httpx, "get", return_value=reply(404)) as get:
            lyrics_online.lookup(8, 5, "A", "T", None, None)
            self.assertEqual(get.call_args.args[0], "http://lrclib:3300/api/get")


@unittest.skipUnless(FFMPEG, "ffmpeg required")
class DetailsUseOnlineLyricsTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        musicdir = root / "media" / "Music"
        self.song = musicdir / "Louis Armstrong" / "What a Wonderful World" / "01 - The Home Fire.flac"
        self.song.parent.mkdir(parents=True)
        subprocess.run([FFMPEG, "-loglevel", "error", "-f", "lavfi", "-i", "sine=duration=1",
                        "-metadata", "title=The Home Fire", "-metadata", "artist=Louis Armstrong", str(self.song)], check=True)
        for name, value in (("DB_PATH", root / "db.sqlite3"), ("MEDIA_ROOT", root / "media")):
            patcher = patch.object(library, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        music._read_tags.cache_clear()
        created = library.create_library(library.LibraryRequest(name="Music", kind="music", path=str(musicdir), icon="music"))
        library.scan_library(created["id"])
        self.track_id = music.music_catalog()["tracks"][0]["id"]

    def test_online_lyrics_only_when_on_and_after_local_ones(self):
        details = music.music_track_details(self.track_id)
        self.assertIsNone(details["lyrics"])
        self.assertIs(details["online_lyrics"], False)
        lyrics_online.save_settings(lyrics_online.OnlineLyricsSettings(enabled=True))
        with patch.object(lyrics_online.httpx, "get", return_value=reply(200, {"plainLyrics": "From LRCLIB"})) as get:
            lyrics = music.music_track_details(self.track_id)["lyrics"]
            self.assertEqual((lyrics["source"], lyrics["plain"]), ("lrclib", "From LRCLIB"))
            self.assertEqual(get.call_args.kwargs["params"]["artist_name"], "Louis Armstrong")
        self.song.with_suffix(".lrc").write_text("[00:01.00]Mine\n[00:02.00]Too\n")
        with patch.object(lyrics_online.httpx, "get") as get:
            self.assertEqual(music.music_track_details(self.track_id)["lyrics"]["source"], "lrc")
            get.assert_not_called()


if __name__ == "__main__":
    unittest.main()
