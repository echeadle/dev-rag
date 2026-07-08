"""
dev-rag FastAPI application — hybrid retrieval (Phase 2).

/search runs dense | sparse | hybrid retrieval and always emits the
canonical `relevance_score` (OBS-001 hard rule). Score semantics are
PER-MODE and not comparable across modes:
  hybrid → cross-encoder logit (unbounded, roughly -10..+10) when the
           reranker ran; RRF score (~0.01-0.033) on fallback — check the
           per-result `reranker_score` debug field to tell which
  dense  → cosine similarity  (0-1)
  sparse → negated BM25       (unbounded positive)
`rrf_score`/`reranker_score`/`dense_rank`/`sparse_rank` are debug fields.
`weak_match` (FBL-006) flags a low-confidence hit when the reranker ran and
scored it below settings.reranker_min_score; None means the reranker did not
run, so confidence is unknowable (RRF encodes rank, not relevance).

The BGE-M3 query embedder loads lazily on the FIRST search (~10 s CPU);
the reranker loads EAGERLY at startup via lifespan when enabled
(ADR-012). Tests inject fakes via dev_rag.retrieve._embedder and
dev_rag.reranker._reranker — the suite never loads real models.
Hybrid is two-stage (Phase 3): top-`reranker_candidates` from RRF, then
bge-reranker-v2-m3 re-scores and returns the caller's n_results.

Fixes applied:
  OBS-001: /search always emits `relevance_score` — never rrf_score/reranker_score/score
  OBS-002: rerank fallback returns RankedResult(reranker_score=None) not raw HybridResult
  OBS-004: cross-domain and graph endpoints gated off until implemented
  OBS-009: /health store_parity reports REAL ChromaDB/SQLite counts per domain
  OBS-010: startup uses lifespan context manager, not deprecated on_event
"""
import sqlite3
from contextlib import asynccontextmanager
from enum import Enum

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, field_validator

from . import reranker
from .reranker import rerank_with_fallback
from .retrieve import dense_search
from .retrieve_hybrid import hybrid_search
from .retrieve_sparse import bm25_search
from .settings import settings

import logging
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lifespan — model loading (OBS-010: replaces deprecated @app.on_event)
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown. Embedder is lazy (see module docstring); the
    reranker loads eagerly here (ADR-012: once per process, ~seconds)."""
    if settings.reranker_enabled:
        reranker.get_reranker()
    log.info("dev-rag startup complete")
    yield
    log.info("dev-rag shutdown")


app = FastAPI(title="dev-rag", version="0.1.0", lifespan=lifespan)


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class SearchMode(str, Enum):
    dense = "dense"     # vector only
    sparse = "sparse"   # BM25 only (debugging / ablation)
    hybrid = "hybrid"   # dense + BM25 + RRF (default)


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    domain: str
    n_results: int = Field(default=5, ge=1, le=50)
    search_mode: SearchMode = SearchMode.hybrid

    @field_validator("domain")
    @classmethod
    def domain_must_be_valid(cls, v):
        if v not in settings.valid_domains:
            raise ValueError(f"domain must be one of {settings.valid_domains}")
        return v


class SearchResult(BaseModel):
    chunk_id: str
    source: str
    domain: str
    content: str
    relevance_score: float          # OBS-001: single canonical field for all callers
    rrf_score: float | None = None  # preserved for debugging — not for consumers
    reranker_score: float | None = None  # debug; None = reranker didn't run
    # FBL-006: True when the reranker ran AND scored this result below
    # settings.reranker_min_score (low-confidence). None = reranker didn't run,
    # so confidence can't be judged (RRF encodes rank, not relevance).
    weak_match: bool | None = None
    dense_rank: int | None = None
    sparse_rank: int | None = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

def _chroma_counts() -> dict[str, int]:
    """Per-domain chunk counts from ChromaDB; missing collections count 0."""
    import chromadb
    from chromadb.config import Settings as ChromaSettings

    client = chromadb.PersistentClient(
        path=settings.chroma_db_path,
        settings=ChromaSettings(anonymized_telemetry=False),
    )
    counts = {}
    for domain in settings.valid_domains:
        try:
            counts[domain] = client.get_collection(f"{domain}_content").count()
        except Exception:  # missing collection (error type varies by chromadb version)
            counts[domain] = 0
    return counts


def _sqlite_counts() -> dict[str, int]:
    """Per-domain active chunk counts from SQLite; missing DB/schema counts 0."""
    counts = dict.fromkeys(settings.valid_domains, 0)
    try:
        conn = sqlite3.connect(settings.sqlite_db_path)
        try:
            rows = conn.execute(
                "SELECT domain, count(*) FROM chunks "
                "WHERE status = 'active' GROUP BY domain"
            ).fetchall()
        finally:
            conn.close()
    except sqlite3.OperationalError:
        return counts
    for domain, n in rows:
        if domain in counts:
            counts[domain] = n
    return counts


@app.get("/health")
async def health():
    """
    Health check including ChromaDB/SQLite parity check.
    OBS-009: surfaces store drift before it silently degrades RRF results.
    """
    chroma = _chroma_counts()
    sqlite_ = _sqlite_counts()
    parity = {
        domain: {
            "chroma_chunks": chroma[domain],
            "sqlite_chunks": sqlite_[domain],
            "in_sync": chroma[domain] == sqlite_[domain],
        }
        for domain in settings.valid_domains
    }
    stores_in_sync = all(p["in_sync"] for p in parity.values())

    return {
        "status": "ok" if stores_in_sync else "degraded",
        "version": "0.1.0",
        "search_mode": settings.search_mode,
        "reranker_enabled": settings.reranker_enabled,
        "valid_domains": settings.valid_domains,
        "store_parity": parity,           # OBS-009: drift visible here
        "stores_in_sync": stores_in_sync,
    }


@app.post("/search")
async def search(request: SearchRequest) -> dict:
    """
    Retrieval in the requested mode. Always returns canonical
    `relevance_score` (OBS-001); value semantics are per-mode — see the
    module docstring. Hybrid mode is two-stage: RRF candidates, then the
    cross-encoder (with OBS-002 RankedResult fallback to RRF order).
    Dense/sparse are single-stage diagnostic modes and never rerank.
    """
    if request.search_mode == SearchMode.hybrid:
        # Stage 1: with the reranker on, fetch a wide pool (ADR-012's 50→N);
        # the backends must also widen or fusion can never fill the pool.
        if settings.reranker_enabled:
            pool = settings.reranker_candidates
            candidates = hybrid_search(
                request.query, request.domain, n_results=pool,
                dense_candidates=pool, sparse_candidates=pool,
            )
        else:
            candidates = hybrid_search(
                request.query, request.domain, n_results=request.n_results,
            )
        # Stage 2: cross-encoder re-score. Falls back to RRF order (OBS-002)
        # when the reranker is disabled, not loaded, or raises.
        ranked = rerank_with_fallback(
            request.query,
            candidates,
            reranker._reranker if settings.reranker_enabled else None,
            top_n=request.n_results,
        )
        results = [
            SearchResult(
                chunk_id=r.chunk_id,
                source=r.source,
                domain=r.domain,
                content=r.content,
                # OBS-001: canonical field — reranker score when it ran,
                # RRF score on any fallback path
                relevance_score=r.reranker_score
                if r.reranker_score is not None else r.rrf_score,
                rrf_score=r.rrf_score,
                reranker_score=r.reranker_score,
                # FBL-006: flag low-confidence hits (sigmoid score below the
                # gate). None on any fallback path where the reranker didn't run.
                weak_match=(r.reranker_score < settings.reranker_min_score)
                if r.reranker_score is not None else None,
                dense_rank=r.dense_rank,
                sparse_rank=r.sparse_rank,
            )
            for r in ranked
        ]
    elif request.search_mode == SearchMode.dense:
        results = [
            SearchResult(
                chunk_id=r.chunk_id,
                source=r.source,
                domain=r.domain,
                content=r.content,
                relevance_score=r.dense_score,
            )
            for r in dense_search(
                request.query, request.domain, n_results=request.n_results,
            )
        ]
    else:  # SearchMode.sparse
        results = [
            SearchResult(
                chunk_id=r.chunk_id,
                source=r.source,
                domain=r.domain,
                content=r.content,
                relevance_score=r.bm25_score,
            )
            for r in bm25_search(
                request.query, request.domain, n_results=request.n_results,
            )
        ]

    return {
        "results": [r.model_dump() for r in results],
        "query": request.query,
        "domain": request.domain,
        "search_mode": request.search_mode.value,
        "reranker": settings.reranker_model if settings.reranker_enabled else None,
    }


@app.get("/documents/{document_id}")
async def get_document(document_id: str, domain: str = ""):
    # TODO: implement document retrieval by ID
    raise HTTPException(status_code=404, detail=f"Document {document_id} not found")


@app.get("/collections")
async def list_collections():
    """Per-domain chunk counts from ChromaDB (missing collections count 0)."""
    counts = _chroma_counts()
    return {
        "collections": [
            {
                "name": domain,
                "documents": counts[domain],
                "status": "ready" if counts[domain] else "empty",
            }
            for domain in settings.valid_domains
        ]
    }


# ---------------------------------------------------------------------------
# OBS-004: Cross-domain and graph endpoints — gated off until implemented
# ---------------------------------------------------------------------------
# These routes are intentionally not defined yet:
#
#   POST /search (with domain=None)  — cross-domain requires explicit design
#   POST /search/graph               — GraphRAG has no spec yet (open question)
#
# The eval runner.py gates both behind feature flags before calling them.
# Uncomment and implement when the relevant specs are written.
