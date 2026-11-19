-- 0002: sign-in providers, TV/device sign-in, subscriptions, audit trail.
-- Purely additive: the deployed Worker keeps working unchanged against it.
-- Apply once to "yarr-accounts" (wrangler d1 execute, or the D1 console).

-- Which sign-in methods belong to which account. Google and Apple both land
-- here; users.google_sub is kept for the current Worker and is a placeholder
-- ('none:<user id>') for accounts that never used Google.
CREATE TABLE user_identities (
  provider TEXT NOT NULL CHECK (provider IN ('google','apple')),
  subject TEXT NOT NULL,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  email TEXT,
  email_verified INTEGER NOT NULL DEFAULT 0,
  is_private_relay INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  last_login_at TEXT,
  PRIMARY KEY (provider, subject)
);
CREATE INDEX user_identities_user_idx ON user_identities(user_id);
INSERT INTO user_identities(provider,subject,user_id,email,email_verified,created_at)
  SELECT 'google', google_sub, id, email, 1, created_at FROM users
  WHERE google_sub NOT LIKE 'none:%';

ALTER TABLE users ADD COLUMN terms_version TEXT;
ALTER TABLE users ADD COLUMN terms_accepted_at TEXT;
ALTER TABLE users ADD COLUMN deleted_at TEXT;

ALTER TABLE sessions ADD COLUMN last_used_at TEXT;
ALTER TABLE sessions ADD COLUMN user_agent TEXT;

-- Google TV / phone app sign-in (RFC 8628 style): the TV asks for a code, shows
-- it, and the user approves it from a signed-in phone or browser.
CREATE TABLE device_login_requests (
  device_code_hash TEXT PRIMARY KEY,
  user_code_hash TEXT NOT NULL UNIQUE,
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','denied','used')),
  user_id TEXT REFERENCES users(id) ON DELETE CASCADE,
  device_name TEXT,
  device_type TEXT NOT NULL DEFAULT 'google_tv',
  poll_interval_s INTEGER NOT NULL DEFAULT 5,
  last_polled_at TEXT,
  expires_at TEXT NOT NULL,
  approved_at TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX device_login_expiry_idx ON device_login_requests(expires_at);

-- A signed-in device holds its own long-lived credential, revocable one by one.
ALTER TABLE devices ADD COLUMN token_hash TEXT;
ALTER TABLE devices ADD COLUMN token_expires_at TEXT;
ALTER TABLE devices ADD COLUMN revoked_at TEXT;
ALTER TABLE devices ADD COLUMN app_version TEXT;
CREATE UNIQUE INDEX devices_token_unique_idx ON devices(token_hash) WHERE token_hash IS NOT NULL;

-- Pro access. Provider-neutral so Stripe, Apple or Google billing can feed it.
-- Access = a row with status in ('active','trialing') and, if set, a
-- current_period_end in the future (plus 'past_due' for a short grace period).
CREATE TABLE subscriptions (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  plan TEXT NOT NULL DEFAULT 'pro',
  status TEXT NOT NULL CHECK (status IN ('trialing','active','past_due','canceled','expired','incomplete')),
  provider TEXT NOT NULL CHECK (provider IN ('stripe','apple','google','manual')),
  provider_customer_id TEXT,
  provider_subscription_id TEXT,
  current_period_end TEXT,
  cancel_at_period_end INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX subscriptions_user_idx ON subscriptions(user_id);
CREATE UNIQUE INDEX subscriptions_provider_unique_idx
  ON subscriptions(provider, provider_subscription_id) WHERE provider_subscription_id IS NOT NULL;

-- Webhook de-duplication and an audit trail of what the provider told us.
CREATE TABLE billing_events (
  provider TEXT NOT NULL,
  event_id TEXT NOT NULL,
  event_type TEXT NOT NULL,
  user_id TEXT REFERENCES users(id) ON DELETE SET NULL,
  payload_hash TEXT,
  received_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (provider, event_id)
);

-- Security-relevant account events (sign-in, device approved/revoked, server
-- paired, plan change, deletion). No media titles or IP addresses, hashes only.
CREATE TABLE audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id TEXT REFERENCES users(id) ON DELETE SET NULL,
  event TEXT NOT NULL,
  detail TEXT,
  ip_hash TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX audit_log_user_idx ON audit_log(user_id, created_at);

CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
INSERT INTO schema_migrations(version,name) VALUES (1,'0001_baseline'),(2,'0002_identities_devices_billing');
