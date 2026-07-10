"""BM25 sparse retrieval tests — fixture built by the REAL migrations
(001+002+003), not a hand-rolled schema, so tests can't drift from it."""
import sqlite3
from pathlib import Path

import pytest

from dev_rag.ingest.load import apply_migrations
from dev_rag.retrieve_sparse import SparseResult, _sanitise_fts_query, bm25_search

MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations"

SOURCES = [
    ("ddd", "devops", "docker-deep-dive.pdf"),
    ("sec", "devops", "docker-security.pdf"),
    ("fpp", "python", "five-lines-of-code.pdf"),
]
CHUNKS = [
    ("c1", "ddd", "devops", "Docker secrets store sensitive data securely"),
    ("c2", "ddd", "devops", "Use --network=host to share the host network namespace"),
    ("c3", "sec", "devops", "Running containers as root is a security risk"),
    ("c4", "ddd", "devops", "Bridge networks are the default Docker network mode"),
    ("c5", "fpp", "python", "Extract method to keep functions accessible and short"),
]


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "dev_rag.db"
    apply_migrations(path, MIGRATIONS)
    conn = sqlite3.connect(path)
    conn.executemany(
        "INSERT INTO sources (source_id, domain, source_path, source_type) "
        "VALUES (?, ?, ?, 'pdf')", SOURCES)
    conn.executemany(
        "INSERT INTO chunks (chunk_id, source_id, domain, content, page_number, content_hash) "
        "VALUES (?, ?, ?, ?, 1, ?)",
        [(cid, sid, dom, text, f"hash-{cid}") for cid, sid, dom, text in CHUNKS])
    conn.commit()
    conn.close()
    return path


def test_bm25_returns_results(db):
    results = bm25_search("Docker secrets", domain="devops", db_path=db)
    assert results
    assert isinstance(results[0], SparseResult)
    assert results[0].chunk_id == "c1"
    assert results[0].bm25_score > 0


def test_bm25_carries_source_filename(db):
    top = bm25_search("Docker secrets", domain="devops", db_path=db)[0]
    assert top.source == "docker-deep-dive.pdf"


def test_bm25_domain_filter(db):
    results = bm25_search("accessible", domain="python", db_path=db)
    assert results and all(r.domain == "python" for r in results)


def test_bm25_no_cross_domain_bleed(db):
    results = bm25_search("Docker network", domain="devops", db_path=db)
    assert results and all(r.domain == "devops" for r in results)


def test_bm25_exact_flag_query_survives_sanitising(db):
    # '--network=host' would be an FTS5 syntax error raw; sanitised to
    # 'network OR host', which must surface the flag chunk first
    results = bm25_search("--network=host", domain="devops", db_path=db)
    assert results[0].chunk_id == "c2"


def test_bm25_natural_language_question_has_recall(db):
    # implicit-AND would return nothing for a sentence like this;
    # OR-joined terms must still surface the network chunks
    results = bm25_search(
        "what is the default network mode used by Docker?",
        domain="devops", db_path=db,
    )
    assert any(r.chunk_id == "c4" for r in results)


def test_bm25_malformed_query_does_not_raise(db):
    results = bm25_search('"unbalanced', domain="devops", db_path=db)
    assert isinstance(results, list)


def test_bm25_operator_only_query_returns_empty(db):
    assert bm25_search('AND OR "*(', domain="devops", db_path=db) == []


def test_bm25_excludes_soft_deleted_chunks(db):
    conn = sqlite3.connect(db)
    conn.execute("UPDATE chunks SET status='deleted' WHERE chunk_id='c1'")
    conn.commit()
    conn.close()
    results = bm25_search("Docker secrets", domain="devops", db_path=db)
    assert all(r.chunk_id != "c1" for r in results)


def test_sanitise_fts_query():
    assert _sanitise_fts_query('"bad query"') == "bad query"
    assert _sanitise_fts_query("docker AND secrets") == "docker secrets"
    assert _sanitise_fts_query("--network=host") == "network host"
    # whole-word only: words containing operators survive
    assert _sanitise_fts_query("android handoff") == "android handoff"
    assert _sanitise_fts_query('AND OR NOT "*') == ""
