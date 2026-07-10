# dev-rag Cross-Encoder Reranker — Implementation Spec

**Version:** 1.0  
**Date:** June 2026  
**Status:** Ready to implement — after hybrid search is working

---

## Why a Reranker

Hybrid search (BM25 + dense vectors + RRF) produces a good ranked list of
candidates. A cross-encoder reranker produces a *better* ranked list by
doing something the first-pass retrieval cannot: reading the query and each
candidate chunk *together* and scoring their relevance as a pair.

The distinction matters because:

**Bi-encoders** (what BGE-M3 is) encode the query and the document
*separately* into vectors, then measure similarity. This is fast and scales
to millions of documents, but the model never directly compares the two texts —
it can only compare their independent representations.

**Cross-encoders** (what `bge-reranker-v2-m3` is) take the query and a
candidate document *concatenated* as a single input and output a relevance
score. The model can attend to every token in both texts simultaneously.
This is much more accurate but too slow to run against your entire corpus —
which is why it runs only on the top 20–50 candidates from hybrid search.

The two-stage pattern:

```
Stage 1 (fast, approximate): Hybrid search → top-50 candidates
Stage 2 (slow, precise):     Cross-encoder → re-scored top-10
```

In practice, adding a reranker is often the single highest-impact retrieval
improvement because it directly addresses hybrid search's main weakness:
candidates that scored high due to token overlap but are not actually
the most relevant answer to the question.

---

## Model Choice: bge-reranker-v2-m3

**Why bge-reranker-v2-m3:**

1. **Companion model to BGE-M3.** Both are from BAAI and were trained to work
   together. The reranker understands the same vocabulary and concept space
   as your embedding model.

2. **Local inference, no API dependency.** Runs via HuggingFace
   `sentence-transformers` or the `rerankers` library. No outbound call,
   no per-query cost, consistent with the project's open-ecosystem principle.

3. **Multilingual.** Handles non-English content without any
   domain-specific configuration, if a future corpus ever needs it.

4. **Reasonable size.** The v2-m3 variant is ~568M parameters — similar to
   BGE-M3 itself. It will run on CPU for a personal corpus (low query volume)
   and comfortably on GPU if available.

**Alternatives considered:**

| Model | Notes |
|-------|-------|
| `bge-reranker-v2-gemma` | Higher accuracy, but 2B params — heavy for local inference |
| `cross-encoder/ms-marco-MiniLM-L-6-v2` | Fast and small, but English-only, weaker on technical content |
| Cohere Rerank API | Hosted, per-call cost, vendor dependency — ruled out |
| Voyage AI Rerank | Same objection as Cohere |

---

## Architecture

### Where the reranker fits

```
Query
  ├──► BGE-M3 embed ──► ChromaDB ANN ──► dense_results
  │
  └──► SQLite FTS5 BM25 ──────────────► sparse_results
                │
                ▼
          RRF fusion (per domain)
                │
                ▼
          top-50 candidates          ← Stage 1 output
                │
                ▼
     bge-reranker-v2-m3             ← Stage 2: cross-encoder
     (query × each candidate)
                │
                ▼
          top-10 re-ranked results   ← Final output
                │
                ▼
     FastAPI → MCP → Claude Code
```

### Key design decision: reranker is loaded once, not per-request

The reranker model (~568M params) takes several seconds to load from disk.
It must be initialised once at FastAPI startup and held in memory for the
lifetime of the process — not loaded on each request.

```python
# Loaded once at startup, reused for every query
_reranker: CrossEncoder | None = None

@app.on_event("startup")
async def load_reranker():
    global _reranker
    if settings.reranker_enabled:
        _reranker = CrossEncoder(settings.reranker_model)
```

---

## Component Design

### 1. `reranker.py` — Core reranking logic

```python
# src/dev_rag/reranker.py

import logging
from dataclasses import dataclass

log = logging.getLogger(__name__)


@dataclass
class RankedResult:
    chunk_id: str
    domain: str
    content: str
    source: str
    reranker_score: float      # cross-encoder output (higher = more relevant)
    rrf_score: float | None    # preserved from Stage 1 for comparison/debugging
    dense_rank: int | None
    sparse_rank: int | None


def rerank(
    query: str,
    candidates: list,          # list of HybridResult from retrieve_hybrid.py
    cross_encoder,             # loaded CrossEncoder instance
    top_n: int = 10,
    batch_size: int = 32,      # score this many pairs per forward pass
) -> list[RankedResult]:
    """
    Re-score a list of hybrid search candidates using a cross-encoder.

    The cross-encoder reads (query, document) pairs and outputs a relevance
    score for each. Results are returned sorted by descending score.

    Args:
        query:        The original search query
        candidates:   Hybrid search results (HybridResult list)
        cross_encoder: Loaded CrossEncoder model (initialised at startup)
        top_n:        Number of results to return after reranking
        batch_size:   Pairs per forward pass (tune for your VRAM/RAM)

    Returns:
        Re-ranked list of RankedResult, length <= top_n
    """
    if not candidates:
        return []

    # Build (query, document) pairs for the cross-encoder
    pairs = [(query, c.content) for c in candidates]

    # Score all pairs — cross-encoder returns one float per pair
    # predict() handles batching internally using batch_size
    scores = cross_encoder.predict(
        pairs,
        batch_size=batch_size,
        show_progress_bar=False,
    )

    # Pair scores back with candidates and sort
    scored = sorted(
        zip(scores, candidates),
        key=lambda x: x[0],
        reverse=True,
    )

    return [
        RankedResult(
            chunk_id=candidate.chunk_id,
            domain=candidate.domain,
            content=candidate.content,
            source=candidate.source,
            reranker_score=float(score),
            rrf_score=candidate.rrf_score,
            dense_rank=candidate.dense_rank,
            sparse_rank=candidate.sparse_rank,
        )
        for score, candidate in scored[:top_n]
    ]


def rerank_with_fallback(
    query: str,
    candidates: list,
    cross_encoder,
    top_n: int = 10,
) -> list:
    """
    Rerank with graceful fallback to RRF order if reranker fails.

    OBS-002 fix: both the success path and all fallback paths return
    RankedResult objects. The fallback maps HybridResult → RankedResult
    with reranker_score=None so the /search serialisation never hits
    an AttributeError when reading .reranker_score on fallback results.
    """
    if cross_encoder is None:
        log.warning("Reranker not loaded — returning hybrid results as-is")
        return _wrap_as_ranked(candidates[:top_n])

    try:
        return rerank(query, candidates, cross_encoder, top_n)
    except Exception as exc:
        log.error("Reranker failed, falling back to RRF order: %s", exc)
        return _wrap_as_ranked(candidates[:top_n])


def _wrap_as_ranked(candidates: list) -> list:
    """
    Convert HybridResult objects to RankedResult with reranker_score=None.

    OBS-002: ensures the /search route can always read .reranker_score
    regardless of whether the reranker ran or fell back.
    """
    return [
        RankedResult(
            chunk_id=c.chunk_id,
            domain=c.domain,
            content=c.content,
            source=c.source,
            reranker_score=None,          # not run — fallback path
            rrf_score=c.rrf_score,
            dense_rank=c.dense_rank,
            sparse_rank=c.sparse_rank,
        )
        for c in candidates
    ]
```

---

### 2. Settings additions

```python
# src/dev_rag/settings.py  (additions)

class Settings(BaseSettings):
    # ... existing fields ...

    # Reranker
    reranker_enabled: bool = True
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    reranker_top_n: int = 10          # final results returned after reranking
    reranker_candidates: int = 50     # candidates passed to reranker from Stage 1
    reranker_batch_size: int = 32     # pairs per forward pass
```

The `reranker_candidates` setting is important. You want to fetch more
candidates in Stage 1 than you return in Stage 2, giving the reranker
meaningful material to work with. 50 candidates → 10 final results is
a typical production ratio.

---

### 3. FastAPI startup and route changes

```python
# src/dev_rag/api.py  (additions)

from sentence_transformers import CrossEncoder
from .reranker import rerank_with_fallback
from .retrieve_hybrid import hybrid_search

# Module-level — initialised once at startup
_reranker: CrossEncoder | None = None


@app.on_event("startup")
async def startup():
    global _reranker
    if settings.reranker_enabled:
        log.info("Loading reranker: %s", settings.reranker_model)
        _reranker = CrossEncoder(
            settings.reranker_model,
            max_length=512,    # max tokens per (query + document) pair
        )
        log.info("Reranker loaded")


@app.post("/search")
async def search(request: SearchRequest) -> dict:
    collection = get_collection(request.domain)

    # Stage 1: hybrid search — fetch more candidates than we'll return
    candidates = await hybrid_search(
        query=request.query,
        domain=request.domain,
        chroma_collection=collection,
        db_path=settings.sqlite_db_path,
        n_results=settings.reranker_candidates,   # 50, not 10
    )

    # Stage 2: rerank (with fallback to RRF order if reranker unavailable)
    results = rerank_with_fallback(
        query=request.query,
        candidates=candidates,
        cross_encoder=_reranker,
        top_n=request.n_results,   # return what the caller asked for
    )

    return {
        "results": [
            {
                "chunk_id":        r.chunk_id,
                "source":          r.source,
                "domain":          r.domain,
                "content":         r.content,
                # OBS-001: single canonical field for all consumers
                # Set from reranker output when available, rrf_score on fallback
                "relevance_score": r.reranker_score if r.reranker_score is not None
                                   else r.rrf_score,
                # Preserved for debugging — not consumed by MCP or eval
                "rrf_score":       r.rrf_score,
                "dense_rank":      r.dense_rank,
                "sparse_rank":     r.sparse_rank,
            }
            for r in results
        ],
        "search_mode": request.search_mode,
        "reranker":    settings.reranker_model if settings.reranker_enabled else None,
        "query":       request.query,
    }
```

---

### 4. pyproject.toml addition

```toml
# Add to [project] dependencies in pyproject.toml
dependencies = [
    # ... existing deps ...
    "sentence-transformers>=3.0.0",   # provides CrossEncoder
    # OR use the dedicated rerankers library (cleaner API, same models):
    # "rerankers[transformers]>=0.5.0",
]
```

**`sentence-transformers` vs `rerankers` library:**

Both work. `sentence-transformers` is already likely in your stack for BGE-M3.
The `rerankers` library (by answerdotai) provides a cleaner unified API across
multiple reranker backends and makes it easier to swap models later. Either is
fine — use whichever is already installed.

---

### 5. Tests

```python
# tests/test_reranker.py

import pytest
from unittest.mock import MagicMock, patch
from dataclasses import dataclass

from dev_rag.reranker import rerank, rerank_with_fallback, RankedResult
from dev_rag.retrieve_hybrid import HybridResult


# ── Fixtures ──────────────────────────────────────────────────────────────────

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
    """Mock CrossEncoder that returns preset scores."""
    ce = MagicMock()
    ce.predict.return_value = scores
    return ce


# ── rerank() tests ────────────────────────────────────────────────────────────

def test_rerank_returns_top_n():
    candidates = _make_hybrid_results([
        ("c1", 0.9), ("c2", 0.8), ("c3", 0.7), ("c4", 0.6), ("c5", 0.5)
    ])
    ce = _mock_cross_encoder([0.9, 0.2, 0.8, 0.1, 0.7])
    results = rerank("docker secrets", candidates, ce, top_n=3)
    assert len(results) == 3


def test_rerank_order_follows_cross_encoder_not_rrf():
    """Reranker should override RRF order."""
    candidates = _make_hybrid_results([
        ("c1", 0.9),   # RRF rank 1
        ("c2", 0.8),   # RRF rank 2
        ("c3", 0.7),   # RRF rank 3
    ])
    # Cross-encoder reverses the order
    ce = _mock_cross_encoder([0.1, 0.5, 0.9])
    results = rerank("query", candidates, ce, top_n=3)

    assert results[0].chunk_id == "c3"   # lowest RRF, highest reranker
    assert results[1].chunk_id == "c2"
    assert results[2].chunk_id == "c1"   # highest RRF, lowest reranker


def test_rerank_preserves_rrf_score():
    """Original RRF score should be preserved on the result for debugging."""
    candidates = _make_hybrid_results([("c1", 0.95)])
    ce = _mock_cross_encoder([0.8])
    results = rerank("query", candidates, ce, top_n=1)
    assert results[0].rrf_score == pytest.approx(0.95)


def test_rerank_empty_candidates():
    ce = _mock_cross_encoder([])
    results = rerank("query", [], ce, top_n=5)
    assert results == []


def test_rerank_scores_are_descending():
    candidates = _make_hybrid_results([
        ("c1", 0.9), ("c2", 0.8), ("c3", 0.7)
    ])
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


def test_rerank_calls_predict_with_pairs():
    """Ensure the cross-encoder receives (query, content) pairs."""
    candidates = _make_hybrid_results([("c1", 0.9), ("c2", 0.8)])
    ce = _mock_cross_encoder([0.5, 0.7])
    rerank("my query", candidates, ce, top_n=2)

    call_args = ce.predict.call_args
    pairs = call_args[0][0]
    assert pairs[0] == ("my query", "Content about c1")
    assert pairs[1] == ("my query", "Content about c2")


# ── rerank_with_fallback() tests ──────────────────────────────────────────────

def test_fallback_when_reranker_is_none():
    """None reranker should return RankedResult objects in RRF order."""
    candidates = _make_hybrid_results([
        ("c1", 0.9), ("c2", 0.8), ("c3", 0.7)
    ])
    results = rerank_with_fallback("query", candidates, None, top_n=2)
    assert len(results) == 2
    assert results[0].chunk_id == "c1"   # original RRF order preserved
    # OBS-002: fallback returns RankedResult, not HybridResult
    assert isinstance(results[0], RankedResult)
    assert results[0].reranker_score is None   # not run — clearly flagged


def test_fallback_on_reranker_exception():
    """If predict() raises, should return RankedResult in RRF order."""
    candidates = _make_hybrid_results([("c1", 0.9), ("c2", 0.8)])
    ce = MagicMock()
    ce.predict.side_effect = RuntimeError("OOM")
    results = rerank_with_fallback("query", candidates, ce, top_n=2)
    assert len(results) == 2
    assert results[0].chunk_id == "c1"
    # OBS-002: even on exception fallback returns RankedResult not HybridResult
    assert isinstance(results[0], RankedResult)
    assert results[0].reranker_score is None


def test_fallback_top_n_respected_without_reranker():
    candidates = _make_hybrid_results([
        ("c1", 0.9), ("c2", 0.8), ("c3", 0.7), ("c4", 0.6)
    ])
    results = rerank_with_fallback("query", candidates, None, top_n=2)
    assert len(results) == 2
```

---

## New Files Summary

```
dev-rag/
├── src/dev_rag/
│   ├── reranker.py       # NEW — cross-encoder reranking + fallback
│   └── api.py            # MODIFIED — startup model load, reranker in /search
├── tests/
│   └── test_reranker.py  # NEW — 11 tests, all using mocked cross-encoder
└── planning/
    └── reranker-spec.md  # THIS document
```

---

## Implementation Order

1. **Add `sentence-transformers` to `pyproject.toml`** and run `uv sync`
2. **Implement `reranker.py`** — run its tests in isolation (all use mocks,
   no model download needed to pass tests)
3. **Add startup model load to `api.py`** — verify the model downloads and
   loads on first startup (this will take a few minutes)
4. **Wire reranker into `/search` route** — increase `n_results` for Stage 1,
   pass output to `rerank_with_fallback()`
5. **Run full test suite** — all 120 existing + 11 hybrid + 11 reranker = 142 tests
6. **Run the eval harness** — compare reranker results against hybrid-only baseline

---

## Latency Profile

Understanding the latency budget helps set `reranker_candidates` correctly:

| Stage | Typical latency | Notes |
|-------|----------------|-------|
| BGE-M3 embed (query) | 50–150ms | CPU; faster on GPU |
| ChromaDB ANN search | 10–50ms | In-process, very fast |
| SQLite FTS5 BM25 | 5–20ms | In-process, very fast |
| RRF fusion | <5ms | Pure Python, trivial |
| bge-reranker-v2-m3 (50 pairs, CPU) | 500ms–2s | The dominant cost |
| bge-reranker-v2-m3 (50 pairs, GPU) | 50–200ms | Much faster |

For a personal local tool used from Claude Code, 1–2 seconds total latency
is perfectly acceptable. If it feels slow, reduce `reranker_candidates`
from 50 to 20 — the quality difference is small and the latency drops
proportionally.

---

## Measuring the Reranker's Contribution

After implementing, run these two eval harness comparisons:

```bash
# Baseline: hybrid search, no reranker
DEV_RAG_RERANKER_ENABLED=false \
  uv run python eval/run_eval.py --domain devops > /dev/null
# (saves results/YYYY-MM-DD_HH-MM.json automatically)

# With reranker
DEV_RAG_RERANKER_ENABLED=true \
  uv run python eval/run_eval.py --domain devops \
  --compare eval/results/<baseline-timestamp>.json
```

Expected improvement: Retrieval@3 +5 to +15 points, MRR +5 to +10 points.
If the delta is smaller than +3 points on Retrieval@3, the corpus may be
too small for the reranker to make a meaningful difference yet — revisit
after ingesting more books.

The delta goes into ADR-012 as the measured evidence for why the reranker
was kept.

---

## Future: Reranker for cross-domain search_all

When `search_all` is called, it currently returns per-domain results
concatenated. The reranker enables a true cross-domain unified ranking:

```
devops_candidates (top 25 from hybrid)  ┐
                                         ├──► reranker ──► unified top-10
python_candidates (top 25 from hybrid)  ┘
```

The cross-encoder doesn't care which domain a candidate came from — it scores
(query, document) pairs directly. This makes cross-domain ranking a natural
future enhancement requiring no new models, just a change to how `search_all`
calls the reranker.

---

*Add this document to `planning/` alongside `rag-document-update-strategy.md`,
`hybrid-search-spec.md`, and `PRD-docker.md`.*
