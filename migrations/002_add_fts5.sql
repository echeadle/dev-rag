-- dev-rag FTS5 migration — adds BM25 full-text search
-- Run after 001_initial_schema.sql

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    chunk_id  UNINDEXED,
    domain    UNINDEXED,
    content,
    tokenize  = 'porter ascii'
);

CREATE TRIGGER IF NOT EXISTS chunks_fts_insert
AFTER INSERT ON chunks BEGIN
    INSERT INTO chunks_fts(chunk_id, domain, content)
    VALUES (new.chunk_id, new.domain, new.content);
END;

CREATE TRIGGER IF NOT EXISTS chunks_fts_delete
AFTER DELETE ON chunks BEGIN
    DELETE FROM chunks_fts WHERE chunk_id = old.chunk_id;
END;
