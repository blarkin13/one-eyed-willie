-- Baseline: the schema that was already live in the D1 database "yarr-accounts"
-- (db4a0ec1-ab0b-49db-b95c-e84d8cef2bf0) when migrations were introduced.
-- Do not apply to the production database; it is here so the schema is in git
-- and tests can rebuild it.
CREATE TABLE users (id TEXT PRIMARY KEY, google_sub TEXT NOT NULL UNIQUE, email TEXT, display_name TEXT, avatar_url TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE sessions (id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE, token_hash TEXT NOT NULL UNIQUE, expires_at TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE INDEX sessions_user_idx ON sessions(user_id);
CREATE TABLE oauth_flows (state_hash TEXT PRIMARY KEY, nonce TEXT NOT NULL, verifier TEXT NOT NULL, expires_at TEXT NOT NULL);
CREATE INDEX oauth_flows_expiry_idx ON oauth_flows(expires_at);
CREATE TABLE servers (id TEXT PRIMARY KEY, owner_user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE, display_name TEXT NOT NULL, public_url TEXT, status TEXT NOT NULL DEFAULT 'pending', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, local_url TEXT, server_identity TEXT, connection_secret_hash TEXT, last_seen_at TEXT);
CREATE INDEX servers_owner_idx ON servers(owner_user_id);
CREATE UNIQUE INDEX servers_identity_unique_idx ON servers(server_identity) WHERE server_identity IS NOT NULL;
CREATE TABLE pairing_requests (code_hash TEXT PRIMARY KEY, server_identity TEXT NOT NULL, secret_hash TEXT NOT NULL UNIQUE, status TEXT NOT NULL DEFAULT 'pending', owner_user_id TEXT, expires_at TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE INDEX pairing_expiry_idx ON pairing_requests(expires_at);
CREATE TABLE pairing_rate_limits (ip_hash TEXT NOT NULL, window TEXT NOT NULL, count INTEGER NOT NULL DEFAULT 1, PRIMARY KEY(ip_hash,window));
CREATE TABLE devices (id TEXT PRIMARY KEY, owner_user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE, server_id TEXT REFERENCES servers(id) ON DELETE SET NULL, device_name TEXT NOT NULL, device_type TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, last_seen_at TEXT);
CREATE INDEX devices_owner_idx ON devices(owner_user_id);
