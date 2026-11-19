-- 0004: each server's public IP, recorded from its regular check-in, so
-- app.yarr.media can reach it without anyone typing an address.
ALTER TABLE servers ADD COLUMN public_ip TEXT;
ALTER TABLE servers ADD COLUMN public_ip_seen_at TEXT;
INSERT INTO schema_migrations(version,name) VALUES (4,'0004_server_public_ip');
