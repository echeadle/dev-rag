"""Dense retrieval tests — temp stores built by the REAL write path
(load_to_stores + real migrations), fake embedder, never real BGE-M3."""
from pathlib import Path

import numpy as np
import pytest

import dev_rag.retrieve as retrieve
from dev_rag.ingest.load import load_to_stores
from dev_rag.ingest.util import content_hash
from dev_rag.retrieve import DenseResult, dense_search, get_query_embedder

MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations"
DIM = 8


class OneHotQueryModel:
    """encode() returns a one-hot vector matching chunk `hot`'s embedding."""

    def __init__(self, hot=1):
        self.hot = hot

    def encode(self, text, **kwargs):
        v = np.zeros(DIM, dtype=np.float32)
        v[self.hot] = 1.0
        return v


def make_chunk(i):
    content = f"Chunk {i} about docker networking and secrets."
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


def one_hot(i):
    v = [0.0] * DIM
    v[i] = 1.0
    return v


@pytest.fixture
def chroma_path(tmp_path):
    load_to_stores(
        [make_chunk(i) for i in range(3)],
        [one_hot(i) for i in range(3)],
        chroma_path=str(tmp_path / "chroma"),
        sqlite_path=tmp_path / "dev_rag.db",
        migrations_dir=MIGRATIONS,
    )
    return str(tmp_path / "chroma")


def test_dense_search_ranks_nearest_first(chroma_path):
    results = dense_search(
        "how do secrets work", "devops",
        chroma_path=chroma_path, model=OneHotQueryModel(hot=1),
    )
    assert results
    assert isinstance(results[0], DenseResult)
    assert results[0].chunk_id == "tiny_0001"
    assert results[0].dense_score == pytest.approx(1.0, abs=1e-5)
    scores = [r.dense_score for r in results]
    assert scores == sorted(scores, reverse=True)


def test_dense_search_carries_metadata(chroma_path):
    top = dense_search("q", "devops", chroma_path=chroma_path,
                       model=OneHotQueryModel())[0]
    assert top.source == "tiny.pdf"
    assert top.domain == "devops"
    assert "docker networking" in top.content


def test_dense_search_respects_n_results(chroma_path):
    results = dense_search("q", "devops", chroma_path=chroma_path,
                           n_results=2, model=OneHotQueryModel())
    assert len(results) == 2


def test_missing_collection_returns_empty(chroma_path):
    assert dense_search("q", "nonexistent", chroma_path=chroma_path,
                        model=OneHotQueryModel()) == []


def test_get_query_embedder_is_cached_singleton(monkeypatch):
    calls = []
    monkeypatch.setattr(retrieve, "_embedder", None)
    monkeypatch.setattr(
        "dev_rag.ingest.embed.get_embedder",
        lambda: calls.append(1) or OneHotQueryModel(),
    )
    a = get_query_embedder()
    b = get_query_embedder()
    assert a is b
    assert len(calls) == 1
