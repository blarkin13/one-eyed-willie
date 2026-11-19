-- 0003: remember where to send someone after Google sign-in (for example back to
-- /activate with their TV code). Only allow-listed paths are ever stored.
ALTER TABLE oauth_flows ADD COLUMN return_to TEXT;
INSERT INTO schema_migrations(version,name) VALUES (3,'0003_return_to');
