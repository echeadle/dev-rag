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

import dev_rag.reranker as reranker
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


class FakeCrossEncoder:
    """Favours the bridge-networks chunk — deliberately inverts RRF order,
    so a reranked top hit is distinguishable from the fused one."""

    def predict(self, pairs, **kwargs):
        return [9.0 if "Bridge" in doc else 1.0 for _, doc in pairs]


class LowConfidenceCrossEncoder:
    """Every pair scores below the default gate (0.5) — mimics the
    out-of-scope negative case (FBL-006): the reranker ran but is not
    confident about any candidate."""

    def predict(self, pairs, **kwargs):
        return [0.2 for _ in pairs]


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
    # Reranker off by default: these tests pin the Phase 2 contract
    # (relevance_score == rrf_score). Reranker-on tests enable it per-test.
    monkeypatch.setattr(settings, "reranker_enabled", False)
    monkeypatch.setattr(reranker, "_reranker", None)
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


def test_hybrid_reranker_end_to_end(client, monkeypatch):
    """Phase 3: cross-encoder re-orders the fused candidates (ADR-012)."""
    monkeypatch.setattr(settings, "reranker_enabled", True)
    monkeypatch.setattr(reranker, "_reranker", FakeCrossEncoder())
    data = search(client, search_mode="hybrid")
    top = data["results"][0]
    # RRF favours the secrets chunk; the cross-encoder favours bridge —
    # a reranked top hit proves Stage 2 actually ran and overrode Stage 1
    assert top["chunk_id"] == "tiny_0002"
    assert top["reranker_score"] == pytest.approx(9.0)
    # OBS-001: canonical field carries the reranker score when it ran
    assert top["relevance_score"] == pytest.approx(9.0)
    assert top["rrf_score"] is not None          # Stage 1 debug preserved
    # FBL-006: 9.0 ≥ gate (0.5) → confident, not flagged
    assert top["weak_match"] is False
    assert data["reranker"] == settings.reranker_model


def test_hybrid_force_rerank_end_to_end(client, monkeypatch):
    """Phase 5b: force_rerank=true triggers reranking on its own, even
    with settings.reranker_enabled left at the fixture default (False) —
    proves the per-request override works independently of the server-wide
    ADR-012 default, which stays unaffected (search_devops/search_python
    style single-domain calls never set this field)."""
    monkeypatch.setattr(reranker, "_reranker", FakeCrossEncoder())
    assert settings.reranker_enabled is False   # the ADR-012 default, untouched
    data = search(client, search_mode="hybrid", force_rerank=True)
    top = data["results"][0]
    # Same assertion as test_hybrid_reranker_end_to_end — the cross-encoder
    # override proves Stage 2 ran, this time via force_rerank alone
    assert top["chunk_id"] == "tiny_0002"
    assert top["reranker_score"] == pytest.approx(9.0)
    assert top["relevance_score"] == pytest.approx(9.0)
    assert data["reranker"] == settings.reranker_model


def test_hybrid_without_force_rerank_stays_rrf_only(client):
    """Sibling of the above: force_rerank defaults to False, so a plain
    request is unaffected — RRF order, no reranker fields populated."""
    data = search(client, search_mode="hybrid")
    top = data["results"][0]
    assert top["reranker_score"] is None
    assert data["reranker"] is None


def test_hybrid_reranker_weak_match_flag(client, monkeypatch):
    """FBL-006: when the reranker ran but scored below reranker_min_score,
    the result is flagged weak_match=True — a soft signal, ranking unchanged."""
    monkeypatch.setattr(settings, "reranker_enabled", True)
    monkeypatch.setattr(reranker, "_reranker", LowConfidenceCrossEncoder())
    data = search(client, search_mode="hybrid")
    for r in data["results"]:
        assert r["reranker_score"] == pytest.approx(0.2)
        assert r["weak_match"] is True            # 0.2 < 0.5 gate


def test_weak_match_gate_is_settings_driven(client, monkeypatch):
    """The gate reads settings.reranker_min_score — lower it below the score
    and the same 0.2 hit is no longer flagged."""
    monkeypatch.setattr(settings, "reranker_enabled", True)
    monkeypatch.setattr(settings, "reranker_min_score", 0.1)
    monkeypatch.setattr(reranker, "_reranker", LowConfidenceCrossEncoder())
    data = search(client, search_mode="hybrid")
    assert all(r["weak_match"] is False for r in data["results"])  # 0.2 ≥ 0.1


def test_hybrid_reranker_fallback_when_model_missing(client, monkeypatch):
    """OBS-002: enabled but not loaded → RRF order, reranker_score=None."""
    monkeypatch.setattr(settings, "reranker_enabled", True)
    monkeypatch.setattr(reranker, "_reranker", None)
    data = search(client, search_mode="hybrid")
    top = data["results"][0]
    assert top["chunk_id"] == "tiny_0001"        # RRF order preserved
    assert top["reranker_score"] is None
    assert top["relevance_score"] == pytest.approx(top["rrf_score"])
    # FBL-006: reranker didn't run → confidence unknowable, not a fake pass
    assert top["weak_match"] is None


def test_collections_report_real_chroma_counts(client):
    data = client.get("/collections").json()
    by_name = {c["name"]: c for c in data["collections"]}
    assert set(by_name) == set(settings.valid_domains)
    assert by_name["devops"] == {"name": "devops", "documents": 3, "status": "ready"}


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
