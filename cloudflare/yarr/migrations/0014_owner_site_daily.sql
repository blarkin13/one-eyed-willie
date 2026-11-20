-- Aggregate HTTP page requests; no visitor IDs, IPs, queries or media metadata.
CREATE TABLE IF NOT EXISTS owner_site_daily (day TEXT NOT NULL,path TEXT NOT NULL,requests INTEGER NOT NULL DEFAULT 0 CHECK(requests>=0),PRIMARY KEY(day,path));
INSERT OR IGNORE INTO schema_migrations(version,name) VALUES(14,'0014_owner_site_daily');
