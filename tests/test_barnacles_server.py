"""Barnacles on the home server: people the owner shares with through yarr.media.

A barnacle pass lets someone watch and listen to the libraries the owner
chose, with their own watch history, and nothing else. Owner passes and the
home network are unchanged.
"""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

from server import library, remote_access as ra
from server.main import app
from tests.test_remote_access import Keys, SERVER, make_pass

REMOTE = {"X-Yarr-Remote": "1"}


class BarnacleServerTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        patches = [patch.object(library, "DB_PATH", Path(temp.name) / "library.sqlite3")]
        self.key = Ed25519PrivateKey.generate()
        patches += [patch.object(ra, "KEYS", Keys({"k1": self.key.public_key()})),
                    patch.object(ra, "get_server_id", lambda: SERVER)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        with library.db() as conn:
            for lib_id, name, kind in ((1, "Movies", "movies"), (2, "TV", "tv"), (3, "Private", "movies"), (4, "Music", "music")):
                conn.execute("INSERT INTO libraries(id,name,kind,path) VALUES(?,?,?,?)", (lib_id, name, kind, f"/media/{name}"))
            for media_id, lib_id, path in ((1, 1, "/media/Movies/Arrival (2016)/Arrival (2016).mkv"),
                                           (2, 2, "/media/TV/Example/Season 01/Example.S01E01.mkv"),
                                           (3, 3, "/media/Private/Secret (2020)/Secret (2020).mkv")):
                conn.execute("INSERT INTO media(id,library_id,path,title,size,mtime_ns,added_at) "
                             "VALUES(?,?,?,?,100,100,'2026-11-15 10:00:00')", (media_id, lib_id, path, Path(path).stem))
            conn.commit()
        self.client = TestClient(app, base_url="https://76-183-183-204.sslip.io")

    def headers(self, role="barnacle", lib=(1, 2), sub="friend-1"):
        claims = {"role": role, "sub": sub}
        if role == "barnacle":
            claims.update(lib=list(lib), nm="Friend")
        return {**REMOTE, "Authorization": "Yarr-Pass " + make_pass(self.key, **claims)}

    # ---- What a barnacle can reach -------------------------------------------------
    def test_barnacle_sees_only_their_libraries(self):
        h = self.headers()
        self.assertEqual(self.client.get("/api/viewer", headers=h).json(),
                         {"role": "barnacle", "name": "Friend", "libraries": [1, 2]})
        libs = self.client.get("/api/libraries", headers=h).json()
        self.assertEqual([l["id"] for l in libs], [1, 2])
        self.assertTrue(all("path" not in l and "folders" not in l for l in libs))
        movies = self.client.get("/api/catalog/all?kind=movies", headers=h).json()["items"]
        self.assertEqual({i["library_id"] for i in movies}, {1})
        # The owner (home network, no pass) still sees everything.
        self.assertEqual(len(self.client.get("/api/libraries").json()), 4)
        owner_movies = self.client.get("/api/catalog/all?kind=movies").json()["items"]
        self.assertEqual({i["library_id"] for i in owner_movies}, {1, 3})
        self.assertEqual(self.client.get("/api/viewer").json()["role"], "owner")

    def test_barnacle_cannot_reach_other_libraries_or_titles(self):
        h = self.headers()
        for method, url in (("GET", "/api/watch/3/status"), ("GET", "/api/watch/3/stream"),
                            ("POST", "/api/stream/hls/start/3"), ("GET", "/api/movies/details?library_id=3&key=x"),
                            ("GET", "/api/tv/next?media_id=3"), ("PUT", "/api/watch/3/watched"),
                            ("GET", "/api/libraries/3/icon.png"), ("GET", "/api/music/catalog?library_id=4"),
                            ("GET", "/api/watch/999/status")):
            with self.subTest(url=url):
                self.assertEqual(self.client.request(method, url, headers=h, json={"watched": True}).status_code, 403)
        progress = self.client.put("/api/playback/progress", headers=h,
                                   json={"media_id": 3, "position_seconds": 10, "duration_seconds": 100})
        self.assertEqual(progress.status_code, 404)
        page = self.client.get("/movie?library_id=3&key=x", headers={**h, "Accept": "text/html"}, follow_redirects=False)
        self.assertEqual((page.status_code, page.headers["location"]), (303, "/"))

    def test_barnacle_cannot_use_owner_tools(self):
        h = self.headers(lib=(1, 2, 3, 4))
        for method, url in (("GET", "/settings/integrations"), ("GET", "/settings/libraries"), ("GET", "/integrations"),
                            ("GET", "/radarr"), ("GET", "/sabnzbd"), ("GET", "/services"), ("GET", "/explore"),
                            ("POST", "/api/libraries"), ("DELETE", "/api/libraries/1"), ("PATCH", "/api/libraries/1"),
                            ("POST", "/api/libraries/1/scan"), ("PUT", "/api/libraries/1/icon.png"),
                            ("PUT", "/api/settings/sidebar"), ("PUT", "/api/settings/playback"),
                            ("GET", "/api/arr/connections"), ("GET", "/api/sabnzbd/status"), ("POST", "/api/sabnzbd/queue"),
                            ("GET", "/api/media/actions"), ("POST", "/api/media/actions/delete"),
                            ("GET", "/api/metadata/settings"), ("PUT", "/api/movies/match?library_id=1&key=x"),
                            ("GET", "/api/remote/settings"), ("POST", "/api/yarr/pair/start"), ("GET", "/api/yarr/pair/status"),
                            ("POST", "/api/plex/import"), ("POST", "/api/maintenance/run"), ("GET", "/api/folders"),
                            ("GET", "/api/stream/subtitles/1/search"), ("POST", "/api/stream/subtitles/1/download"),
                            ("GET", "/docs"), ("GET", "/openapi.json"), ("POST", "/api/catalog/metadata/refresh"),
                            ("GET", "/api/libraries/1/media"), ("POST", "/api/yarr/direct/offer")):
            with self.subTest(method=method, url=url):
                r = self.client.request(method, url, headers=h, follow_redirects=False)
                self.assertIn(r.status_code, (303, 403), f"{method} {url} -> {r.status_code}")
        # Owner passes keep full access.
        self.assertEqual(self.client.get("/api/remote/settings", headers=self.headers(role="owner")).status_code, 200)

    # ---- Separate watch history -------------------------------------------------------
    @staticmethod
    def progress(viewer, media_id):
        with library.db() as conn:
            row = conn.execute("SELECT position_seconds,completed FROM playback_progress WHERE viewer=? AND media_id=?",
                               (viewer, media_id)).fetchone()
        return tuple(row) if row else None

    def test_each_person_has_their_own_history(self):
        friend, other = self.headers(sub="friend-1"), self.headers(sub="friend-2")
        save = self.client.put("/api/playback/progress", headers=friend,
                               json={"media_id": 1, "position_seconds": 600, "duration_seconds": 7200})
        self.assertEqual(save.status_code, 200, save.text)
        self.assertEqual(self.progress("u:friend-1", 1), (600.0, 0))
        self.assertIsNone(self.progress("", 1), "owner unaffected")
        self.assertIsNone(self.progress("u:friend-2", 1))
        cw = lambda h=None: [c["media_id"] for c in self.client.get("/api/home", headers=h or {}).json()["continue_watching"]]
        self.assertEqual(cw(friend), [1])
        self.assertEqual(cw(), [])
        # Owner marks it watched; the barnacle's resume point stays.
        with patch("server.playback._item", lambda media_id: (None, None)):
            self.assertEqual(self.client.put("/api/watch/1/watched", json={"watched": True}).status_code, 200)
            self.assertEqual(self.progress("", 1)[1], 1)
            self.assertEqual(self.progress("u:friend-1", 1), (600.0, 0))
            self.assertEqual(self.client.put("/api/watch/1/watched", headers=friend, json={"watched": True}).status_code, 200)
            self.assertEqual(self.progress("u:friend-1", 1)[1], 1)
            self.assertEqual(self.client.put("/api/watch/1/watched", headers=friend, json={"watched": False}).status_code, 200)
            self.assertIsNone(self.progress("u:friend-1", 1))
            self.assertEqual(self.progress("", 1)[1], 1, "owner's watched mark stays")
        # Dismissing from Continue Watching is per person too.
        self.client.put("/api/playback/progress", json={"media_id": 2, "position_seconds": 60, "duration_seconds": 1800})
        self.client.put("/api/playback/progress", headers=friend, json={"media_id": 2, "position_seconds": 90, "duration_seconds": 1800})
        self.assertEqual(self.client.post("/api/home/continue/2/dismiss", headers=friend).status_code, 200)
        self.assertNotIn(2, cw(friend))
        self.assertIn(2, cw())


class PassRuleTests(unittest.TestCase):
    def setUp(self):
        self.key = Ed25519PrivateKey.generate()
        self.keys = Keys({"k1": self.key.public_key()})

    def check(self, **claims):
        return ra.verify_pass(make_pass(self.key, **claims), keys=self.keys, server_id=SERVER)

    def test_barnacle_passes_need_an_account_and_a_library_list(self):
        self.assertEqual(self.check(role="barnacle", lib=[1, 2], nm="F")["lib"], [1, 2])
        for bad in ({"role": "barnacle"}, {"role": "barnacle", "lib": "1"}, {"role": "barnacle", "lib": [True]},
                    {"role": "barnacle", "lib": [1], "sub": ""}, {"role": "barnacle", "lib": ["1"]}):
            with self.subTest(bad=bad), self.assertRaises(ra.PassError):
                self.check(**bad)
        for role in ("admin", "guest", None):
            with self.subTest(role=role), self.assertRaises(ra.PassError):
                self.check(role=role)

    def test_heartbeat_sends_library_names_and_kinds_only(self):
        from server import yarr_pairing as yp
        sent = {}
        with tempfile.TemporaryDirectory() as temp, patch.object(library, "DB_PATH", Path(temp) / "l.sqlite3"), \
                patch.object(yp, "_read", lambda: {"status": "paired", "poll_secret": "s"}), \
                patch.object(yp, "_save", lambda record: None), \
                patch.object(yp, "_cloud", lambda path, data=None, secret=None: sent.update(data=data) or {}):
            with library.db() as conn:
                conn.execute("INSERT INTO libraries(id,name,kind,path) VALUES(1,'Movies','movies','/srv/data/media/movies')")
                conn.commit()
            self.assertTrue(yp.report_heartbeat())
        self.assertEqual(sent["data"], {"libraries": [{"id": 1, "name": "Movies", "kind": "movies"}]})


class UpgradeTests(unittest.TestCase):
    def test_existing_history_becomes_the_owners(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "library.sqlite3"
            old = sqlite3.connect(path)
            old.execute("CREATE TABLE playback_progress (media_id INTEGER PRIMARY KEY, position_seconds REAL NOT NULL, "
                        "duration_seconds REAL NOT NULL, completed INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
            old.execute("CREATE TABLE continue_watching_hidden (kind TEXT NOT NULL, library_id INTEGER NOT NULL, media_key TEXT NOT NULL, "
                        "PRIMARY KEY (kind,library_id,media_key))")
            old.execute("INSERT INTO playback_progress VALUES(7,120,3600,0,'2026-11-01 10:00:00'),(8,0,0,1,'2026-11-02 10:00:00')")
            old.execute("INSERT INTO continue_watching_hidden VALUES('tv',2,'Show')")
            old.commit()
            old.close()
            with patch.object(library, "DB_PATH", path):
                with library.db() as conn:
                    rows = [tuple(r) for r in conn.execute(
                        "SELECT viewer,media_id,position_seconds,completed FROM playback_progress ORDER BY media_id")]
                    hidden = [tuple(r) for r in conn.execute("SELECT viewer,kind,library_id,media_key FROM continue_watching_hidden")]
                    version = conn.execute("PRAGMA user_version").fetchone()[0]
            self.assertEqual(rows, [("", 7, 120.0, 0), ("", 8, 0.0, 1)])
            self.assertEqual(hidden, [("", "tv", 2, "Show")])
            self.assertEqual(version, library.SCHEMA_VERSION)


if __name__ == "__main__":
    unittest.main()
