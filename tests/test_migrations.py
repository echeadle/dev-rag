"""Migration-level FTS sync tests — FBL-001 (003_fts_update_trigger).

These exercise raw SQL against the real migrations, independent of the
ingest loader, because Strategy B (ADR-006) will mutate chunks via UPDATE.
"""
import sqlite3
from pathlib import Path

import pytest

from dev_rag.ingest.load import apply_migrations

MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations"


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "dev_rag.db"
    apply_migrations(path, MIGRATIONS)
    conn = sqlite3.connect(path)
    conn.execute(
        "INSERT INTO sources (source_id, domain, source_path, source_type) "
        "VALUES ('src', 'devops', 'src.pdf', 'pdf')"
    )
    conn.execute(
        "INSERT INTO chunks (chunk_id, source_id, domain, content, page_number, content_hash) "
        "VALUES ('c1', 'src', 'devops', 'original text about docker overlay networks', 1, 'h1')"
    )
    conn.commit()
    yield conn
    conn.close()


def fts_match(conn, term):
    return [r[0] for r in conn.execute(
        "SELECT chunk_id FROM chunks_fts WHERE chunks_fts MATCH ?", (term,))]


def test_update_content_reindexes_fts(db):
    db.execute("UPDATE chunks SET content='rewritten text about swarm ingress' WHERE chunk_id='c1'")
    db.commit()
    assert fts_match(db, "ingress") == ["c1"]      # new content searchable
    assert fts_match(db, "overlay") == []          # stale content gone


def test_status_deleted_removes_from_fts(db):
    db.execute("UPDATE chunks SET status='deleted' WHERE chunk_id='c1'")
    db.commit()
    assert fts_match(db, "overlay") == []
    # the chunk row itself remains (soft delete), only the FTS entry goes
    assert db.execute("SELECT count(*) FROM chunks").fetchone()[0] == 1


def test_status_reactivated_restores_fts(db):
    db.execute("UPDATE chunks SET status='deleted' WHERE chunk_id='c1'")
    db.execute("UPDATE chunks SET status='active' WHERE chunk_id='c1'")
    db.commit()
    assert fts_match(db, "overlay") == ["c1"]


def test_no_duplicate_fts_rows_after_update(db):
    db.execute("UPDATE chunks SET content='updated once more, docker networking' WHERE chunk_id='c1'")
    db.commit()
    n = db.execute("SELECT count(*) FROM chunks_fts WHERE chunk_id='c1'").fetchone()[0]
    assert n == 1
