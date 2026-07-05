"""
dev-rag hybrid retrieval — RRF fusion of dense (ChromaDB) + sparse (BM25).

RRF: score(doc) = Σ 1/(k + rank_in_list). Only rank matters, never the
raw scores — which is exactly why it can fuse cosine similarity and BM25,
two scales that are not comparable. Documents appearing in both lists sum
both contributions; documents in only one list keep that one (BM25 may
surface an exact-token match dense missed entirely — it must survive).

Adapted from planning/hybrid-search-spec.md §3 per the Phase 2 plan:
takes DenseResult/SparseResult dataclasses (spec used raw dicts), and
sparse-only results already carry their source filename (stage 2 JOINs
sources), so no post-hoc enrichment step is needed. Plain sync functions
— nothing here awaits anything, and this is a single-user tool.
"""
from dataclasses import dataclass
from pathlib import Path

from .retrieve import DenseResult, dense_search
from .retrieve_sparse import SparseResult, bm25_search
from .settings import settings


@dataclass
class HybridResult:
    chunk_id: str
    domain: str
    content: str
    source: str
    rrf_score: float
    dense_rank: int | None     # rank in dense list (None if absent)
    sparse_rank: int | None    # rank in BM25 list (None if absent)
    dense_score: float | None
    bm25_score: float | None


def reciprocal_rank_fusion(
    dense_results: list[DenseResult],
    sparse_results: list[SparseResult],
    k: int | None = None,
) -> list[HybridResult]:
    """Fuse two ranked lists; best RRF score first."""
    k = k or settings.rrf_k
    scores: dict[str, dict] = {}

    for rank, r in enumerate(dense_results, start=1):
        scores[r.chunk_id] = {
            "chunk_id":    r.chunk_id,
            "domain":      r.domain,
            "content":     r.content,
            "source":      r.source,
            "rrf_score":   1.0 / (k + rank),
            "dense_rank":  rank,
            "sparse_rank": None,
            "dense_score": r.dense_score,
            "bm25_score":  None,
        }

    for rank, r in enumerate(sparse_results, start=1):
        contribution = 1.0 / (k + rank)
        if r.chunk_id in scores:
            entry = scores[r.chunk_id]
            entry["rrf_score"] += contribution
            entry["sparse_rank"] = rank
            entry["bm25_score"] = r.bm25_score
        else:
            scores[r.chunk_id] = {
                "chunk_id":    r.chunk_id,
                "domain":      r.domain,
                "content":     r.content,
                "source":      r.source,
                "rrf_score":   contribution,
                "dense_rank":  None,
                "sparse_rank": rank,
                "dense_score": None,
                "bm25_score":  r.bm25_score,
            }

    fused = sorted(scores.values(), key=lambda e: e["rrf_score"], reverse=True)
    return [HybridResult(**e) for e in fused]


def hybrid_search(
    query: str,
    domain: str,
    chroma_path: str | None = None,
    db_path: Path | None = None,
    n_results: int | None = None,
    dense_candidates: int | None = None,
    sparse_candidates: int | None = None,
    model=None,
) -> list[HybridResult]:
    """
    Dense + BM25, fused with RRF; top n_results after fusion.

    Both backends fetch more candidates than requested (settings:
    dense_candidates/sparse_candidates, default 20/20) so fusion has
    material to work with.
    """
    dense = dense_search(
        query, domain,
        chroma_path=chroma_path,
        n_results=dense_candidates or settings.dense_candidates,
        model=model,
    )
    sparse = bm25_search(
        query, domain,
        db_path=db_path,
        n_results=sparse_candidates or settings.sparse_candidates,
    )
    fused = reciprocal_rank_fusion(dense, sparse)
    return fused[:n_results or 10]
