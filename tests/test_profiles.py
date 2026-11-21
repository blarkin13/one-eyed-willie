"""Household profiles: Family, the owner and everyone else on one server."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

from server import library, profiles, remote_access as ra
from server.main import app
from tests.test_remote_access import Keys, SERVER, make_pass

HTML = {"Accept": "text/html"}


class ProfileTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.key = Ed25519PrivateKey.generate()
        for p in (patch.object(library, "DB_PATH", Path(temp.name) / "library.sqlite3"),
                  patch.object(ra, "KEYS", Keys({"k1": self.key.public_key()})),
                  patch.object(ra, "get_server_id", lambda: SERVER)):
            p.start()
            self.addCleanup(p.stop)
        profiles._attempts.clear()
        with library.db() as conn:
            conn.execute("INSERT INTO libraries(id,name,kind,path) VALUES(1,'Movies','movies','/media/Movies')")
            conn.execute("INSERT INTO libraries(id,name,kind,path) VALUES(2,'Music','music','/media/Music')")
            conn.execute("INSERT INTO media(id,library_id,path,title,size,mtime_ns,added_at) "
                         "VALUES(1,1,'/media/Movies/Arrival (2016)/Arrival (2016).mkv','Arrival',1,1,'2026-11-15')")
        self.client = TestClient(app)

    def setup_household(self, kind="adult"):
        r = self.client.post("/api/profiles/setup", json={"owner_name": "Brian", "person": {"name": "Sam", "kind": kind}})
        self.assertEqual(r.status_code, 200, r.text)
        return {p["name"]: p for p in r.json()["profiles"]}

    def choose(self, pid, pin=None, client=None):
        c = client or TestClient(app)
        r = c.post("/api/profiles/choose", json={"id": pid, "pin": pin})
        return c, r

    def test_one_person_changes_nothing(self):
        self.assertEqual(self.client.get("/api/profiles").json()["active"], False)
        page = self.client.get("/", headers=HTML, follow_redirects=False)
        self.assertNotEqual(page.status_code, 303)
        viewer = self.client.get("/api/viewer").json()
        self.assertEqual((viewer["role"], viewer["profile"], viewer["profiles_active"]), ("owner", None, False))

    def test_adding_a_person_turns_on_who_is_watching(self):
        people = self.setup_household()
        self.assertEqual(list(people), ["Family", "Brian", "Sam"])
        self.assertTrue(people["Brian"]["is_owner"])
        fresh = TestClient(app)
        page = fresh.get("/movies?library_id=1", headers=HTML, follow_redirects=False)
        self.assertEqual((page.status_code, page.headers["location"]), (303, "/who?next=%2Fmovies%3Flibrary_id%3D1"))
        self.assertEqual(fresh.get("/who").status_code, 200)
        self.assertEqual(fresh.get("/assets/shell.js").status_code, 200)
        # Older apps' native calls carry no profile and count as Family.
        self.assertEqual(fresh.get("/api/viewer").json()["profile"], None)
        c, r = self.choose(people["Sam"]["id"])
        self.assertEqual(r.status_code, 200)
        self.assertIn("yarr_profile=", r.headers["set-cookie"])
        self.assertEqual(r.headers["x-yarr-profile-set"], r.json()["token"])
        self.assertEqual(c.get("/api/viewer").json()["profile"]["name"], "Sam")
        self.assertEqual(c.get("/", headers=HTML, follow_redirects=False).status_code, 200)
        # app.yarr.media's service worker sends the token as a header instead.
        token = r.json()["token"]
        self.assertEqual(TestClient(app).get("/api/viewer", headers={"x-yarr-profile": token}).json()["name"], "Sam")
        forged = token[:-3] + ("AAA" if not token.endswith("AAA") else "BBB")
        self.assertIsNone(TestClient(app).get("/api/viewer", headers={"x-yarr-profile": forged}).json()["profile"])

    def test_each_person_has_their_own_history_and_settings(self):
        people = self.setup_household()
        sam, _ = self.choose(people["Sam"]["id"])
        fam, _ = self.choose(people["Family"]["id"])
        sam.put("/api/playback/progress", json={"media_id": 1, "position_seconds": 600, "duration_seconds": 6000})
        self.assertEqual(sam.get("/api/playback/movie?media_id=1").status_code in (200, 404), True)
        with library.db() as conn:
            rows = {r["viewer"]: r["position_seconds"] for r in conn.execute("SELECT viewer,position_seconds FROM playback_progress")}
        self.assertEqual(rows, {"p:" + people["Sam"]["id"]: 600})
        sam.put("/api/settings/playback", json={"auto_play_next": True})
        self.assertTrue(sam.get("/api/settings/playback").json()["auto_play_next"])
        self.assertFalse(fam.get("/api/settings/playback").json()["auto_play_next"])
        sam.put("/api/settings/tv-appearance", json={"selection_color": "#EF4444"})
        self.assertEqual(sam.get("/api/settings/tv-appearance").json()["selection_color"], "#EF4444")
        self.assertNotEqual(fam.get("/api/settings/tv-appearance").json()["selection_color"], "#EF4444")
        sam.put("/api/settings/subtitle-appearance", json={"size": "large"})
        self.assertEqual(sam.get("/api/settings/subtitle-appearance").json()["size"], "large")
        self.assertEqual(fam.get("/api/settings/subtitle-appearance").json()["size"], "normal")
        # Removing a person can delete their history too.
        self.client.delete("/api/profiles/" + people["Sam"]["id"] + "?forget=true")
        with library.db() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM playback_progress").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM app_settings WHERE key LIKE 'p:%'").fetchone()[0], 0)
        # Down to one person: no picker again.
        self.assertFalse(self.client.get("/api/profiles").json()["active"])

    def test_optional_pins(self):
        people = self.setup_household()
        sam = people["Sam"]["id"]
        self.client.put(f"/api/profiles/{sam}/pin", json={"pin": "1234"})
        _, r = self.choose(sam)
        self.assertEqual((r.status_code, r.json()["detail"]), (403, "pin_required"))
        _, r = self.choose(sam, "9999")
        self.assertEqual((r.status_code, r.json()["detail"]), (403, "Wrong PIN."))
        _, r = self.choose(sam, "1234")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.client.put(f"/api/profiles/{sam}/pin", json={"pin": "12"}).status_code, 422)
        # Too many wrong tries lock that PIN for a while.
        for _ in range(5):
            self.choose(sam, "0000")
        _, r = self.choose(sam, "1234")
        self.assertEqual(r.status_code, 429)

    def test_kid_profiles_stay_put_and_only_watch(self):
        people = self.setup_household(kind="kid")
        self.client.put("/api/profiles/parent-pin/set", json={"pin": "4321"})
        kid, r = self.choose(people["Sam"]["id"])
        self.assertEqual(r.status_code, 200)
        listing = kid.get("/api/profiles").json()
        self.assertTrue(listing["locked"])
        self.assertFalse(listing["can_manage"])
        _, r = self.choose(people["Brian"]["id"], client=kid)
        self.assertEqual(r.status_code, 403)
        # Owner tools are out of reach.
        self.assertEqual(kid.get("/settings/people", headers=HTML, follow_redirects=False).headers["location"], "/")
        self.assertEqual(kid.put("/api/settings/sidebar", json={"order": [], "hidden": []}).status_code, 403)
        self.assertEqual(kid.post("/api/profiles", json={"name": "X"}).status_code, 403)
        self.assertEqual(kid.get("/api/viewer").json()["role"], "kid")
        self.assertEqual(kid.get("/api/watch/1/status").status_code != 403, True)
        _, r = self.choose(people["Brian"]["id"], "4321", client=kid)
        self.assertEqual(r.status_code, 200)

    def test_parent_pin_protects_changes(self):
        people = self.setup_household()
        self.client.put("/api/profiles/parent-pin/set", json={"pin": "4321"})
        self.assertEqual(self.client.post("/api/profiles", json={"name": "Alex"}).status_code, 403)
        ok = self.client.post("/api/profiles", json={"name": "Alex"}, headers={"x-yarr-parent-pin": "4321"})
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(self.client.post("/api/profiles/parent-pin/check", json={"pin": "1111"}).status_code, 403)
        self.assertEqual(self.client.post("/api/profiles/parent-pin/check", json={"pin": "4321"}).status_code, 200)
        self.assertEqual(self.client.delete("/api/profiles/" + people["Family"]["id"],
                                            headers={"x-yarr-parent-pin": "4321"}).status_code, 409)

    def test_barnacles_are_not_household_profiles(self):
        self.setup_household()
        h = {"X-Yarr-Remote": "1", "Authorization": "Yarr-Pass " + make_pass(self.key, role="barnacle", sub="f", lib=[1], nm="Friend")}
        self.assertEqual(self.client.get("/api/profiles", headers=h).json()["profiles"], [])
        self.assertEqual(self.client.get("/api/viewer", headers=h).json()["role"], "barnacle")
        self.assertEqual(self.client.get("/", headers={**h, **HTML}, follow_redirects=False).status_code, 200)

    def test_owner_away_from_home_picks_a_profile_too(self):
        people = self.setup_household()
        h = {"X-Yarr-Remote": "1", "Authorization": "Yarr-Pass " + make_pass(self.key)}
        page = self.client.get("/", headers={**h, **HTML}, follow_redirects=False)
        self.assertEqual(page.status_code, 303)
        c = TestClient(app)
        r = c.post("/api/profiles/choose", json={"id": people["Brian"]["id"]}, headers=h)
        self.assertEqual(c.get("/api/viewer", headers={**h, "x-yarr-profile": r.json()["token"]}).json()["name"], "Brian")


if __name__ == "__main__":
    unittest.main()
