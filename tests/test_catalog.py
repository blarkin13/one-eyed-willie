import unittest
from server.catalog import episode_info, movie_info, pretty

class CatalogTests(unittest.TestCase):
    def test_movies(self):
        x = movie_info("/media/Media/Movies/Alien (1979)/Alien.1979.mkv", "/media/Media/Movies")
        self.assertEqual(x["title"], "Alien")
        self.assertEqual(x["year"], 1979)

    def test_tv_episode(self):
        x = episode_info("/media/Media/TV/Severance/Season 01/Severance.S01E02.mkv", "/media/Media/TV")
        self.assertEqual(x["title"], "Severance")
        self.assertEqual((x["season"], x["episode"]), (1, 2))

    def test_title_cleanup(self):
        self.assertEqual(pretty("The.Matrix.1080p.BluRay"), "The Matrix")

if __name__ == "__main__":
    unittest.main()
