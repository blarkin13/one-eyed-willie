-- Additive migration for ONE-TIME Stripe Pro purchases. Do not deploy until tested.
-- Deliberately separate from the older subscription-based plan schema.
CREATE TABLE IF NOT EXISTS stripe_checkout_sessions (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id),
  price_id TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('pending','paid','refunded','disputed')),
  amount_total INTEGER,
  currency TEXT,
  payment_intent_id TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS stripe_checkout_user_idx ON stripe_checkout_sessions(user_id);
CREATE UNIQUE INDEX IF NOT EXISTS stripe_checkout_payment_idx ON stripe_checkout_sessions(payment_intent_id)
  WHERE payment_intent_id IS NOT NULL;
CREATE TABLE IF NOT EXISTS stripe_webhook_events (
  event_id TEXT PRIMARY KEY,
  event_type TEXT NOT NULL,
  session_id TEXT,
  received_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS one_time_pro_entitlements (
  user_id TEXT NOT NULL REFERENCES users(id),
  checkout_session_id TEXT NOT NULL UNIQUE REFERENCES stripe_checkout_sessions(id),
  status TEXT NOT NULL CHECK(status IN ('active','revoked')),
  granted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (user_id,checkout_session_id)
);

INSERT OR IGNORE INTO schema_migrations(version,name) VALUES(10,'0010_stripe_one_time_pro');
