"""
dev-rag cross-encoder reranker (Stage 2) — Phase 3.

Two-stage retrieval per ADR-012: hybrid search fetches a wide candidate
pool (settings.reranker_candidates), then bge-reranker-v2-m3 reads each
(query, passage) pair together and re-scores it — unlike RRF, which only
fuses ranks and never sees the text. Top-N by cross-encoder score wins.

The model (~568M params) is loaded once at FastAPI startup (api.py
lifespan) into the module-level `_reranker` singleton — same pattern as
dev_rag.retrieve._embedder, and injectable/monkeypatchable in tests the
same way. The test suite must never load the real model.

OBS-002 hard rule: rerank_with_fallback returns RankedResult objects on
the success path AND every fallback path (model missing, predict()
raising), with reranker_score=None marking "reranker did not run" — so
/search serialisation never sees a mixed type.

Spec: planning/reranker-spec.md
"""
import logging
from dataclasses import dataclass

from .settings import settings

log = logging.getLogger(__name__)

_reranker = None


def get_reranker(model_name: str | None = None):
    """Lazy singleton loader for the CrossEncoder (heavy imports deferred)."""
    global _reranker
    if _reranker is None:
        import torch
        from sentence_transformers import CrossEncoder

        device = "cuda" if torch.cuda.is_available() else "cpu"
        log.info("Loading reranker %s on %s", settings.reranker_model, device)
        _reranker = CrossEncoder(
            model_name or settings.reranker_model,
            max_length=512,     # tokens per (query + passage) pair
            device=device,
        )
        log.info("Reranker loaded: %s", settings.reranker_model)
    return _reranker


@dataclass
class RankedResult:
    chunk_id: str
    domain: str
    content: str
    source: str
    reranker_score: float | None   # cross-encoder output; None = fallback path
    rrf_score: float | None        # preserved from Stage 1 for debugging
    dense_rank: int | None
    sparse_rank: int | None


def rerank(
    query: str,
    candidates: list,              # list[HybridResult] from retrieve_hybrid
    cross_encoder,
    top_n: int = 10,
    batch_size: int | None = None,
) -> list[RankedResult]:
    """
    Re-score hybrid candidates with the cross-encoder; best score first.

    predict() batches internally (batch_size pairs per forward pass) and
    returns one float per (query, content) pair.
    """
    if not candidates:
        return []

    pairs = [(query, c.content) for c in candidates]
    scores = cross_encoder.predict(
        pairs,
        batch_size=batch_size or settings.reranker_batch_size,
        show_progress_bar=False,
    )

    scored = sorted(zip(scores, candidates), key=lambda x: x[0], reverse=True)
    return [
        RankedResult(
            chunk_id=c.chunk_id,
            domain=c.domain,
            content=c.content,
            source=c.source,
            reranker_score=float(score),
            rrf_score=c.rrf_score,
            dense_rank=c.dense_rank,
            sparse_rank=c.sparse_rank,
        )
        for score, c in scored[:top_n]
    ]


def rerank_with_fallback(
    query: str,
    candidates: list,
    cross_encoder,
    top_n: int = 10,
) -> list[RankedResult]:
    """Rerank, falling back to RRF order (OBS-002) if the model is missing
    or scoring fails."""
    if cross_encoder is None:
        log.warning("Reranker not loaded — returning hybrid results as-is")
        return _wrap_as_ranked(candidates[:top_n])

    try:
        return rerank(query, candidates, cross_encoder, top_n)
    except Exception as exc:
        log.error("Reranker failed, falling back to RRF order: %s", exc)
        return _wrap_as_ranked(candidates[:top_n])


def _wrap_as_ranked(candidates: list) -> list[RankedResult]:
    """HybridResult → RankedResult with reranker_score=None (did not run)."""
    return [
        RankedResult(
            chunk_id=c.chunk_id,
            domain=c.domain,
            content=c.content,
            source=c.source,
            reranker_score=None,
            rrf_score=c.rrf_score,
            dense_rank=c.dense_rank,
            sparse_rank=c.sparse_rank,
        )
        for c in candidates
    ]
