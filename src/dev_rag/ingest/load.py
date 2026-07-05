"""
Stage 7: Load — write chunks and embeddings to ChromaDB and SQLite.

Load DEFINES the storage contract (retrieve.py is an empty stub):
- Chroma collection "{domain}_content", cosine space (embeddings are
  L2-normalized by Stage 6), per-chunk metadata >= source, domain,
  page_number, chunk_id.
- SQLite per migrations/001 (+002's trigger auto-populates chunks_fts
  on insert, so Phase 2 hybrid search needs no re-ingest).

Idempotency via content_hash: a chunk whose stored hash is unchanged is
skipped; changed or new chunks are upserted in both stores. Count parity
across ChromaDB / SQLite / FTS is asserted after every load — a mismatch
raises rather than silently degrading future RRF results (OBS-009).

Spec: planning/ingest-pipeline-spec.md (Stage 7) +
docs/plans/dev-rag-phase1a-plan.md (storage contract).
"""
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass
class LoadStats:
    inserted: int          # new or changed chunks written
    skipped: int           # unchanged chunks (hash match)
    chroma_count: int      # chunks in the domain collection
    sqlite_count: int      # active chunks for this domain
    fts_count: int         # rows in chunks_fts for this domain


def apply_migrations(sqlite_path: Path, migrations_dir: Path = Path("migrations")) -> None:
    """Apply all SQL migrations in filename order (all use IF NOT EXISTS)."""
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(sqlite_path)
    try:
        for script in sorted(migrations_dir.glob("*.sql")):
            conn.executescript(script.read_text())
        conn.commit()
    finally:
        conn.close()


def load_to_stores(
    chunks: list[dict],
    embeddings: list[list[float]],
    chroma_path: str,
    sqlite_path: Path,
    migrations_dir: Path = Path("migrations"),
) -> LoadStats:
    """Write chunks + embeddings to both stores; assert count parity."""
    if len(chunks) != len(embeddings):
        raise ValueError(f"{len(chunks)} chunks but {len(embeddings)} embeddings")

    import chromadb
    from chromadb.config import Settings as ChromaSettings

    domain = chunks[0]["domain"]
    source_id = chunks[0]["source_id"]

    apply_migrations(sqlite_path, migrations_dir)
    conn = sqlite3.connect(sqlite_path)
    try:
        # Upsert the source row (chunks reference sources.source_id)
        conn.execute(
            """INSERT INTO sources (source_id, domain, source_path, source_type)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(source_id) DO UPDATE SET
                 domain=excluded.domain, source_path=excluded.source_path""",
            (source_id, domain, chunks[0]["source"], "pdf"),
        )

        # Partition on stored content_hash for idempotent re-runs
        stored = dict(conn.execute(
            "SELECT chunk_id, content_hash FROM chunks WHERE source_id = ?",
            (source_id,),
        ).fetchall())
        changed = [
            (c, e) for c, e in zip(chunks, embeddings)
            if stored.get(c["chunk_id"]) != c["content_hash"]
        ]

        # Explicit DELETE + INSERT, not INSERT OR REPLACE: REPLACE's
        # implicit delete does NOT fire the 002 FTS delete trigger
        # (recursive_triggers is off by default), which would leave a
        # stale chunks_fts row behind on content updates
        conn.executemany(
            "DELETE FROM chunks WHERE chunk_id = ?",
            [(c["chunk_id"],) for c, _ in changed],
        )
        conn.executemany(
            """INSERT INTO chunks
               (chunk_id, source_id, domain, content, page_number, content_hash)
               VALUES (?, ?, ?, ?, ?, ?)""",
            [
                (c["chunk_id"], c["source_id"], c["domain"], c["content"],
                 c["page_number"], c["content_hash"])
                for c, _ in changed
            ],
        )
        conn.commit()

        client = chromadb.PersistentClient(
            path=chroma_path,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        collection = client.get_or_create_collection(
            f"{domain}_content",
            metadata={"hnsw:space": "cosine"},
        )
        if changed:
            collection.upsert(
                ids=[c["chunk_id"] for c, _ in changed],
                embeddings=[e for _, e in changed],
                documents=[c["content"] for c, _ in changed],
                metadatas=[
                    {
                        "chunk_id": c["chunk_id"],
                        "source": c["source"],
                        "source_id": c["source_id"],
                        "domain": c["domain"],
                        "title": c["title"],
                        "page_number": c["page_number"],
                    }
                    for c, _ in changed
                ],
            )

        stats = LoadStats(
            inserted=len(changed),
            skipped=len(chunks) - len(changed),
            chroma_count=collection.count(),
            sqlite_count=conn.execute(
                "SELECT count(*) FROM chunks WHERE domain = ? AND status = 'active'",
                (domain,),
            ).fetchone()[0],
            fts_count=conn.execute(
                "SELECT count(*) FROM chunks_fts WHERE domain = ?", (domain,),
            ).fetchone()[0],
        )
    finally:
        conn.close()

    if not (stats.chroma_count == stats.sqlite_count == stats.fts_count):
        raise ValueError(
            f"store parity violated: chroma={stats.chroma_count} "
            f"sqlite={stats.sqlite_count} fts={stats.fts_count}"
        )
    return stats


def load_embeddings(path: Path) -> list[dict]:
    """Load a Stage 6 embeddings JSON."""
    return json.loads(path.read_text())
