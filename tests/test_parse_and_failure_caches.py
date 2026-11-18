import unittest
import urllib.error
from unittest.mock import patch

from server import catalog, tvmaze

TV = "/media/TV/Show A (2001)/Season 01/Show.A.S01E02.mkv"


class FilenameParseCacheTests(unittest.TestCase):
    def setUp(self):
        catalog._movie_info_cached.cache_clear()
        catalog._episode_info_cached.cache_clear()

    def test_repeat_parses_hit_the_cache_and_match_the_uncached_result(self):
        movie = "/media/Movies/Alien (1979)/Alien.1979.mkv"
        for _ in range(5):
            self.assertEqual(catalog.movie_info(movie, "/media/Movies"),
                             catalog._movie_info(movie, "/media/Movies"))
            self.assertEqual(catalog.episode_info(TV, "/media/TV"),
                             catalog._episode_info(TV, "/media/TV"))
        self.assertEqual(catalog._movie_info_cached.cache_info().misses, 1)
        self.assertEqual(catalog._episode_info_cached.cache_info().misses, 1)
        self.assertEqual(catalog._episode_info_cached.cache_info().hits, 4)

    def test_callers_get_independent_copies(self):
        first = catalog.episode_info(TV, "/media/TV")
        first["title"] = "changed"
        first["season"] = 99
        again = catalog.episode_info(TV, "/media/TV")
        self.assertEqual((again["title"], again["season"]), ("Show A", 1))

    def test_path_and_str_arguments_share_one_entry(self):
        from pathlib import Path
        self.assertEqual(catalog.episode_info(Path(TV), Path("/media/TV")),
                         catalog.episode_info(TV, "/media/TV"))
        self.assertEqual(catalog._episode_info_cached.cache_info().misses, 1)

    def test_errors_are_not_cached_and_keep_raising(self):
        for _ in range(2):
            with self.assertRaises(ValueError):
                catalog.episode_info("/elsewhere/x.S01E01.mkv", "/media/TV")
        self.assertEqual(catalog._episode_info_cached.cache_info().currsize, 0)

    def test_different_roots_are_different_entries(self):
        a = catalog.episode_info(TV, "/media/TV")
        b = catalog.episode_info(TV, "/media/TV/Show A (2001)")
        self.assertEqual(a["title"], "Show A")
        self.assertEqual(b["title"], "Season 01")   # first folder under that root
        self.assertEqual(catalog._episode_info_cached.cache_info().misses, 2)


class TvmazeFailureCacheTests(unittest.TestCase):
    def setUp(self):
        tvmaze._FAILED_UNTIL.clear()
        self.addCleanup(tvmaze._FAILED_UNTIL.clear)

    def test_failed_request_is_not_retried_until_the_ttl_expires(self):
        clock = [1000.0]
        with patch.object(tvmaze.time, "monotonic", lambda: clock[0]), \
                patch.object(tvmaze.urllib.request, "urlopen",
                             side_effect=urllib.error.URLError("down")) as opener:
            self.assertIsNone(tvmaze._get("/search/shows", {"q": "x"}))
            self.assertIsNone(tvmaze._get("/search/shows", {"q": "x"}))
            self.assertEqual(opener.call_count, 1)
            self.assertIsNone(tvmaze._get("/search/shows", {"q": "other"}))
            self.assertEqual(opener.call_count, 2, "other URLs are unaffected")
            clock[0] += tvmaze.FAILURE_TTL_SECONDS + 1
            self.assertIsNone(tvmaze._get("/search/shows", {"q": "x"}))
            self.assertEqual(opener.call_count, 3, "retried after the TTL")

    def test_successful_responses_are_never_blocked_by_the_failure_cache(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self, n): return b'[{"id": 1}]'
        with patch.object(tvmaze.urllib.request, "urlopen", return_value=Response()) as opener:
            for _ in range(3):
                self.assertEqual(tvmaze._get("/shows/1"), [{"id": 1}])
        self.assertEqual(opener.call_count, 3)


if __name__ == "__main__":
    unittest.main()
