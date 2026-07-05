"""RRF fusion unit tests (spec's six cases) + hybrid_search integration
against temp stores built by the real write path. No real BGE-M3."""
from pathlib import Path

import numpy as np
import pytest

from dev_rag.ingest.load import load_to_stores
from dev_rag.ingest.util import content_hash
from dev_rag.retrieve import DenseResult
from dev_rag.retrieve_hybrid import HybridResult, hybrid_search, reciprocal_rank_fusion
from dev_rag.retrieve_sparse import SparseResult

MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations"
DIM = 8


def _dense(items):
    return [
        DenseResult(chunk_id=cid, domain="devops", content=f"content {cid}",
                    source="test.pdf", dense_score=score)
        for cid, score in items
    ]


def _sparse(items):
    return [
        SparseResult(chunk_id=cid, domain="devops", content=f"content {cid}",
                     source="test.pdf", bm25_score=score)
        for cid, score in items
    ]


# ── RRF unit tests (per spec §6) ─────────────────────────────────────────────

def test_rrf_document_in_both_lists_ranks_highest():
    dense = _dense([("c1", 0.9), ("c2", 0.8), ("c3", 0.7)])
    sparse = _sparse([("c2", 5.0), ("c4", 4.0), ("c1", 3.0)])
    fused_ids = [r.chunk_id for r in reciprocal_rank_fusion(dense, sparse)]
    assert fused_ids.index("c1") < fused_ids.index("c3")
    assert fused_ids.index("c2") < fused_ids.index("c4")


def test_rrf_bm25_only_result_included_with_source():
    dense = _dense([("c1", 0.9), ("c2", 0.8)])
    sparse = _sparse([("c3", 9.0), ("c1", 5.0)])
    fused = reciprocal_rank_fusion(dense, sparse)
    c3 = next(r for r in fused if r.chunk_id == "c3")
    assert c3.dense_rank is None and c3.sparse_rank == 1
    assert c3.source == "test.pdf"      # carried by stage 2, not enriched later


def test_rrf_scores_positive_and_descending():
    fused = reciprocal_rank_fusion(
        _dense([("c1", 0.9), ("c2", 0.7)]), _sparse([("c2", 4.0), ("c1", 3.0)]))
    scores = [r.rrf_score for r in fused]
    assert all(s > 0 for s in scores)
    assert scores == sorted(scores, reverse=True)


def test_rrf_rank_and_score_fields_populated():
    fused = reciprocal_rank_fusion(_dense([("c1", 0.9)]), _sparse([("c1", 4.0)]))
    c1 = fused[0]
    assert isinstance(c1, HybridResult)
    assert c1.dense_rank == 1 and c1.sparse_rank == 1
    assert c1.dense_score == 0.9 and c1.bm25_score == 4.0
    assert c1.rrf_score == pytest.approx(2 / 61)


def test_rrf_empty_sparse_returns_dense_order():
    fused = reciprocal_rank_fusion(_dense([("c1", 0.9), ("c2", 0.7)]), [])
    assert [r.chunk_id for r in fused] == ["c1", "c2"]


def test_rrf_empty_dense_returns_sparse_order():
    fused = reciprocal_rank_fusion([], _sparse([("c3", 5.0), ("c4", 3.0)]))
    assert [r.chunk_id for r in fused] == ["c3", "c4"]


# ── hybrid_search integration ────────────────────────────────────────────────

CONTENTS = [
    "Docker images are built in layers from a Dockerfile.",     # dense favourite
    "Bridge networks are the default Docker network mode.",
    "Swarm ingress routing publishes ports across every node.",  # sparse favourite
]


class QueryModel:
    """Query embeds as one-hot(0) → dense ranks chunk 0 first."""

    def encode(self, text, **kwargs):
        v = np.zeros(DIM, dtype=np.float32)
        v[0] = 1.0
        return v


@pytest.fixture
def stores(tmp_path):
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
    return {"chroma_path": str(tmp_path / "chroma"), "db_path": tmp_path / "dev_rag.db"}


def test_hybrid_search_merges_both_channels(stores):
    # dense favours chunk 0 (one-hot); BM25 favours chunk 2 ("swarm ingress")
    results = hybrid_search("swarm ingress routing", "devops",
                            model=QueryModel(), **stores)
    ids = [r.chunk_id for r in results]
    assert "tiny_0000" in ids and "tiny_0002" in ids
    top = results[0]
    assert top.rrf_score > 0
    assert top.source == "tiny.pdf"


def test_hybrid_search_respects_n_results(stores):
    results = hybrid_search("docker network", "devops", n_results=2,
                            model=QueryModel(), **stores)
    assert len(results) <= 2


def test_hybrid_search_survives_empty_domain(stores):
    # travel: no collection AND no FTS rows -> empty, not an error
    assert hybrid_search("anything", "travel", model=QueryModel(), **stores) == []
