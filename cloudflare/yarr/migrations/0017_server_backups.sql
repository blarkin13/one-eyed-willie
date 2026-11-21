-- 0017: encrypted watch-history backups uploaded by paired servers. The server
-- encrypts with a key derived from a recovery code only its owner holds, so
-- yarr.media stores bytes it cannot read. Kept per server (and owner) so a
-- reinstalled server can restore; deleted with the owner's account.
CREATE TABLE server_backups (
  server_id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  server_name TEXT NOT NULL DEFAULT '',
  blob BLOB NOT NULL,
  size INTEGER NOT NULL,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX server_backups_user ON server_backups(user_id);
INSERT OR IGNORE INTO schema_migrations(version,name) VALUES(17,'0017_server_backups');
