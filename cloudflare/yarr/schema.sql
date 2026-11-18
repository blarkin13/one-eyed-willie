-- Yarr account control plane; independent from each customer's local media SQLite database.
-- Deployed to the Cloudflare D1 database yarr-accounts on 2026-11-18.
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY,
  google_sub TEXT NOT NULL UNIQUE,
  email TEXT,
  display_name TEXT,
  avatar_url TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS servers (
  id TEXT PRIMARY KEY,
  owner_user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  display_name TEXT NOT NULL,
  public_url TEXT,
  local_url TEXT,
  server_identity TEXT,
  status TEXT NOT NULL DEFAULT 'pending',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS servers_owner_idx ON servers(owner_user_id);
CREATE TABLE IF NOT EXISTS devices (
  id TEXT PRIMARY KEY,
  owner_user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  server_id TEXT REFERENCES servers(id) ON DELETE SET NULL,
  device_name TEXT NOT NULL,
  device_type TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  last_seen_at TEXT
);
CREATE INDEX IF NOT EXISTS devices_owner_idx ON devices(owner_user_id);
CREATE TABLE IF NOT EXISTS sessions (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  token_hash TEXT NOT NULL UNIQUE,
  expires_at TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS sessions_user_idx ON sessions(user_id);

-- Ephemeral OAuth transactions prevent cross-site login CSRF and enforce one-time callbacks.
CREATE TABLE IF NOT EXISTS oauth_flows (
  state_hash TEXT PRIMARY KEY,
  nonce TEXT NOT NULL,
  verifier TEXT NOT NULL,
  expires_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS oauth_flows_expiry_idx ON oauth_flows(expires_at);

-- Time-limited pairing codes; only hashed code and polling secret are stored.
CREATE TABLE IF NOT EXISTS pairing_requests (
  code_hash TEXT PRIMARY KEY,
  server_identity TEXT NOT NULL,
  secret_hash TEXT NOT NULL UNIQUE,
  status TEXT NOT NULL DEFAULT 'pending',
  owner_user_id TEXT,
  expires_at TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS pairing_expiry_idx ON pairing_requests(expires_at);
CREATE TABLE IF NOT EXISTS pairing_rate_limits (
  ip_hash TEXT NOT NULL,
  window TEXT NOT NULL,
  count INTEGER NOT NULL DEFAULT 1,
  PRIMARY KEY(ip_hash,window)
);
CREATE UNIQUE INDEX IF NOT EXISTS servers_identity_unique_idx ON servers(server_identity) WHERE server_identity IS NOT NULL;
