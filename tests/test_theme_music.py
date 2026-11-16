"""Local theme music discovery cannot escape mounted title folders."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from server import library, playback_settings, theme_music


class LocalThemeTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.media = root / "media"
        self.media.mkdir()
        self.db_patch = patch.object(library, "DB_PATH", root / "db.sqlite3")
        self.root_patch = patch.object(library, "MEDIA_ROOT", self.media)
        self.theme_root_patch = patch.object(theme_music, "MEDIA_ROOT", self.media)
        self.playback_root_patch = patch("server.playback.MEDIA_ROOT", self.media)
        for item in (self.db_patch, self.root_patch, self.theme_root_patch, self.playback_root_patch):
            item.start()
            self.addCleanup(item.stop)
        movies = self.media / "Movies"
        shows = self.media / "TV"
        movies.mkdir()
        shows.mkdir()
        self.movie_folder = movies / "Interstellar (2014)"
        self.movie_folder.mkdir()
        self.video = self.movie_folder / "Interstellar.mkv"
        self.video.write_bytes(b"video")
        self.show_folder = shows / "Severance"
        season = self.show_folder / "Season 01"
        season.mkdir(parents=True)
        self.episode = season / "Severance.S01E01.mkv"
        self.episode.write_bytes(b"episode")
        with library.db() as conn:
            conn.execute("INSERT INTO libraries(id,name,kind,path) VALUES (1,'Movies','movies',?)",
                         (str(movies),))
            conn.execute("INSERT INTO libraries(id,name,kind,path) VALUES (2,'TV Shows','tv',?)",
                         (str(shows),))
            conn.execute(
                "INSERT INTO media(id,library_id,path,title,size,mtime_ns,added_at) "
                "VALUES(1,1,?,'Interstellar',5,0,'2026-11-16')", (str(self.video),))
            conn.execute(
                "INSERT INTO media(id,library_id,path,title,size,mtime_ns,added_at) "
                "VALUES(2,2,?,'Severance',7,0,'2026-11-16')", (str(self.episode),))

    def test_movies_and_tv_are_discovered_from_own_folders(self):
        self.assertFalse(theme_music.theme_info(1)["available"])
        self.assertFalse(theme_music.theme_info(2)["available"])
        (self.movie_folder / "theme.mp3").write_bytes(b"audio")
        (self.show_folder / "theme.ogg").write_bytes(b"audio")
        self.assertEqual(theme_music.theme_for_media(1).name, "theme.mp3")
        self.assertEqual(theme_music.theme_for_media(2).name, "theme.ogg")
        self.assertEqual(theme_music.theme_info(2)["url"], "/api/themes/2/audio")
        response = theme_music.theme_audio(1)
        self.assertEqual(response.media_type, "audio/mpeg")
        self.assertEqual(response.headers["cache-control"], "private, no-store")

    def test_symlinks_oversized_and_parent_theme_are_not_exposed(self):
        outside = self.media.parent / "not-a-title.mp3"
        outside.write_bytes(b"private")
        (self.movie_folder / "theme.mp3").symlink_to(outside)
        self.assertIsNone(theme_music.theme_for_media(1))
        (self.movie_folder / "theme.mp3").unlink()
        with self.assertRaises(HTTPException):
            theme_music.theme_audio(1)
        (self.show_folder / "theme.mp3").write_bytes(b"audio")
        with patch.object(theme_music, "MAX_BYTES", 1):
            self.assertIsNone(theme_music.theme_for_media(2))

    def test_connected_plex_theme_is_discovered_without_local_mp3(self):
        from server import plex_import
        setting = {"url": "http://plex:32400", "token": "private-token"}
        def details(url, token, path, params=None):
            return {"Metadata": [{"theme": "/library/metadata/123/theme/987"}]}
        with patch.object(plex_import, "_require_config", return_value=setting), \
             patch.object(theme_music, "_plex_index", return_value={
                 ("show", "severance"): [(2022, 123)],
                 ("movie", "interstellar"): [(2014, 123)]
             }), \
             patch.object(plex_import, "_plex_get", side_effect=details):
            info = theme_music.theme_info(2)
            self.assertTrue(info["available"])
            self.assertEqual(info["source"], "plex")
            self.assertEqual(info["url"], "/api/themes/2/audio")
            self.assertTrue(theme_music.theme_info(1)["available"])

    def test_local_theme_has_priority_over_plex(self):
        theme = self.movie_folder / "theme.mp3"
        theme.write_bytes(b"audio")
        with patch.object(theme_music, "_plex_theme", side_effect=AssertionError("plex not needed")):
            self.assertEqual(theme_music.theme_info(1)["source"], "local")

    def test_wrong_or_ambiguous_plex_match_and_untrusted_theme_rejected(self):
        from server import plex_import
        setting = {"url": "http://plex:32400", "token": "private-token"}
        with patch.object(plex_import, "_require_config", return_value=setting), \
             patch.object(theme_music, "_plex_index", return_value={
                 ("show", "severance"): [(2022, 123), (2022, 124)]
             }), \
             patch.object(plex_import, "_plex_get") as getter:
            self.assertIsNone(theme_music._plex_theme(2))
            getter.assert_not_called()
        with patch.object(plex_import, "_require_config", return_value=setting), \
             patch.object(theme_music, "_plex_index", return_value={
                 ("show", "severance"): [(2022, 123)]
             }), \
             patch.object(plex_import, "_plex_get", return_value={
                 "Metadata": [{"theme": "https://untrusted.example/bad.mp3"}]
             }):
            self.assertIsNone(theme_music._plex_theme(2))

    def test_plex_catalog_is_bounded_and_cached(self):
        from server import plex_import
        setting = {"url": "http://plex:32400", "token": "private-token"}
        def plex_data(url, token, path, params=None):
            if path == "/library/sections":
                return {"Directory": [{"type": "show", "key": "1"}]}
            return {"Metadata": [{"type": "show", "title": "Severance",
                                  "year": 2022, "ratingKey": "123"}],
                    "totalSize": 1}
        with patch.object(plex_import, "_plex_get", side_effect=plex_data) as request:
            theme_music._index.update(url=None, expires=0, items={})
            self.assertEqual(theme_music._plex_index(setting)[("show", "severance")],
                             [(2022, 123)])
            theme_music._plex_index(setting)
            self.assertEqual(request.call_count, 2)

    def test_settings_keep_legacy_autoplay_and_validate_volume(self):
        defaults = playback_settings.get_preferences()
        self.assertTrue(defaults["movie_theme_music"])
        self.assertTrue(defaults["tv_theme_music"])
        self.assertEqual(defaults["theme_volume"], 25)
        changed = playback_settings.PlaybackPreferences(
            auto_play_next=True, tv_theme_music=False,
            movie_theme_music=True, theme_volume=35,
            theme_loop=False, theme_fade=True)
        playback_settings.update_preferences(changed)
        updated = playback_settings.get_preferences()
        self.assertTrue(updated["auto_play_next"])
        self.assertFalse(updated["tv_theme_music"])
        self.assertEqual(updated["theme_volume"], 35)
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            playback_settings.PlaybackPreferences(theme_volume=125)

    def test_client_scripts_are_wired_to_play_and_stop(self):
        server = Path(__file__).resolve().parents[1] / "server"
        movie = (server / "movie_detail.html").read_text()
        tv = (server / "tv_detail.html").read_text()
        player = (server / "player.js").read_text()
        javascript = (server / "theme-music.js").read_text()
        settings = (server / "general_settings.html").read_text()
        self.assertIn("WillieThemeMusic?.attach(movie.media_id,'movies'", movie)
        self.assertIn("WillieThemeMusic?.attach(firstEpisodeId,'tv'", tv)
        self.assertIn("WillieThemeMusic?.stop(true)", player)
        self.assertIn("pagehide", javascript)
        self.assertIn("audio.play()", javascript)
        self.assertIn("id=\"theme-volume\"", settings)


if __name__ == "__main__":
    unittest.main()
