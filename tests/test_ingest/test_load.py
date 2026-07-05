"""Stage 7 load tests — temp Chroma dir + temp SQLite, tiny embeddings."""
import sqlite3
from pathlib import Path

import pytest

from dev_rag.ingest.load import apply_migrations, load_to_stores
from dev_rag.ingest.util import content_hash

MIGRATIONS = Path(__file__).resolve().parents[2] / "migrations"
DIM = 8   # load has no dim assertion (that's Stage 6's job); small = fast


def make_chunk(i, content=None):
    content = content or f"Chunk {i} explains docker overlay networking in depth."
    return {
        "chunk_id": f"tiny_{i:04d}",
        "source_id": "tiny",
        "source": "tiny.pdf",
        "domain": "devops",
        "title": "Tiny Book",
        "page_number": i + 1,
        "content": content,
        "content_hash": content_hash(content),
    }


def embedding(i):
    return [float(i)] * (DIM - 1) + [1.0]


@pytest.fixture
def stores(tmp_path):
    return {
        "chroma_path": str(tmp_path / "chroma"),
        "sqlite_path": tmp_path / "dev_rag.db",
        "migrations_dir": MIGRATIONS,
    }


def test_migrations_create_schema(stores):
    apply_migrations(stores["sqlite_path"], MIGRATIONS)
    conn = sqlite3.connect(stores["sqlite_path"])
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')")}
    conn.close()
    assert {"sources", "chunks", "chunks_fts"} <= tables


def test_load_writes_both_stores_with_parity(stores):
    chunks = [make_chunk(i) for i in range(3)]
    stats = load_to_stores(chunks, [embedding(i) for i in range(3)], **stores)
    assert stats.inserted == 3 and stats.skipped == 0
    assert stats.chroma_count == stats.sqlite_count == stats.fts_count == 3

    conn = sqlite3.connect(stores["sqlite_path"])
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM chunks WHERE chunk_id='tiny_0001'").fetchone()
    assert row["content"].startswith("Chunk 1")
    assert row["status"] == "active"
    src = conn.execute("SELECT * FROM sources WHERE source_id='tiny'").fetchone()
    assert src["domain"] == "devops"
    conn.close()


def test_fts_populated_and_searchable(stores):
    chunks = [make_chunk(i) for i in range(3)]
    load_to_stores(chunks, [embedding(i) for i in range(3)], **stores)
    conn = sqlite3.connect(stores["sqlite_path"])
    hits = conn.execute(
        "SELECT chunk_id FROM chunks_fts WHERE chunks_fts MATCH 'overlay'"
    ).fetchall()
    conn.close()
    assert len(hits) == 3


def test_chroma_metadata_contract(stores):
    import chromadb
    from chromadb.config import Settings as ChromaSettings

    load_to_stores([make_chunk(0)], [embedding(0)], **stores)
    client = chromadb.PersistentClient(
        path=stores["chroma_path"],
        settings=ChromaSettings(anonymized_telemetry=False),
    )
    got = client.get_collection("devops_content").get(ids=["tiny_0000"])
    meta = got["metadatas"][0]
    for key in ("source", "domain", "page_number", "chunk_id"):
        assert key in meta, f"missing metadata key {key}"
    assert meta["source"] == "tiny.pdf"


def test_reload_is_idempotent(stores):
    chunks = [make_chunk(i) for i in range(3)]
    embeds = [embedding(i) for i in range(3)]
    load_to_stores(chunks, embeds, **stores)
    stats = load_to_stores(chunks, embeds, **stores)
    assert stats.inserted == 0 and stats.skipped == 3
    assert stats.chroma_count == stats.sqlite_count == stats.fts_count == 3


def test_changed_content_is_updated_everywhere(stores):
    chunks = [make_chunk(i) for i in range(2)]
    embeds = [embedding(i) for i in range(2)]
    load_to_stores(chunks, embeds, **stores)

    chunks[1] = make_chunk(1, content="Rewritten chunk about docker swarm ingress.")
    stats = load_to_stores(chunks, embeds, **stores)
    assert stats.inserted == 1 and stats.skipped == 1

    conn = sqlite3.connect(stores["sqlite_path"])
    text = conn.execute(
        "SELECT content FROM chunks WHERE chunk_id='tiny_0001'").fetchone()[0]
    # FTS must see the new content, not the stale original (002 triggers)
    fts_new = conn.execute(
        "SELECT count(*) FROM chunks_fts WHERE chunks_fts MATCH 'ingress'").fetchone()[0]
    fts_stale = conn.execute(
        "SELECT count(*) FROM chunks_fts WHERE chunk_id='tiny_0001' AND chunks_fts MATCH 'overlay'"
    ).fetchone()[0]
    conn.close()
    assert text.startswith("Rewritten")
    assert fts_new == 1 and fts_stale == 0
    assert stats.chroma_count == stats.sqlite_count == stats.fts_count == 2


def test_mismatched_lengths_rejected(stores):
    with pytest.raises(ValueError, match="chunks but"):
        load_to_stores([make_chunk(0)], [], **stores)
