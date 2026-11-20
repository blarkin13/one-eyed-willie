-- 0015: Barnacles. An owner shares a paired server with people who have their
-- own Yarr account. They watch the owner's chosen libraries (TV, phone and
-- app.yarr.media) under the owner's Pro; they have no media of their own.
-- Servers report their library list (id, name, kind; never titles or files)
-- so the owner can choose libraries on My Account.
ALTER TABLE servers ADD COLUMN libraries_json TEXT;
CREATE TABLE server_shares (
  id TEXT PRIMARY KEY,
  server_id TEXT NOT NULL REFERENCES servers(id) ON DELETE CASCADE,
  owner_user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  invite_email TEXT NOT NULL,
  barnacle_user_id TEXT REFERENCES users(id) ON DELETE CASCADE,
  library_ids TEXT NOT NULL DEFAULT '[]',
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','active')),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  accepted_at TEXT,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX server_shares_server_idx ON server_shares(server_id);
CREATE INDEX server_shares_owner_idx ON server_shares(owner_user_id);
CREATE INDEX server_shares_barnacle_idx ON server_shares(barnacle_user_id);
CREATE INDEX server_shares_email_idx ON server_shares(invite_email);
CREATE UNIQUE INDEX server_shares_unique_idx ON server_shares(server_id, invite_email);
INSERT OR IGNORE INTO schema_migrations(version,name) VALUES(15,'0015_server_shares');
