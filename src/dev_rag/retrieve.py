"""
dev-rag dense retrieval — BGE-M3 query embedding + ChromaDB ANN search.

Phase 1a collections have NO bound embedding function (ingest passes
embeddings explicitly), so the query must be embedded here and passed as
query_embeddings — chromadb's query_texts= would fail. See
docs/plans/dev-rag-phase2-plan.md ("Spec vs. reality" #2).

The embedder is a lazy module-level singleton: loaded once on first
search (~10 s CPU), shared with api.py, and injectable/monkeypatchable
in tests — never load real BGE-M3 in the test suite.
"""
import logging
from dataclasses import dataclass

from .settings import settings

log = logging.getLogger(__name__)

_embedder = None


def get_query_embedder():
    """Lazy singleton around the same BGE-M3 loader ingest uses."""
    global _embedder
    if _embedder is None:
        from dev_rag.ingest.embed import get_embedder
        _embedder = get_embedder()
    return _embedder


@dataclass
class DenseResult:
    chunk_id: str
    domain: str
    content: str
    source: str            # filename, from Chroma metadata
    dense_score: float     # cosine similarity (1 - cosine distance)


def dense_search(
    query: str,
    domain: str,
    chroma_path: str | None = None,
    n_results: int | None = None,
    model=None,
) -> list[DenseResult]:
    """
    Embed the query and run ANN search in the domain's collection.

    Returns [] if the domain has no collection yet (nothing ingested) —
    degraded-but-working beats a 500 for a personal tool, and the
    search_all fan-out will legitimately hit un-ingested domains.
    """
    import chromadb
    from chromadb.config import Settings as ChromaSettings

    client = chromadb.PersistentClient(
        path=chroma_path or settings.chroma_db_path,
        settings=ChromaSettings(anonymized_telemetry=False),
    )
    try:
        collection = client.get_collection(f"{domain}_content")
    except Exception:  # chromadb's missing-collection error type varies by version
        log.warning("no collection for domain %r — returning no dense results", domain)
        return []

    model = model or get_query_embedder()
    embedding = model.encode(
        query, convert_to_numpy=True, normalize_embeddings=True,
    ).tolist()

    response = collection.query(
        query_embeddings=[embedding],
        n_results=n_results or settings.dense_candidates,
        include=["documents", "metadatas", "distances"],
    )

    results = []
    if response["ids"] and response["ids"][0]:
        for chunk_id, doc, meta, dist in zip(
            response["ids"][0],
            response["documents"][0],
            response["metadatas"][0],
            response["distances"][0],
        ):
            results.append(DenseResult(
                chunk_id=chunk_id,
                domain=meta.get("domain", domain),
                content=doc,
                source=meta.get("source", ""),
                dense_score=1.0 - dist,
            ))
    return results
