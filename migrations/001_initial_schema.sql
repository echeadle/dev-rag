-- dev-rag initial SQLite schema
-- Run once on first startup

CREATE TABLE IF NOT EXISTS sources (
    source_id         TEXT PRIMARY KEY,
    domain            TEXT NOT NULL,
    source_path       TEXT NOT NULL,
    source_type       TEXT NOT NULL,   -- pdf | url
    version           TEXT,
    ingest_timestamp  TEXT DEFAULT (datetime('now')),
    status            TEXT DEFAULT 'active'
);

CREATE TABLE IF NOT EXISTS chunks (
    chunk_id          TEXT PRIMARY KEY,
    source_id         TEXT NOT NULL REFERENCES sources(source_id),
    domain            TEXT NOT NULL,
    content           TEXT NOT NULL,
    page_number       INTEGER,
    content_hash      TEXT NOT NULL,
    ingest_timestamp  TEXT DEFAULT (datetime('now')),
    status            TEXT DEFAULT 'active'
);

CREATE INDEX IF NOT EXISTS chunks_source_idx  ON chunks(source_id);
CREATE INDEX IF NOT EXISTS chunks_domain_idx  ON chunks(domain);
CREATE INDEX IF NOT EXISTS chunks_hash_idx    ON chunks(content_hash);
CREATE INDEX IF NOT EXISTS chunks_status_idx  ON chunks(status);
