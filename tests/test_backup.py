"""Encrypted watch-history backups: what goes in, encryption, and restoring on another install."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

from server import backup, library, profiles
from server.main import app


def make_db(path, libs, media):
    with patch.object(library, "DB_PATH", path):
        with library.db() as conn:
            for lib_id, name, kind, root in libs:
                conn.execute("INSERT INTO libraries(id,name,kind,path) VALUES(?,?,?,?)", (lib_id, name, kind, root))
            for media_id, lib_id, file in media:
                conn.execute("INSERT INTO media(id,library_id,path,title,size,mtime_ns,added_at) VALUES(?,?,?,?,1,1,'2026-11-15')",
                             (media_id, lib_id, file, Path(file).stem))


class SealTests(unittest.TestCase):
    def test_only_the_recovery_code_opens_a_backup(self):
        code = backup.new_code()
        self.assertRegex(code, r"^[A-Z2-9]{5}(-[A-Z2-9]{5}){4}$")
        salt = b"s" * 16
        blob = backup.seal({"v": 1, "hello": "world"}, backup.derive(code, salt), salt)
        self.assertEqual(blob[:4], b"YRB1")
        self.assertNotIn(b"world", blob)
        data, got_salt = backup.open_sealed(blob, code.lower().replace("-", " "))
        self.assertEqual((data["hello"], got_salt), ("world", salt))
        with self.assertRaises(HTTPException) as wrong:
            backup.open_sealed(blob, backup.new_code())
        self.assertEqual(wrong.exception.status_code, 403)
        with self.assertRaises(HTTPException):
            backup.open_sealed(blob, "short")


class RoundTripTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.old = Path(temp.name) / "old.sqlite3"
        self.new = Path(temp.name) / "new.sqlite3"
        make_db(self.old, [(1, "Movies", "movies", "/media/Movies"), (2, "TV", "tv", "/media/TV")],
                [(10, 1, "/media/Movies/Arrival (2016)/Arrival (2016).mkv"),
                 (11, 2, "/media/TV/Bluey/Season 01/Bluey.S01E01.mkv")])
        # A reinstall: same folders, different ids (and the TV folder moved disks).
        make_db(self.new, [(7, "TV", "tv", "/mnt/big/TV"), (8, "Movies", "movies", "/media/Movies")],
                [(70, 7, "/mnt/big/TV/Bluey/Season 01/Bluey.S01E01.mkv"),
                 (80, 8, "/media/Movies/Arrival (2016)/Arrival (2016).mkv")])

    def test_history_profiles_and_settings_come_back_on_a_new_install(self):
        with patch.object(library, "DB_PATH", self.old):
            client = TestClient(app)
            r = client.post("/api/profiles/setup", json={"owner_name": "Brian", "person": {"name": "Sam", "kind": "kid"}})
            sam = next(p["id"] for p in r.json()["profiles"] if p["name"] == "Sam")
            client.put(f"/api/profiles/{sam}/rules", json={"max_level": 1, "libraries": [2]})
            with library.db() as conn:
                conn.execute("INSERT INTO playback_progress(viewer,media_id,position_seconds,duration_seconds,completed,updated_at) "
                             "VALUES('',10,600,6000,0,'2026-11-20 10:00:00'),(?,11,0,700,1,'2026-11-19 09:00:00')", ("p:" + sam,))
                conn.execute("INSERT INTO app_settings(key,value) VALUES(?, 'true')", ("p:" + sam + "|auto_play_next",))
                conn.execute("INSERT INTO app_settings(key,value) VALUES('radarr_api_key','secret-key')")
            data = backup.collect()
        self.assertNotIn("secret-key", json.dumps(data))
        with patch.object(library, "DB_PATH", self.new):
            with library.db() as conn:   # the new install already has newer progress for Arrival
                conn.execute("INSERT INTO playback_progress(viewer,media_id,position_seconds,duration_seconds,completed,updated_at) "
                             "VALUES('',80,900,6000,0,'2026-11-21 10:00:00')")
            counts = backup.apply(json.loads(json.dumps(data)))
            with library.db() as conn:
                rows = {(r["viewer"], r["media_id"]): (r["position_seconds"], r["completed"])
                        for r in conn.execute("SELECT * FROM playback_progress")}
                setting = conn.execute("SELECT value FROM app_settings WHERE key=?", ("p:" + sam + "|auto_play_next",)).fetchone()
            self.assertEqual(rows, {("", 80): (900, 0), ("p:" + sam, 70): (0, 1)})
            self.assertEqual(counts["profiles"], 3)
            self.assertEqual(setting["value"], "true")
            home = profiles.household()
            self.assertTrue(home.active)
            self.assertEqual(home.by_id[sam].rules["libraries"], [7], "kids' library limits follow the library name")


class ApiTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        p = patch.object(library, "DB_PATH", Path(temp.name) / "l.sqlite3")
        p.start()
        self.addCleanup(p.stop)
        self.cloud = {}

        def fake_cloud(method, path, body=None, *, raw=False):
            if method == "PUT":
                self.cloud["srv-1234567"] = body
                return {"stored": True}
            if method == "DELETE":
                self.cloud.clear()
                return {"deleted": True}
            if path == "/api/connection/backups":
                return {"backups": [{"id": k, "server_name": "Home", "size": len(v)} for k, v in self.cloud.items()]}
            key = path.rsplit("/", 1)[1]
            if key not in self.cloud:
                raise HTTPException(404, "No backup found.")
            return self.cloud[key]
        for q in (patch.object(backup, "_cloud", fake_cloud),
                  patch.object(backup, "_credential", lambda: ("https://yarr.media", "s" * 48))):
            q.start()
            self.addCleanup(q.stop)
        self.client = TestClient(app)

    def test_turn_on_back_up_and_restore(self):
        self.assertFalse(self.client.get("/api/backup").json()["enabled"])
        on = self.client.post("/api/backup/enable").json()
        code = on["recovery_code"]
        self.assertTrue(on["enabled"])
        self.assertIsNotNone(on["last_backup"])
        self.assertIn("srv-1234567", self.cloud)
        self.assertEqual(self.client.post("/api/backup/now").status_code, 200)
        listed = self.client.get("/api/backup/available").json()["backups"]
        self.assertEqual([b["id"] for b in listed], ["srv-1234567"])
        bad = self.client.post("/api/backup/restore", json={"id": "srv-1234567", "code": backup.new_code()})
        self.assertEqual(bad.status_code, 403)
        good = self.client.post("/api/backup/restore", json={"id": "srv-1234567", "code": code})
        self.assertEqual(good.status_code, 200, good.text)
        self.client.post("/api/backup/disable")
        self.assertEqual(self.cloud, {})
        self.assertFalse(self.client.get("/api/backup").json()["enabled"])

    def test_needs_a_yarr_connection(self):
        with patch.object(backup, "_credential", side_effect=HTTPException(409, "Connect this server to Yarr first")):
            self.assertEqual(self.client.post("/api/backup/enable").status_code, 409)
