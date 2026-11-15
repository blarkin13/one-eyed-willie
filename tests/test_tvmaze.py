import unittest
from unittest.mock import patch

from server import tv, tvmaze


class TVmazeTests(unittest.TestCase):
    def test_strip_html_summary_safely(self):
        self.assertEqual(tvmaze.plain("<p>A <b>new</b> show.</p>"), "A new show.")
        self.assertEqual(tvmaze.plain('<script>evil()</script><p>Safe</p>'), "Safe")

    def test_allow_only_tvmaze_images(self):
        self.assertEqual(
            tvmaze.image_url({"medium":"https://static.tvmaze.com/uploads/images/medium_portrait/1.jpg"}),
            "https://static.tvmaze.com/uploads/images/medium_portrait/1.jpg")
        self.assertIsNone(tvmaze.image_url({"medium":"https://other.example.org/no.jpg"}))

    def test_automatic_show_match_without_token(self):
        responses = {
            "/search/shows": [{"show":{
                "id":44, "name":"Severance", "premiered":"2022-02-18",
                "summary":"<p>Office thriller</p>",
                "url":"https://www.tvmaze.com/shows/44/severance",
                "image":{"medium":"https://static.tvmaze.com/uploads/images/medium_portrait/1.jpg"},
            }}],
            "/shows/44/seasons": [{"number":1,"name":"Season 1","image":None,
                                   "episodeOrder":9}],
        }
        with patch.object(tvmaze, "_get", side_effect=lambda path, query=None: responses.get(path)), \
             patch.object(tvmaze,"_cache_get",return_value=None), \
             patch.object(tvmaze,"_cache_put") as cache:
            result = tvmaze.show_metadata("Severance", 2022)
        self.assertEqual(result["source"], "TVmaze")
        self.assertEqual(result["overview"], "Office thriller")
        self.assertEqual(result["tvmaze_id"], 44)
        self.assertEqual(result["seasons"][0]["number"], 1)
        cache.assert_called_once()

    def test_no_incorrect_show_matched(self):
        with patch.object(tvmaze, "_get", return_value=[
            {"show":{"id":42,"name":"Severance: The Aftershow"}}
        ]),patch.object(tvmaze,"_cache_get",return_value=None),patch.object(tvmaze,"_cache_put"):
            self.assertEqual(tvmaze.show_metadata("Severance"), {})

    def test_automatic_episode_synopsis_without_token(self):
        episodes=[{"season":2,"number":1,"name":"Hello, Ms. Cobel",
                   "summary":"<p>The next chapter.</p>","airdate":"2025-01-17",
                   "runtime":55,
                   "image":{"medium":"https://static.tvmaze.com/uploads/images/medium_landscape/2.jpg"}}]
        with patch.object(tvmaze,"_get", return_value=episodes), \
             patch.object(tvmaze,"_cache_get",return_value=None), \
             patch.object(tvmaze,"_cache_put"):
            data=tvmaze.season_metadata(44,2)
        self.assertEqual(data["episodes"]["1"]["overview"],"The next chapter.")
        self.assertTrue(data["episodes"]["1"]["still_url"].startswith("https://static.tvmaze.com/"))

    def test_tmdb_not_required(self):
        with patch.object(tv,"token_status", return_value=False), \
             patch.object(tv,"tvmaze_show_metadata",return_value={"source":"TVmaze"}) as automatic, \
             patch.object(tv,"tmdb_show_metadata") as optional:
            self.assertEqual(tv.show_metadata("Severance"),{"source":"TVmaze"})
        automatic.assert_called_once_with("Severance",None)
        optional.assert_not_called()

    def test_optional_tmdb_can_be_used(self):
        with patch.object(tv,"token_status",return_value=True), \
             patch.object(tv,"tmdb_show_metadata",return_value={"source":"TMDB"}) as optional, \
             patch.object(tv,"tvmaze_show_metadata") as automatic:
            self.assertEqual(tv.show_metadata("Severance"),{"source":"TMDB"})
        optional.assert_called_once_with("Severance",None)
        automatic.assert_not_called()

if __name__=="__main__":
    unittest.main()
