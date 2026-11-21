"""Top songs: the artist's most-listened songs (ListenBrainz) that are in the library."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx

from server import barnacle_access, library, music, music_top
from server.viewer import Viewer

FFMPEG = shutil.which("ffmpeg")
MBID = "bdacc37b-8633-4bf8-9dd5-c662ee651aec"


def reply(body):
    r = MagicMock()
    r.json.return_value = body
    r.raise_for_status.return_value = None
    return r


class NormalizeTests(unittest.TestCase):
    def test_titles_match_across_editions(self):
        self.assertEqual(music_top.normalize("Raining Blood (Remastered 2015)"), "raining blood")
        self.assertEqual(music_top.normalize("Angel Of Death - 2013 Remaster"), "angel of death")
        self.assertEqual(music_top.normalize("Sólo Tú & Yo"), "solo tu and yo")
        self.assertEqual(music_top.normalize("South of Heaven [Live]"), "south of heaven")

    def test_shared_viewers_can_see_top_songs(self):
        friend = Viewer(id="u:y", role="barnacle", name="Y", libraries=(1,))
        self.assertTrue(barnacle_access.allowed(friend, "GET", "/api/music/artist-top", {"name": ["Slayer"]}))


@unittest.skipUnless(FFMPEG, "ffmpeg required")
class ArtistTopTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        musicdir = root / "media" / "Music"
        for n, title in enumerate(["Raining Blood (Remastered)", "Angel of Death", "Postmortem", "Criminally Insane"], 1):
            path = musicdir / "Slayer" / "Reign in Blood" / f"0{n} {title}.flac"
            path.parent.mkdir(parents=True, exist_ok=True)
            tags = ["-metadata", f"title={title}", "-metadata", "artist=Slayer"]
            if n == 1:
                tags += ["-metadata", f"MUSICBRAINZ_ARTISTID={MBID}"]
            subprocess.run([FFMPEG, "-loglevel", "error", "-f", "lavfi", "-i", "sine=duration=1", *tags, str(path)], check=True)
        for name, value in (("DB_PATH", root / "db.sqlite3"), ("MEDIA_ROOT", root / "media")):
            p = patch.object(library, name, value)
            p.start()
            self.addCleanup(p.stop)
        music._read_tags.cache_clear()
        created = library.create_library(library.LibraryRequest(name="Music", kind="music", path=str(musicdir), icon="music"))
        library.scan_library(created["id"])
        self.ids = {t["title"]: t["id"] for t in music.music_catalog()["tracks"]}

    def test_ranked_by_listens_limited_to_owned_songs_and_cached(self):
        ranking = [{"recording_name": n} for n in ["Raining Blood", "Angel of Death", "South of Heaven", "Criminally Insane"]]
        with patch.object(music_top.httpx, "get", return_value=reply(ranking)) as get:
            result = music_top.artist_top("Slayer", limit=5)
            self.assertEqual(result["tracks"], [self.ids["Raining Blood (Remastered)"], self.ids["Angel of Death"],
                                                self.ids["Criminally Insane"]])
            self.assertEqual(result["source"], "ListenBrainz")
            self.assertIn(MBID, get.call_args.args[0], "the MusicBrainz id comes from the file's tags")
            music_top.artist_top("slayer", limit=5)
            self.assertEqual(get.call_count, 1, "cached")

    def test_name_search_when_tags_have_no_id_and_offline_is_quiet(self):
        with patch.object(music_top, "_mbid_from_tags", return_value=None), \
             patch.object(music_top.httpx, "get", side_effect=[
                 reply({"artists": [{"id": MBID, "name": "Slayer", "score": 100}]}),
                 reply([{"recording_name": "Postmortem"}])]) as get:
            self.assertEqual(music_top.artist_top("Slayer", limit=5)["tracks"], [self.ids["Postmortem"]])
            self.assertEqual(get.call_args_list[0].kwargs["params"]["query"], 'artist:"Slayer"')
        with library.db() as conn:
            conn.execute("DELETE FROM music_artist_top")
        with patch.object(music_top.httpx, "get", side_effect=httpx.ConnectError("offline")):
            self.assertEqual(music_top.artist_top("Slayer"), {"tracks": [], "source": None})
        self.assertEqual(music_top.artist_top("Nobody"), {"tracks": [], "source": None})


if __name__ == "__main__":
    unittest.main()
