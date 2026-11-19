"""The Yarr account database schema: baseline plus additive migrations.

Rebuilds the live D1 schema in SQLite, applies the migrations to a database that
already holds a Google user, and checks that nothing breaks for the deployed Worker.
"""
import sqlite3
import unittest
from pathlib import Path

MIGRATIONS = Path(__file__).resolve().parents[1] / "cloudflare/yarr/migrations"


def connect():
    db = sqlite3.connect(":memory:")
    db.execute("PRAGMA foreign_keys=ON")
    return db


def apply(db, name):
    db.executescript((MIGRATIONS / name).read_text())


class AccountSchemaTests(unittest.TestCase):
    def setUp(self):
        self.db = connect()
        apply(self.db, "0001_baseline.sql")
        self.db.execute("INSERT INTO users(id,google_sub,email) VALUES('u1','g-123','a@example.com')")
        self.db.execute("INSERT INTO sessions(id,user_id,token_hash,expires_at) VALUES('s1','u1','h1','2099-01-01')")
        self.db.execute("INSERT INTO servers(id,owner_user_id,display_name) VALUES('sv1','u1','Home')")
        apply(self.db, "0002_identities_devices_billing.sql")

    def test_existing_google_user_gets_an_identity_and_keeps_everything(self):
        row = self.db.execute("SELECT provider,subject,user_id,email FROM user_identities").fetchall()
        self.assertEqual(row, [("google", "g-123", "u1", "a@example.com")])
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0], 1)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM servers").fetchone()[0], 1)
        self.assertEqual(self.db.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall(), [(1,), (2,)])

    def test_the_current_worker_statements_still_work(self):
        # Statements copied from cloudflare/yarr/worker.js.
        self.db.execute("INSERT INTO users(id,google_sub,email,display_name,avatar_url) VALUES(?,?,?,?,?) "
                        "ON CONFLICT(google_sub) DO UPDATE SET email=excluded.email", ("u2", "g-2", "b@example.com", "B", None))
        self.db.execute("INSERT INTO sessions(id,user_id,token_hash,expires_at) VALUES(?,?,?,datetime('now','+7 days'))", ("s2", "u2", "h2"))
        self.db.execute("INSERT INTO servers(id,owner_user_id,display_name,status,server_identity,connection_secret_hash) "
                        "VALUES('sv2','u2','Yarr Server','paired','ident','secret')")

    def test_an_apple_only_account_fits(self):
        self.db.execute("INSERT INTO users(id,google_sub,email) VALUES('u3','none:u3',NULL)")
        self.db.execute("INSERT INTO user_identities(provider,subject,user_id,is_private_relay) VALUES('apple','001.abc','u3',1)")
        with self.assertRaises(sqlite3.IntegrityError):  # one Apple subject = one account
            self.db.execute("INSERT INTO user_identities(provider,subject,user_id) VALUES('apple','001.abc','u1')")
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("INSERT INTO user_identities(provider,subject,user_id) VALUES('github','x','u1')")

    def test_tv_sign_in_request_and_device_credential(self):
        self.db.execute("INSERT INTO device_login_requests(device_code_hash,user_code_hash,expires_at) VALUES('d','u','2099-01-01')")
        with self.assertRaises(sqlite3.IntegrityError):  # codes cannot collide
            self.db.execute("INSERT INTO device_login_requests(device_code_hash,user_code_hash,expires_at) VALUES('d2','u','2099-01-01')")
        self.db.execute("UPDATE device_login_requests SET status='approved',user_id='u1' WHERE user_code_hash='u'")
        self.db.execute("INSERT INTO devices(id,owner_user_id,device_name,device_type,token_hash) VALUES('dev1','u1','Living room','google_tv','t1')")
        with self.assertRaises(sqlite3.IntegrityError):  # a credential identifies one device
            self.db.execute("INSERT INTO devices(id,owner_user_id,device_name,device_type,token_hash) VALUES('dev2','u1','Den','google_tv','t1')")
        # Uncredentialed rows (the old empty table's shape) are still allowed.
        self.db.execute("INSERT INTO devices(id,owner_user_id,device_name,device_type) VALUES('dev3','u1','Phone','android')")
        self.db.execute("INSERT INTO devices(id,owner_user_id,device_name,device_type) VALUES('dev4','u1','Phone 2','android')")

    def test_subscriptions_are_one_per_provider_subscription(self):
        add = ("INSERT INTO subscriptions(id,user_id,status,provider,provider_subscription_id) "
               "VALUES(?,?,?,?,?)")
        self.db.execute(add, ("p1", "u1", "active", "stripe", "sub_1"))
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute(add, ("p2", "u1", "active", "stripe", "sub_1"))
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute(add, ("p3", "u1", "paused", "stripe", "sub_9"))
        self.db.execute("INSERT INTO billing_events(provider,event_id,event_type) VALUES('stripe','evt_1','invoice.paid')")
        with self.assertRaises(sqlite3.IntegrityError):  # a replayed webhook is rejected
            self.db.execute("INSERT INTO billing_events(provider,event_id,event_type) VALUES('stripe','evt_1','invoice.paid')")

    def test_deleting_an_account_removes_its_data_but_keeps_the_audit_trail(self):
        self.db.execute("INSERT INTO subscriptions(id,user_id,status,provider) VALUES('p1','u1','active','manual')")
        self.db.execute("INSERT INTO devices(id,owner_user_id,device_name,device_type) VALUES('d1','u1','TV','google_tv')")
        self.db.execute("INSERT INTO audit_log(user_id,event) VALUES('u1','signed_in')")
        self.db.execute("DELETE FROM users WHERE id='u1'")
        for table in ("user_identities", "sessions", "servers", "devices", "subscriptions"):
            self.assertEqual(self.db.execute("SELECT COUNT(*) FROM " + table).fetchone()[0], 0, table)
        self.assertEqual(self.db.execute("SELECT user_id FROM audit_log").fetchall(), [(None,)])


if __name__ == "__main__":
    unittest.main()
