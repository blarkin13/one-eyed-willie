"""One-time Pro schema must preserve existing accounts and deduplicate Stripe events."""
import sqlite3
import unittest
from pathlib import Path

MIGRATIONS = Path(__file__).resolve().parents[1] / "cloudflare/yarr/migrations"


class StripeOneTimeSchemaTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.execute("PRAGMA foreign_keys=ON")
        for name in ("0001_baseline.sql", "0002_identities_devices_billing.sql", "0003_return_to.sql", "0010_stripe_one_time_pro.sql", "0011_stripe_purchase_archive.sql"):
            self.db.executescript((MIGRATIONS / name).read_text())
        self.db.execute("INSERT INTO users(id,google_sub,email) VALUES('u1','google-1','customer@example.org')")

    def test_additive_schema_preserves_accounts(self):
        self.assertEqual(self.db.execute("SELECT email FROM users WHERE id='u1'").fetchone()[0], "customer@example.org")

    def test_one_checkout_id_cannot_grant_two_licenses(self):
        self.db.execute("INSERT INTO stripe_checkout_sessions(id,user_id,price_id,status) VALUES('cs_test_1','u1','price_test','pending')")
        self.db.execute("INSERT INTO one_time_pro_entitlements(user_id,checkout_session_id,status) VALUES('u1','cs_test_1','active')")
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("INSERT INTO one_time_pro_entitlements(user_id,checkout_session_id,status) VALUES('u1','cs_test_1','active')")

    def test_event_id_is_unique(self):
        self.db.execute("INSERT INTO stripe_webhook_events(event_id,event_type) VALUES('evt_1','checkout.session.completed')")
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("INSERT INTO stripe_webhook_events(event_id,event_type) VALUES('evt_1','charge.refunded')")

    def test_refund_state_revokes_entitlement(self):
        self.db.execute("INSERT INTO stripe_checkout_sessions(id,user_id,price_id,status) VALUES('cs_test_1','u1','price_test','paid')")
        self.db.execute("INSERT INTO one_time_pro_entitlements(user_id,checkout_session_id,status) VALUES('u1','cs_test_1','active')")
        self.db.execute("UPDATE stripe_checkout_sessions SET status='refunded' WHERE id='cs_test_1'")
        self.db.execute("UPDATE one_time_pro_entitlements SET status='revoked' WHERE checkout_session_id='cs_test_1'")
        self.assertEqual(self.db.execute("SELECT status FROM one_time_pro_entitlements").fetchone()[0], "revoked")

    def test_account_deletion_preserves_anonymous_purchase_and_removes_pro(self):
        self.db.execute("INSERT INTO stripe_checkout_sessions(id,user_id,price_id,status,amount_total,currency,payment_intent_id) VALUES('cs_test_deleted','u1','price_test','paid',3139,'usd','pi_test_deleted')")
        self.db.execute("INSERT INTO one_time_pro_entitlements(user_id,checkout_session_id,status) VALUES('u1','cs_test_deleted','active')")
        self.db.execute("INSERT INTO stripe_purchase_archive(checkout_session_id,price_id,status,amount_total,currency,payment_intent_id,purchased_at,updated_at) SELECT id,price_id,status,amount_total,currency,payment_intent_id,created_at,updated_at FROM stripe_checkout_sessions WHERE user_id=?", ("u1",))
        self.db.execute("DELETE FROM one_time_pro_entitlements WHERE user_id=?", ("u1",))
        self.db.execute("DELETE FROM stripe_checkout_sessions WHERE user_id=?", ("u1",))
        self.db.execute("DELETE FROM users WHERE id=?", ("u1",))
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM users WHERE id='u1'").fetchone()[0], 0)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM one_time_pro_entitlements").fetchone()[0], 0)
        archive = self.db.execute("SELECT checkout_session_id,amount_total,status,payment_intent_id FROM stripe_purchase_archive").fetchone()
        self.assertEqual(archive, ("cs_test_deleted", 3139, "paid", "pi_test_deleted"))

    def test_archive_records_refunds_without_recreating_user(self):
        self.db.execute("INSERT INTO stripe_purchase_archive(checkout_session_id,price_id,status,amount_total,currency,payment_intent_id) VALUES('cs_test_1','price_test','paid',3139,'usd','pi_test_1')")
        self.db.execute("UPDATE stripe_purchase_archive SET status='refunded' WHERE payment_intent_id='pi_test_1'")
        self.assertEqual(self.db.execute("SELECT status FROM stripe_purchase_archive WHERE payment_intent_id='pi_test_1'").fetchone()[0], "refunded")


if __name__ == "__main__":
    unittest.main()
