"""
Stage 8: Verify — confirm the ingest produced a working, queryable corpus.

STORE-LEVEL on purpose: checks ChromaDB and SQLite directly, NOT via
/search or /health — those are Phase 2 surface (/health parity is
OBS-009). Two checks:
  (a) count parity across ChromaDB / SQLite chunks / chunks_fts
  (b) a sample domain query embedded and run against ChromaDB returns
      at least one chunk from the expected source

Spec: planning/ingest-pipeline-spec.md (Stage 8, store-level per
docs/plans/dev-rag-phase1a-plan.md).
"""
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path


class VerificationError(Exception):
    """Raised when the ingested corpus fails a store-level check."""


@dataclass
class VerifyReport:
    domain: str
    chroma_count: int
    sqlite_count: int
    fts_count: int
    query: str
    top_results: list[dict] = field(default_factory=list)

    @property
    def parity_ok(self) -> bool:
        return self.chroma_count == self.sqlite_count == self.fts_count > 0


def verify_ingest(
    domain: str,
    expected_source: str,
    query: str,
    chroma_path: str,
    sqlite_path: Path,
    model,
    n_results: int = 5,
) -> VerifyReport:
    """
    Run both store-level checks; raise VerificationError on failure.

    `model` is injected (real BGE-M3 from embed.get_embedder() in
    production, a mock in tests).
    """
    import chromadb
    from chromadb.config import Settings as ChromaSettings

    conn = sqlite3.connect(sqlite_path)
    try:
        sqlite_count = conn.execute(
            "SELECT count(*) FROM chunks WHERE domain = ? AND status = 'active'",
            (domain,),
        ).fetchone()[0]
        fts_count = conn.execute(
            "SELECT count(*) FROM chunks_fts WHERE domain = ?", (domain,),
        ).fetchone()[0]
    finally:
        conn.close()

    client = chromadb.PersistentClient(
        path=chroma_path,
        settings=ChromaSettings(anonymized_telemetry=False),
    )
    collection = client.get_collection(f"{domain}_content")

    query_embedding = model.encode(
        query, convert_to_numpy=True, normalize_embeddings=True,
    ).tolist()
    hits = collection.query(
        query_embeddings=[query_embedding],
        n_results=n_results,
        include=["metadatas", "documents", "distances"],
    )

    report = VerifyReport(
        domain=domain,
        chroma_count=collection.count(),
        sqlite_count=sqlite_count,
        fts_count=fts_count,
        query=query,
        top_results=[
            {
                "chunk_id": meta["chunk_id"],
                "source": meta["source"],
                "page_number": meta["page_number"],
                "distance": dist,
                "snippet": doc[:120],
            }
            for meta, doc, dist in zip(
                hits["metadatas"][0], hits["documents"][0], hits["distances"][0],
            )
        ],
    )

    if not report.parity_ok:
        raise VerificationError(
            f"store parity failed: chroma={report.chroma_count} "
            f"sqlite={report.sqlite_count} fts={report.fts_count}"
        )
    if not any(r["source"] == expected_source for r in report.top_results):
        raise VerificationError(
            f"query {query!r} returned no chunk from {expected_source!r}; "
            f"sources: {[r['source'] for r in report.top_results]}"
        )
    return report
