"""Reranker unit tests — fully mocked CrossEncoder (never the real 568M
model), per planning/reranker-spec.md §5. OBS-002 assertions: every
fallback path returns RankedResult, never raw HybridResult."""
from unittest.mock import MagicMock

import pytest

from dev_rag.reranker import RankedResult, rerank, rerank_with_fallback
from dev_rag.retrieve_hybrid import HybridResult


def _make_hybrid_results(items: list[tuple[str, float]]) -> list[HybridResult]:
    """Build HybridResult list from (chunk_id, rrf_score) pairs."""
    return [
        HybridResult(
            chunk_id=cid,
            domain="devops",
            content=f"Content about {cid}",
            source="test.pdf",
            rrf_score=score,
            dense_rank=i + 1,
            sparse_rank=None,
            dense_score=score,
            bm25_score=None,
        )
        for i, (cid, score) in enumerate(items)
    ]


def _mock_cross_encoder(scores: list[float]) -> MagicMock:
    """Mock CrossEncoder returning preset scores."""
    ce = MagicMock()
    ce.predict.return_value = scores
    return ce


# -- rerank() ----------------------------------------------------------------

def test_rerank_returns_top_n():
    candidates = _make_hybrid_results(
        [("c1", 0.9), ("c2", 0.8), ("c3", 0.7), ("c4", 0.6), ("c5", 0.5)])
    ce = _mock_cross_encoder([0.9, 0.2, 0.8, 0.1, 0.7])
    results = rerank("docker secrets", candidates, ce, top_n=3)
    assert len(results) == 3


def test_rerank_order_follows_cross_encoder_not_rrf():
    """Reranker should override RRF order."""
    candidates = _make_hybrid_results([("c1", 0.9), ("c2", 0.8), ("c3", 0.7)])
    ce = _mock_cross_encoder([0.1, 0.5, 0.9])   # reverses the order
    results = rerank("query", candidates, ce, top_n=3)

    assert results[0].chunk_id == "c3"   # lowest RRF, highest reranker
    assert results[1].chunk_id == "c2"
    assert results[2].chunk_id == "c1"   # highest RRF, lowest reranker


def test_rerank_preserves_rrf_score():
    """Original RRF score stays on the result for debugging."""
    candidates = _make_hybrid_results([("c1", 0.95)])
    ce = _mock_cross_encoder([0.8])
    results = rerank("query", candidates, ce, top_n=1)
    assert results[0].rrf_score == pytest.approx(0.95)


def test_rerank_empty_candidates():
    ce = _mock_cross_encoder([])
    assert rerank("query", [], ce, top_n=5) == []
    ce.predict.assert_not_called()


def test_rerank_scores_are_descending():
    candidates = _make_hybrid_results([("c1", 0.9), ("c2", 0.8), ("c3", 0.7)])
    ce = _mock_cross_encoder([0.6, 0.9, 0.3])
    results = rerank("query", candidates, ce, top_n=3)
    scores = [r.reranker_score for r in results]
    assert scores == sorted(scores, reverse=True)


def test_rerank_result_type():
    candidates = _make_hybrid_results([("c1", 0.9)])
    ce = _mock_cross_encoder([0.75])
    results = rerank("query", candidates, ce, top_n=1)
    assert isinstance(results[0], RankedResult)
    assert results[0].reranker_score == pytest.approx(0.75)


def test_rerank_calls_predict_with_pairs_and_batching():
    """Cross-encoder receives (query, content) pairs, batched, no progress bar."""
    candidates = _make_hybrid_results([("c1", 0.9), ("c2", 0.8)])
    ce = _mock_cross_encoder([0.5, 0.7])
    rerank("my query", candidates, ce, top_n=2, batch_size=16)

    args, kwargs = ce.predict.call_args
    assert args[0] == [("my query", "Content about c1"),
                       ("my query", "Content about c2")]
    assert kwargs["batch_size"] == 16
    assert kwargs["show_progress_bar"] is False


def test_rerank_carries_ranks_through():
    candidates = _make_hybrid_results([("c1", 0.9), ("c2", 0.8)])
    ce = _mock_cross_encoder([0.2, 0.7])
    results = rerank("query", candidates, ce, top_n=2)
    assert results[0].chunk_id == "c2"
    assert results[0].dense_rank == 2
    assert results[0].sparse_rank is None


# -- rerank_with_fallback() (OBS-002) -----------------------------------------

def test_fallback_when_reranker_is_none():
    """None reranker returns RankedResult objects in RRF order."""
    candidates = _make_hybrid_results([("c1", 0.9), ("c2", 0.8), ("c3", 0.7)])
    results = rerank_with_fallback("query", candidates, None, top_n=2)
    assert len(results) == 2
    assert results[0].chunk_id == "c1"           # RRF order preserved
    assert isinstance(results[0], RankedResult)  # OBS-002: never HybridResult
    assert results[0].reranker_score is None     # not run — clearly flagged


def test_fallback_on_reranker_exception():
    """If predict() raises, return RankedResult in RRF order."""
    candidates = _make_hybrid_results([("c1", 0.9), ("c2", 0.8)])
    ce = MagicMock()
    ce.predict.side_effect = RuntimeError("OOM")
    results = rerank_with_fallback("query", candidates, ce, top_n=2)
    assert len(results) == 2
    assert results[0].chunk_id == "c1"
    assert isinstance(results[0], RankedResult)
    assert results[0].reranker_score is None


def test_fallback_top_n_respected_without_reranker():
    candidates = _make_hybrid_results(
        [("c1", 0.9), ("c2", 0.8), ("c3", 0.7), ("c4", 0.6)])
    results = rerank_with_fallback("query", candidates, None, top_n=2)
    assert len(results) == 2


def test_fallback_success_path_delegates_to_rerank():
    candidates = _make_hybrid_results([("c1", 0.9), ("c2", 0.8)])
    ce = _mock_cross_encoder([0.1, 0.9])
    results = rerank_with_fallback("query", candidates, ce, top_n=2)
    assert results[0].chunk_id == "c2"
    assert results[0].reranker_score == pytest.approx(0.9)
