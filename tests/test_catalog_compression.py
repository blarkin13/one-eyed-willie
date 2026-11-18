import gzip
import json
import unittest

from fastapi import Request

from server.compression import accepts_gzip, compressed_json


def request(accept_encoding=None):
    headers = [] if accept_encoding is None else [
        (b"accept-encoding", accept_encoding.encode())]
    return Request({"type": "http", "headers": headers})


PAYLOAD = {"total": 3000, "items": [
    {"title": "Movie %d" % i, "key": "k%d" % i, "episodes": [], "seasons": [],
     "poster_url": "/api/artwork/thumb/" + "a" * 64} for i in range(300)]}


class CatalogCompressionTests(unittest.TestCase):
    def test_large_json_is_gzipped_and_round_trips(self):
        response = compressed_json(request("gzip, deflate, br"), PAYLOAD)
        self.assertEqual(response.headers["content-encoding"], "gzip")
        self.assertEqual(response.headers["vary"], "Accept-Encoding")
        self.assertEqual(response.media_type, "application/json")
        self.assertEqual(json.loads(gzip.decompress(response.body)), PAYLOAD)
        plain = len(json.dumps(PAYLOAD))
        self.assertLess(len(response.body), plain * 0.2)

    def test_clients_without_gzip_get_plain_json(self):
        for header in (None, "identity", "br", "gzip;q=0", "gzip; q=0.0"):
            with self.subTest(header=header):
                response = compressed_json(request(header), PAYLOAD)
                self.assertNotIn("content-encoding", response.headers)
                self.assertEqual(json.loads(response.body), PAYLOAD)

    def test_small_payloads_are_not_compressed(self):
        response = compressed_json(request("gzip"), {"total": 0, "items": []})
        self.assertNotIn("content-encoding", response.headers)
        self.assertEqual(json.loads(response.body), {"total": 0, "items": []})

    def test_values_json_cannot_encode_natively_still_serialize(self):
        import datetime
        payload = {"seasons": {3, 1, 2}, "day": datetime.date(2026, 11, 17),
                   "nested": [{"when": datetime.datetime(2026, 1, 2, 3, 4, 5)}]}
        body = json.loads(compressed_json(request(None), payload).body)
        self.assertEqual(sorted(body["seasons"]), [1, 2, 3])
        self.assertEqual(body["day"], "2026-11-17")
        self.assertEqual(body["nested"][0]["when"], "2026-01-02T03:04:05")

    def test_quality_and_wildcard_forms(self):
        self.assertTrue(accepts_gzip("gzip;q=0.8"))
        self.assertTrue(accepts_gzip("*"))
        self.assertTrue(accepts_gzip("deflate, GZIP"))
        self.assertFalse(accepts_gzip("gzip;q=0, deflate"))

    def test_catalog_routes_use_the_helper_and_media_routes_do_not(self):
        source = open("server/main.py").read()
        self.assertEqual(source.count("compressed_json("), 2)
        self.assertNotIn("GZipMiddleware", source)


if __name__ == "__main__":
    unittest.main()
