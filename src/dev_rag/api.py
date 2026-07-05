"""
dev-rag FastAPI application — hybrid retrieval (Phase 2).

/search runs dense | sparse | hybrid retrieval and always emits the
canonical `relevance_score` (OBS-001 hard rule). Score semantics are
PER-MODE and not comparable across modes:
  hybrid → RRF score          (~0.01-0.033)
  dense  → cosine similarity  (0-1)
  sparse → negated BM25       (unbounded positive)
`rrf_score`/`dense_rank`/`sparse_rank` remain as optional debug fields.

The BGE-M3 query embedder loads lazily on the FIRST search (~10 s CPU),
not at startup — keeps uvicorn boot and the test suite fast (tests
inject a fake via dev_rag.retrieve). Reranking is Phase 3; until then
relevance_score = the mode's own score (documented OBS-001 fallback).

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
    """Startup/shutdown. Embedder is lazy (see module docstring)."""
    # TODO Phase 3: load bge-reranker-v2-m3 here (see planning/reranker-spec.md)
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
    module docstring. Reranking arrives in Phase 3 (until then this is
    the documented relevance_score = mode-score fallback; OBS-002's
    RankedResult wrapping applies when the reranker stage lands).
    """
    if request.search_mode == SearchMode.hybrid:
        results = [
            SearchResult(
                chunk_id=r.chunk_id,
                source=r.source,
                domain=r.domain,
                content=r.content,
                relevance_score=r.rrf_score,
                rrf_score=r.rrf_score,
                dense_rank=r.dense_rank,
                sparse_rank=r.sparse_rank,
            )
            for r in hybrid_search(
                request.query, request.domain, n_results=request.n_results,
            )
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
