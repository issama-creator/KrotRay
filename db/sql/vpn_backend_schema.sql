-- VPN backend core schema
-- Tables: servers, connections
-- Safe to run multiple times.

BEGIN;

CREATE TABLE IF NOT EXISTS servers (
    id SERIAL PRIMARY KEY,
    host TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'alive',
    load DOUBLE PRECISION NOT NULL DEFAULT 0,
    score DOUBLE PRECISION NOT NULL DEFAULT 0,
    previous_active INTEGER NOT NULL DEFAULT 0,
    cooldown_until TIMESTAMP NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

ALTER TABLE servers ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'alive';
ALTER TABLE servers ADD COLUMN IF NOT EXISTS load DOUBLE PRECISION NOT NULL DEFAULT 0;
ALTER TABLE servers ADD COLUMN IF NOT EXISTS score DOUBLE PRECISION NOT NULL DEFAULT 0;
ALTER TABLE servers ADD COLUMN IF NOT EXISTS previous_active INTEGER NOT NULL DEFAULT 0;
ALTER TABLE servers ADD COLUMN IF NOT EXISTS cooldown_until TIMESTAMP NULL;
ALTER TABLE servers ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NOT NULL DEFAULT NOW();

CREATE TABLE IF NOT EXISTS connections (
    key TEXT PRIMARY KEY,
    server_id INTEGER NOT NULL REFERENCES servers(id) ON DELETE CASCADE,
    last_seen TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_connections_server_last_seen
    ON connections(server_id, last_seen);

CREATE INDEX IF NOT EXISTS idx_connections_last_seen
    ON connections(last_seen);

CREATE INDEX IF NOT EXISTS idx_servers_score
    ON servers(score);

COMMIT;
