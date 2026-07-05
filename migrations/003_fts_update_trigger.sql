-- dev-rag FTS5 sync fix — FBL-001 (Fable review 2026-07-05)
-- Run after 002_add_fts5.sql
--
-- 002 covers INSERT and DELETE, but ADR-006 Strategy B (incremental upsert
-- for living sources) mutates chunks via UPDATE: rewriting content whose
-- hash changed, and marking vanished chunks status='deleted'. Without this
-- trigger those updates leave chunks_fts stale — BM25 would keep serving
-- old text and "deleted" chunks would stay searchable forever.
--
-- NOTE: SQLite fires triggers only on explicit statements. INSERT OR
-- REPLACE's implicit delete does NOT fire the delete trigger (unless
-- PRAGMA recursive_triggers is on) — which is why ingest/load.py uses
-- explicit DELETE + INSERT. This trigger covers the explicit-UPDATE path.

CREATE TRIGGER IF NOT EXISTS chunks_fts_update
AFTER UPDATE ON chunks BEGIN
    DELETE FROM chunks_fts WHERE chunk_id = old.chunk_id;
    INSERT INTO chunks_fts(chunk_id, domain, content)
    SELECT new.chunk_id, new.domain, new.content
    WHERE new.status = 'active';
END;
