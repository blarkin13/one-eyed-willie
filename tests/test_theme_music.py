"""Local theme music discovery cannot escape mounted title folders."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError

from fastapi import HTTPException

from server import library, playback_settings, theme_music


class LocalThemeTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        theme_music._failures.clear()
        self.media = root / "media"
        self.media.mkdir()
        self.db_patch = patch.object(library, "DB_PATH", root / "db.sqlite3")
        self.root_patch = patch.object(library, "MEDIA_ROOT", self.media)
        self.theme_root_patch = patch.object(theme_music, "MEDIA_ROOT", self.media)
        self.playback_root_patch = patch("server.playback.MEDIA_ROOT", self.media)
        self.no_network = patch.object(theme_music, "_fetch", side_effect=URLError("blocked in tests"))
        self.no_network.start()
        self.addCleanup(self.no_network.stop)
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

    def test_televisiontunes_automatically_downloads_exact_big_bang_theme(self):
        title = "The Big Bang Theory"
        show_folder = self.media / "TV" / title / "Season 01"
        show_folder.mkdir(parents=True)
        episode = show_folder / "The Big Bang Theory.S01E01.mkv"
        episode.write_bytes(b"episode")
        with library.db() as conn:
            conn.execute("UPDATE media SET path=? WHERE id=2", (str(episode),))
        page = (b'<html><h1>The Big Bang Theory</h1><a href="'
                b'/download.php?f=Big_Bang_Theory_%28The%29">Download MP3</a></html>')
        audio = b"ID3" + b"theme-data"
        def fake_fetch(url, accept, limit):
            if url.endswith(".html"):
                self.assertIn("Big_Bang_Theory_%28The%29", url)
                return page, "text/html"
            self.assertIn("/download.php?f=Big_Bang_Theory_", url)
            return audio, "audio/mpeg"
        cache = self.media.parent / "theme-cache"
        with patch.dict("os.environ", {"THEME_CACHE_DIR": str(cache)}), \
             patch.object(theme_music, "_fetch", side_effect=fake_fetch) as fetch:
            result = theme_music.theme_info(2)
            self.assertTrue(result["available"])
            self.assertEqual(result["source"], "televisiontunes")
            self.assertEqual(theme_music.theme_audio(2).media_type, "audio/mpeg")
            self.assertEqual(fetch.call_count, 2)
        self.assertEqual(len(list(cache.glob("*.mp3"))), 1)

    def test_legacy_heading_with_theme_song_suffix_is_accepted(self):
        title = "The Big Bang Theory"
        folder = self.media / "TV" / title / "Season 01"
        folder.mkdir(parents=True)
        video = folder / "The Big Bang Theory.S01E01.mkv"
        video.write_bytes(b"episode")
        with library.db() as conn:
            conn.execute("UPDATE media SET path=? WHERE id=2", (str(video),))
        page = (b'<h1>The Big Bang Theory - Theme Song</h1>'
                b'<a href="/download.php?f=Big_Bang_Theory_%28The%29">MP3</a>')
        cache = self.media.parent / "legacy-cache"
        def fake_fetch(url, accept, limit):
            if url.endswith(".html"):
                return page, "text/html"
            return b"ID3music", "audio/mpeg"
        with patch.dict("os.environ", {"THEME_CACHE_DIR": str(cache)}), \
             patch.object(theme_music, "_fetch", side_effect=fake_fetch):
            self.assertTrue(theme_music.theme_info(2)["available"])

    def test_access_denied_reports_distinct_reason_and_does_not_retry_rapidly(self):
        from urllib.error import HTTPError
        cache = self.media.parent / "blocked-cache"
        blocked = HTTPError("https://televisiontunes.com/", 403, "Forbidden", {}, None)
        with patch.dict("os.environ", {"THEME_CACHE_DIR": str(cache)}), \
             patch.object(theme_music, "_fetch", side_effect=blocked) as fetch:
            info = theme_music.theme_info(2)
            self.assertEqual(info["reason"], "source_access_denied")
            self.assertEqual(theme_music.theme_info(2)["reason"], "source_access_denied")
            self.assertEqual(fetch.call_count, 1)

    def test_source_heading_mismatch_reports_precise_reason(self):
        cache = self.media.parent / "mismatch-cache"
        with patch.dict("os.environ", {"THEME_CACHE_DIR": str(cache)}), \
             patch.object(theme_music, "_fetch", return_value=(b"<h1>Other TV Show</h1>", "text/html")):
            self.assertEqual(theme_music.theme_info(2)["reason"], "source_title_mismatch")

    def test_wrong_title_or_unavailable_site_never_returns_audio(self):
        cache = self.media.parent / "another-cache"
        page = b'<html><h1>Different Show</h1><a href="/download.php?f=Severance">MP3</a></html>'
        with patch.dict("os.environ", {"THEME_CACHE_DIR": str(cache)}), \
             patch.object(theme_music, "_fetch", return_value=(page, "text/html")) as fetch:
            info = theme_music.theme_info(2)
            self.assertFalse(info["available"])
            self.assertEqual(info["reason"], "source_title_mismatch")
            self.assertEqual(fetch.call_count, 1)
        self.assertFalse(list(cache.glob("*.mp3")) if cache.exists() else False)

    def test_network_failures_are_classified_without_leaking_details(self):
        import socket
        import ssl
        from urllib.error import URLError
        check = theme_music._network_failure
        self.assertEqual(check(URLError(socket.gaierror(socket.EAI_NONAME, "dns"))),
                         "source_dns_failure")
        self.assertEqual(check(URLError(ssl.SSLError("certificate verify failed"))),
                         "source_tls_failure")
        self.assertEqual(check(URLError(socket.timeout("timed out"))),
                         "source_timeout")
        self.assertEqual(check(URLError(ConnectionRefusedError("refused"))),
                         "source_connection_refused")

    def test_timeout_message_is_distinct_from_missing_theme(self):
        import socket
        cache = self.media.parent / "timeouts-cache"
        with patch.dict("os.environ", {"THEME_CACHE_DIR": str(cache)}), \
             patch.object(theme_music, "_fetch", side_effect=URLError(socket.timeout("timeout"))):
            self.assertEqual(theme_music.theme_info(2)["reason"], "source_timeout")

    def test_source_page_uses_canonical_encoded_parentheses(self):
        from server import theme_music
        folder = self.media / "TV" / "The Big Bang Theory" / "Season 01"
        folder.mkdir(parents=True)
        episode = folder / "The Big Bang Theory.S01E01.mkv"
        episode.write_bytes(b"episode")
        with library.db() as conn:
            conn.execute("UPDATE media SET path=? WHERE id=2", (str(episode),))
        self.assertEqual(
            theme_music._source_page_url(2),
            "https://televisiontunes.com/Big_Bang_Theory_%28The%29.html")
        self.assertEqual(
            theme_music.theme_info(2)["source_page"],
            "https://televisiontunes.com/Big_Bang_Theory_%28The%29.html")

    def test_movies_never_download_from_tv_only_source(self):
        with patch.object(theme_music, "_fetch") as fetch:
            info = theme_music.theme_info(1)
            self.assertEqual(info["reason"], "tv_only_source")
            fetch.assert_not_called()

    def test_local_theme_preferred_to_download(self):
        (self.show_folder / "theme.ogg").write_bytes(b"audio")
        with patch.object(theme_music, "_fetch", side_effect=AssertionError("not needed")):
            self.assertEqual(theme_music.theme_info(2)["source"], "local")

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
