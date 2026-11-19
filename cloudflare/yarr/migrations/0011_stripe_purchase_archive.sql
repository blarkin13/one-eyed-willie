-- Preserve the payment ledger while deleting a Yarr account and revoking its Pro entitlement.
-- Archive intentionally has no user identifier or foreign key to users.
CREATE TABLE IF NOT EXISTS stripe_purchase_archive (
  checkout_session_id TEXT PRIMARY KEY,
  price_id TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('pending','paid','refunded','disputed')),
  amount_total INTEGER,
  currency TEXT,
  payment_intent_id TEXT UNIQUE,
  purchased_at TEXT,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  archived_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS stripe_purchase_archive_status_idx ON stripe_purchase_archive(status);
INSERT OR IGNORE INTO schema_migrations(version,name) VALUES(11,'0011_stripe_purchase_archive');
