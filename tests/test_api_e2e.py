"""End-to-end /search tests against the REAL endpoint (CLAUDE.md rule).

The full path is exercised: HTTP → api.py → retrieve/retrieve_sparse/
retrieve_hybrid → temp ChromaDB + SQLite built by the REAL migrations and
the REAL ingest loader. Only the embedding model is fake. This is what
finally proves the OBS-001 relevance_score contract against a live
producer instead of hand-written fixtures.
"""
import sqlite3
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

import dev_rag.retrieve as retrieve
from dev_rag.api import app
from dev_rag.ingest.load import load_to_stores
from dev_rag.ingest.util import content_hash
from dev_rag.settings import settings

MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations"
DIM = 8

CONTENTS = [
    "Docker images are built in layers from a Dockerfile.",
    "Docker secrets are encrypted in the swarm cluster store.",
    "Bridge networks are the default Docker network mode.",
]


class QueryModel:
    """Query always embeds one-hot(1) → dense favours the secrets chunk."""

    def encode(self, text, **kwargs):
        v = np.zeros(DIM, dtype=np.float32)
        v[1] = 1.0
        return v


@pytest.fixture
def client(tmp_path, monkeypatch):
    chunks = [
        {
            "chunk_id": f"tiny_{i:04d}", "source_id": "tiny", "source": "tiny.pdf",
            "domain": "devops", "title": "Tiny Book", "page_number": i + 1,
            "content": text, "content_hash": content_hash(text),
        }
        for i, text in enumerate(CONTENTS)
    ]
    embeds = []
    for i in range(3):
        v = [0.0] * DIM
        v[i] = 1.0
        embeds.append(v)
    load_to_stores(chunks, embeds, chroma_path=str(tmp_path / "chroma"),
                   sqlite_path=tmp_path / "dev_rag.db", migrations_dir=MIGRATIONS)

    monkeypatch.setattr(settings, "chroma_db_path", str(tmp_path / "chroma"))
    monkeypatch.setattr(settings, "sqlite_db_path", tmp_path / "dev_rag.db")
    monkeypatch.setattr(retrieve, "_embedder", QueryModel())
    return TestClient(app)


def search(client, **overrides):
    payload = {"query": "docker secrets", "domain": "devops", "n_results": 3}
    payload.update(overrides)
    r = client.post("/search", json=payload)
    assert r.status_code == 200
    return r.json()


def test_hybrid_mode_end_to_end(client):
    data = search(client, search_mode="hybrid")
    assert data["search_mode"] == "hybrid"
    results = data["results"]
    assert results, "hybrid returned nothing through the live endpoint"
    top = results[0]
    # dense (one-hot) and BM25 ('docker secrets') both favour the secrets chunk
    assert top["chunk_id"] == "tiny_0001"
    assert top["source"] == "tiny.pdf"
    # OBS-001: canonical field present and equal to the RRF debug field
    assert top["relevance_score"] == pytest.approx(top["rrf_score"])
    assert 0 < top["relevance_score"] < 0.04     # RRF scale
    assert top["dense_rank"] == 1 and top["sparse_rank"] == 1


def test_dense_mode_end_to_end(client):
    data = search(client, search_mode="dense")
    top = data["results"][0]
    assert top["chunk_id"] == "tiny_0001"
    assert top["relevance_score"] == pytest.approx(1.0, abs=1e-5)  # cosine sim
    assert top["rrf_score"] is None              # debug fields absent in dense


def test_sparse_mode_end_to_end(client):
    data = search(client, search_mode="sparse")
    top = data["results"][0]
    assert top["chunk_id"] == "tiny_0001"
    assert top["relevance_score"] > 0            # negated BM25


def test_all_results_carry_canonical_relevance_score(client):
    for mode in ("hybrid", "dense", "sparse"):
        for r in search(client, search_mode=mode)["results"]:
            assert r["relevance_score"] is not None, f"missing in {mode}"


def test_collections_report_real_chroma_counts(client):
    data = client.get("/collections").json()
    by_name = {c["name"]: c for c in data["collections"]}
    assert set(by_name) == set(settings.valid_domains)
    assert by_name["devops"] == {"name": "devops", "documents": 3, "status": "ready"}
    assert by_name["travel"] == {"name": "travel", "documents": 0, "status": "empty"}


def test_health_reports_real_counts_and_detects_drift(client):
    data = client.get("/health").json()
    assert data["store_parity"]["devops"] == {
        "chroma_chunks": 3, "sqlite_chunks": 3, "in_sync": True,
    }
    assert data["status"] == "ok"

    # OBS-009: simulate a partial-write failure — /health must degrade
    conn = sqlite3.connect(settings.sqlite_db_path)
    conn.execute("DELETE FROM chunks WHERE chunk_id='tiny_0002'")
    conn.commit()
    conn.close()
    data = client.get("/health").json()
    assert data["status"] == "degraded"
    assert data["store_parity"]["devops"]["in_sync"] is False
