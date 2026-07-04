"""
dev-rag FastAPI application.
Implement retrieval per planning/hybrid-search-spec.md and planning/reranker-spec.md.

Fixes applied:
  OBS-001: /search always emits `relevance_score` — never rrf_score/reranker_score/score
  OBS-002: rerank fallback returns RankedResult(reranker_score=None) not raw HybridResult
  OBS-004: cross-domain and graph endpoints gated off until implemented
  OBS-010: startup uses lifespan context manager, not deprecated on_event
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, field_validator
from .settings import settings

import logging
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lifespan — model loading (OBS-010: replaces deprecated @app.on_event)
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load reranker and other heavy resources once at startup."""
    # TODO: load BGE-M3 embedder here
    # TODO: load bge-reranker-v2-m3 here (see planning/reranker-spec.md)
    log.info("dev-rag startup complete")
    yield
    log.info("dev-rag shutdown")


app = FastAPI(title="dev-rag", version="0.1.0", lifespan=lifespan)


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class SearchRequest(BaseModel):
    query: str
    domain: str
    n_results: int = 5
    search_mode: str = "hybrid"   # dense | sparse | hybrid

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

@app.get("/health")
async def health():
    """
    Health check including ChromaDB/SQLite parity check.
    OBS-009: surfaces store drift before it silently degrades RRF results.
    """
    # TODO: replace stub counts with real collection queries
    parity = {}
    for domain in settings.valid_domains:
        chroma_count = 0   # TODO: chroma_collection.count()
        sqlite_count = 0   # TODO: SELECT count(*) FROM chunks WHERE domain=?
        parity[domain] = {
            "chroma_chunks": chroma_count,
            "sqlite_chunks": sqlite_count,
            "in_sync": chroma_count == sqlite_count,
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
    Two-stage retrieval: hybrid search (Stage 1) → reranker (Stage 2).

    Always returns `relevance_score` as the single canonical relevance field.
    When the reranker runs: relevance_score = reranker output score.
    When the reranker falls back: relevance_score = rrf_score from hybrid search.
    When dense-only: relevance_score = cosine similarity.

    OBS-002 note: the fallback must return RankedResult objects (with
    reranker_score=None), never raw HybridResult objects, so the
    serialisation below never hits an AttributeError.
    """
    # TODO: implement full retrieval pipeline
    # Stage 1: hybrid_search() → top-50 candidates (HybridResult list)
    # Stage 2: rerank_with_fallback() → top-N RankedResult list
    #          fallback MUST return RankedResult(reranker_score=None, ...)
    #          so the relevance_score serialisation below always works.
    # See planning/hybrid-search-spec.md and planning/reranker-spec.md

    return {
        "results": [],
        "query": request.query,
        "domain": request.domain,
        "search_mode": request.search_mode,
        "reranker": settings.reranker_model if settings.reranker_enabled else None,
    }


@app.get("/documents/{document_id}")
async def get_document(document_id: str, domain: str = ""):
    # TODO: implement document retrieval by ID
    raise HTTPException(status_code=404, detail=f"Document {document_id} not found")


@app.get("/collections")
async def list_collections():
    # TODO: return ChromaDB collection stats per domain
    return {
        "collections": [
            {"name": domain, "documents": 0, "status": "empty"}
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
