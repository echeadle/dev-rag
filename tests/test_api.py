"""Tests for FastAPI routes — expand as you implement api.py"""
import pytest
from fastapi.testclient import TestClient
from dev_rag.api import app

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] in ("ok", "degraded")
    assert "valid_domains" in data
    assert "store_parity" in data       # OBS-009
    assert "stores_in_sync" in data     # OBS-009


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
