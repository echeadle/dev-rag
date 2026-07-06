"""Tests for FastAPI routes.

Autouse fixture points settings at EMPTY temp stores, injects a fake
embedder, and disables the reranker — /search must never load real
BGE-M3 or bge-reranker-v2-m3, or touch the real corpus. Full-pipeline
assertions live in test_api_e2e.py (loaded temp stores).
"""
import numpy as np
import pytest
from fastapi.testclient import TestClient

import dev_rag.reranker as reranker
import dev_rag.retrieve as retrieve
from dev_rag.api import app
from dev_rag.settings import settings

client = TestClient(app)


class FakeEmbedder:
    def encode(self, text, **kwargs):
        return np.zeros(8, dtype=np.float32)


@pytest.fixture(autouse=True)
def isolated_stores(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "chroma_db_path", str(tmp_path / "chroma"))
    monkeypatch.setattr(settings, "sqlite_db_path", tmp_path / "dev_rag.db")
    monkeypatch.setattr(retrieve, "_embedder", FakeEmbedder())
    monkeypatch.setattr(settings, "reranker_enabled", False)
    monkeypatch.setattr(reranker, "_reranker", None)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] in ("ok", "degraded")
    assert "valid_domains" in data
    assert "store_parity" in data       # OBS-009
    assert "stores_in_sync" in data     # OBS-009


def test_health_empty_stores_report_zero_and_ok():
    data = client.get("/health").json()
    assert data["status"] == "ok"       # 0 == 0 everywhere
    assert data["store_parity"]["devops"] == {
        "chroma_chunks": 0, "sqlite_chunks": 0, "in_sync": True,
    }


def test_search_returns_200():
    r = client.post("/search", json={
        "query": "docker secrets",
        "domain": "devops",
        "n_results": 5,
    })
    assert r.status_code == 200


def test_search_response_shape():
    r = client.post("/search", json={
        "query": "docker networking",
        "domain": "devops",
    })
    data = r.json()
    assert "results" in data
    assert "query" in data
    assert data["search_mode"] == "hybrid"     # default mode


def test_search_rejects_bad_domain():
    r = client.post("/search", json={"query": "q", "domain": "nonsense"})
    assert r.status_code == 422


def test_search_rejects_bad_mode_and_bounds():
    assert client.post("/search", json={
        "query": "q", "domain": "devops", "search_mode": "psychic",
    }).status_code == 422
    assert client.post("/search", json={
        "query": "q", "domain": "devops", "n_results": 0,
    }).status_code == 422
    assert client.post("/search", json={
        "query": "", "domain": "devops",
    }).status_code == 422
