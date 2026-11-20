-- 0016: a picture (PNG) each owner can set for their server; shown to them and
-- to the people they share it with (server switcher, Shared with you).
CREATE TABLE server_icons (
  server_id TEXT PRIMARY KEY REFERENCES servers(id) ON DELETE CASCADE,
  png BLOB NOT NULL,
  version INTEGER NOT NULL DEFAULT 1,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
INSERT OR IGNORE INTO schema_migrations(version,name) VALUES(16,'0016_server_icons');
