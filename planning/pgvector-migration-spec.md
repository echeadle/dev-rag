# dev-rag pgvector Migration — Implementation Spec

**Version:** 1.0  
**Date:** June 2026  
**Status:** Ready to implement — after hybrid search, reranker, and eval
harness baseline are established with ChromaDB

---

## Why Migrate from ChromaDB to pgvector

ChromaDB was the right starting point (ADR-003) — it has a batteries-included
Python API, zero infrastructure overhead, and gets a working retrieval system
running quickly. The migration to pgvector is not a correction of a mistake;
it is the planned second step in the build-and-swap learning approach.

**What pgvector gives you that ChromaDB does not:**

1. **Hybrid search in a single SQL query.** ChromaDB requires a separate FTS5
   SQLite index (our current approach) for BM25. pgvector + Postgres `tsvector`
   does dense + lexical hybrid search in one query using native RRF fusion.
   The two-database architecture (ChromaDB + SQLite) collapses to one.

2. **Full SQL for metadata filtering.** ChromaDB's metadata filter is limited
   to simple equality and range operations. Postgres gives you joins, aggregates,
   subqueries, and full-text expressions against chunk metadata — useful as the
   corpus grows and queries become more complex.

3. **ACID transactions.** Ingest operations that update both vectors and
   metadata are atomic in Postgres. In the current setup, ChromaDB and SQLite
   are separate systems that can drift out of sync if a write fails mid-ingest.

4. **One infrastructure component.** The current Docker Compose runs ChromaDB
   (in-process) and SQLite (file). pgvector means one Postgres container
   handles vectors, metadata, FTS, and graph storage if desired.

5. **Mature operational tooling.** Postgres has decades of backup, monitoring,
   replication, and tuning tooling. ChromaDB is newer and has less operational
   history.

**What ChromaDB gives you that pgvector requires effort for:**

- Zero-config startup (no Postgres to configure)
- Built-in embedding function binding to collections
- Simpler Python API for basic use cases

The migration is worth doing once the system is working and the eval harness
gives you a baseline to compare against.

---

## Security Note

pgvector versions 0.6.0–0.8.1 contain a buffer overflow in parallel HNSW
index builds that can leak data from other relations. Always use 0.8.2 or
later. Verify with:

```sql
SELECT extversion FROM pg_extension WHERE extname = 'vector';
```

**OBS-011 fix:** The Docker image in this spec uses the explicit pinned tag:

```
pgvector/pgvector:pg16-0.8.2
```

This is the `pgvector 0.8.2` build on `Postgres 16`. If a newer patch is
available when you deploy, use the latest `pg16-0.8.x` tag where x ≥ 2.
Check current available tags at: https://hub.docker.com/r/pgvector/pgvector/tags

Do not use the untagged `pgvector/pgvector:pg16` image — it floats to
whatever the latest release is and may introduce breaking changes.

---

## Architecture After Migration

### Current (ChromaDB + SQLite)

```
Ingest pipeline
    ├──► ChromaDB (vectors, per-domain collections)
    └──► SQLite  (chunk metadata + FTS5 BM25 index)

Query pipeline
    ├──► ChromaDB ANN search   ──► dense_results
    ├──► SQLite FTS5 BM25      ──► sparse_results
    └──► Python RRF fusion     ──► fused_results
                                       │
                                  bge-reranker
                                       │
                                  top-10 results
```

### After migration (pgvector only)

```
Ingest pipeline
    └──► Postgres + pgvector
             ├── chunks table (content, embedding vector, tsvector, metadata)
             ├── sources table (source-level metadata)
             └── HNSW index on embedding column

Query pipeline
    └──► Single SQL query (dense ANN + tsvector BM25 + RRF in SQL)
                │
           bge-reranker (unchanged)
                │
           top-10 results
```

The reranker, MCP server, and FastAPI routes are **unchanged**. Only the
retrieval backend swaps.

---

## Database Schema

```sql
-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Source documents table (replaces SQLite sources table)
CREATE TABLE sources (
    source_id         TEXT PRIMARY KEY,
    domain            TEXT NOT NULL,          -- devops | python | ai
    source_path       TEXT NOT NULL,          -- file path or URL
    source_type       TEXT NOT NULL,          -- pdf | url
    version           TEXT,
    ingest_timestamp  TIMESTAMPTZ DEFAULT NOW(),
    status            TEXT DEFAULT 'active'   -- active | superseded
);

-- Chunks table (replaces ChromaDB collections + SQLite chunks table)
CREATE TABLE chunks (
    chunk_id          TEXT PRIMARY KEY,
    source_id         TEXT NOT NULL REFERENCES sources(source_id) ON DELETE CASCADE,
    domain            TEXT NOT NULL,
    content           TEXT NOT NULL,
    page_number       INTEGER,
    content_hash      TEXT NOT NULL,
    ingest_timestamp  TIMESTAMPTZ DEFAULT NOW(),
    status            TEXT DEFAULT 'active',  -- active | deleted

    -- Dense vector (BGE-M3 produces 1024-dimensional vectors)
    embedding         vector(1024),

    -- Sparse / lexical index (auto-maintained by Postgres)
    tsv               tsvector
                      GENERATED ALWAYS AS (to_tsvector('english', content)) STORED
);

-- HNSW index for fast approximate nearest-neighbour search
-- m=16, ef_construction=64 are standard starting values for personal-scale corpus
CREATE INDEX chunks_embedding_idx ON chunks
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- GIN index for fast full-text search
CREATE INDEX chunks_tsv_idx ON chunks USING GIN(tsv);

-- Domain filter index (used in WHERE domain = $1 on every query)
CREATE INDEX chunks_domain_idx ON chunks(domain);

-- Source lookup index
CREATE INDEX chunks_source_idx ON chunks(source_id);

-- Content hash index (used for incremental upsert update detection)
CREATE INDEX chunks_hash_idx ON chunks(content_hash);
```

---

## Hybrid Search SQL Query

This single query replaces the current Python RRF fusion across ChromaDB
and SQLite FTS5. It is the direct pgvector equivalent of the two-stage
retrieval in `retrieve_hybrid.py`.

```sql
-- Hybrid search: dense ANN + BM25 lexical, fused with RRF
-- Parameters: $1 = query_embedding (vector), $2 = domain, $3 = tsquery, $4 = limit

WITH dense AS (
    -- Dense vector ANN search using HNSW index
    SELECT
        chunk_id,
        ROW_NUMBER() OVER (ORDER BY embedding <=> $1) AS rank,
        1 - (embedding <=> $1)                        AS cosine_score
    FROM chunks
    WHERE domain = $2
      AND status = 'active'
    ORDER BY embedding <=> $1
    LIMIT 50   -- fetch more candidates than needed for RRF
),
sparse AS (
    -- BM25 full-text search using tsvector GIN index
    SELECT
        chunk_id,
        ROW_NUMBER() OVER (ORDER BY ts_rank_cd(tsv, query) DESC) AS rank,
        ts_rank_cd(tsv, query)                                    AS bm25_score
    FROM chunks, to_tsquery('english', $3) query
    WHERE tsv @@ query
      AND domain = $2
      AND status = 'active'
    ORDER BY ts_rank_cd(tsv, query) DESC
    LIMIT 50
),
fused AS (
    -- RRF fusion: 1/(60+rank) summed across both lists
    SELECT
        COALESCE(d.chunk_id, s.chunk_id)                AS chunk_id,
        COALESCE(1.0 / (60 + d.rank), 0.0)
            + COALESCE(1.0 / (60 + s.rank), 0.0)       AS rrf_score,
        d.rank                                           AS dense_rank,
        s.rank                                           AS sparse_rank,
        d.cosine_score,
        s.bm25_score
    FROM dense d
    FULL OUTER JOIN sparse s USING (chunk_id)
)
SELECT
    c.chunk_id,
    c.domain,
    c.content,
    s.source_path  AS source,
    f.rrf_score,
    f.dense_rank,
    f.sparse_rank,
    f.cosine_score,
    f.bm25_score
FROM fused f
JOIN chunks  c ON c.chunk_id = f.chunk_id
JOIN sources s ON s.source_id = c.source_id
ORDER BY f.rrf_score DESC
LIMIT $4;
```

**Why `ts_rank_cd` instead of `ts_rank`:** `ts_rank_cd` accounts for document
length (the `_cd` suffix means "cover density") which produces more consistent
BM25-like scores across chunks of varying length. For a sliding-window chunker
with fixed chunk sizes this matters less, but it is the safer default.

**Converting the query string to tsquery:** The Python layer needs to convert
the raw user query to a Postgres `tsquery` expression before passing it as `$3`:

```python
def query_to_tsquery(query: str) -> str:
    """
    Convert a natural-language query to a Postgres tsquery expression.
    Joins terms with & (AND) so all terms must appear, then falls back
    to | (OR) if AND returns no results.
    """
    # Strip punctuation, lowercase, split on whitespace
    import re
    terms = re.sub(r'[^\w\s]', ' ', query.lower()).split()
    # Filter stopwords Postgres would ignore anyway
    stopwords = {'the', 'a', 'an', 'in', 'on', 'at', 'to', 'for', 'of', 'and', 'or'}
    terms = [t for t in terms if t not in stopwords and len(t) > 1]
    if not terms:
        return ""
    return " & ".join(terms)
```

---

## New Retrieval File: `retrieve_pgvector.py`

This replaces `retrieve_sparse.py` and `retrieve_hybrid.py` with a single
clean file. The `reranker.py` and `api.py` are unchanged.

```python
# src/dev_rag/retrieve_pgvector.py

import asyncio
import logging
import re
from dataclasses import dataclass

import asyncpg

from .settings import settings

log = logging.getLogger(__name__)


@dataclass
class HybridResult:
    """
    Identical field names to the ChromaDB HybridResult in retrieve_hybrid.py
    so the reranker and API layer need no changes.
    """
    chunk_id: str
    domain: str
    content: str
    source: str
    rrf_score: float
    dense_rank: int | None
    sparse_rank: int | None
    dense_score: float | None
    bm25_score: float | None


HYBRID_SQL = """
WITH dense AS (
    SELECT chunk_id,
           ROW_NUMBER() OVER (ORDER BY embedding <=> $1) AS rank,
           1 - (embedding <=> $1)                        AS cosine_score
    FROM chunks
    WHERE domain = $2 AND status = 'active'
    ORDER BY embedding <=> $1
    LIMIT 50
),
sparse AS (
    SELECT chunk_id,
           ROW_NUMBER() OVER (ORDER BY ts_rank_cd(tsv, query) DESC) AS rank,
           ts_rank_cd(tsv, query)                                    AS bm25_score
    FROM chunks, to_tsquery('english', $3) query
    WHERE tsv @@ query AND domain = $2 AND status = 'active'
    ORDER BY ts_rank_cd(tsv, query) DESC
    LIMIT 50
),
fused AS (
    SELECT COALESCE(d.chunk_id, s.chunk_id)           AS chunk_id,
           COALESCE(1.0/(60+d.rank), 0.0)
               + COALESCE(1.0/(60+s.rank), 0.0)       AS rrf_score,
           d.rank      AS dense_rank,
           s.rank      AS sparse_rank,
           d.cosine_score,
           s.bm25_score
    FROM dense d FULL OUTER JOIN sparse s USING (chunk_id)
)
SELECT c.chunk_id, c.domain, c.content,
       s.source_path AS source,
       f.rrf_score, f.dense_rank, f.sparse_rank,
       f.cosine_score, f.bm25_score
FROM fused f
JOIN chunks  c ON c.chunk_id = f.chunk_id
JOIN sources s ON s.source_id = c.source_id
ORDER BY f.rrf_score DESC
LIMIT $4;
"""


def _query_to_tsquery(query: str) -> str:
    terms = re.sub(r'[^\w\s]', ' ', query.lower()).split()
    stopwords = {'the', 'a', 'an', 'in', 'on', 'at', 'to', 'for', 'of', 'and', 'or'}
    terms = [t for t in terms if t not in stopwords and len(t) > 1]
    return " & ".join(terms) if terms else ""


async def hybrid_search(
    query: str,
    domain: str,
    query_embedding: list[float],   # from BGE-M3 — same as before
    pool: asyncpg.Pool,
    n_results: int = 50,            # candidates for reranker; reranker trims to 10
) -> list[HybridResult]:
    """
    Run hybrid search (dense ANN + BM25) against pgvector in a single SQL query.

    Args:
        query:           Natural-language search query (used for BM25)
        domain:          Domain to search within (devops | python | ai)
        query_embedding: BGE-M3 embedding of the query (used for ANN)
        pool:            asyncpg connection pool (initialised at startup)
        n_results:       Number of results to return after RRF fusion

    Returns:
        List of HybridResult ordered by descending RRF score
    """
    tsquery = _query_to_tsquery(query)

    # If the query produces no valid tsquery terms, run dense-only
    if not tsquery:
        log.info("Empty tsquery for '%s' — running dense-only search", query)
        return await _dense_only_search(query_embedding, domain, pool, n_results)

    try:
        rows = await pool.fetch(
            HYBRID_SQL,
            query_embedding,   # $1: vector
            domain,            # $2: text
            tsquery,           # $3: tsquery string
            n_results,         # $4: limit
        )
    except asyncpg.exceptions.InvalidTextRepresentationError:
        # tsquery syntax error — fall back to dense-only
        log.warning("tsquery parse error for '%s' — falling back to dense-only", query)
        return await _dense_only_search(query_embedding, domain, pool, n_results)

    return [
        HybridResult(
            chunk_id=row["chunk_id"],
            domain=row["domain"],
            content=row["content"],
            source=row["source"],
            rrf_score=float(row["rrf_score"]),
            dense_rank=row["dense_rank"],
            sparse_rank=row["sparse_rank"],
            dense_score=float(row["cosine_score"]) if row["cosine_score"] else None,
            bm25_score=float(row["bm25_score"]) if row["bm25_score"] else None,
        )
        for row in rows
    ]


async def _dense_only_search(
    embedding: list[float],
    domain: str,
    pool: asyncpg.Pool,
    n_results: int,
) -> list[HybridResult]:
    """Fallback: ANN-only search when BM25 is unavailable."""
    rows = await pool.fetch(
        """
        SELECT c.chunk_id, c.domain, c.content, s.source_path AS source,
               1 - (c.embedding <=> $1) AS cosine_score
        FROM chunks c JOIN sources s ON s.source_id = c.source_id
        WHERE c.domain = $2 AND c.status = 'active'
        ORDER BY c.embedding <=> $1
        LIMIT $3
        """,
        embedding, domain, n_results,
    )
    return [
        HybridResult(
            chunk_id=row["chunk_id"],
            domain=row["domain"],
            content=row["content"],
            source=row["source"],
            rrf_score=float(row["cosine_score"]),
            dense_rank=i + 1,
            sparse_rank=None,
            dense_score=float(row["cosine_score"]),
            bm25_score=None,
        )
        for i, row in enumerate(rows)
    ]
```

---

## Docker Compose Changes

```yaml
# docker-compose.yml — replace ChromaDB service with Postgres + pgvector

services:
  postgres:
    image: pgvector/pgvector:pg16-0.8.2   # OBS-011: pinned — never use floating :pg16 tag
    restart: unless-stopped
    environment:
      POSTGRES_DB:       devrag
      POSTGRES_USER:     devrag
      POSTGRES_PASSWORD: "${POSTGRES_PASSWORD}"   # set in .env
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./migrations:/docker-entrypoint-initdb.d  # runs SQL on first start
    ports:
      - "127.0.0.1:5432:5432"   # localhost only
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U devrag"]
      interval: 10s
      timeout: 5s
      retries: 5

  dev-rag:
    build: .
    restart: unless-stopped
    environment:
      DATABASE_URL: "postgresql://devrag:${POSTGRES_PASSWORD}@postgres:5432/devrag"
      # Remove CHROMA_DB_PATH — no longer needed
    depends_on:
      postgres:
        condition: service_healthy

volumes:
  postgres_data:
```

---

## Settings Changes

```python
# src/dev_rag/settings.py — add DATABASE_URL, remove chroma settings

class Settings(BaseSettings):
    # Postgres / pgvector
    database_url: str = "postgresql://devrag:devrag@localhost:5432/devrag"

    # Remove these ChromaDB-specific settings:
    # chroma_db_path: str = "./chroma_db"
    # chroma_collection_prefix: str = "devrag"
```

---

## FastAPI Startup Changes

```python
# src/dev_rag/api.py — replace ChromaDB client with asyncpg pool

import asyncpg
from .retrieve_pgvector import hybrid_search as pgvector_hybrid_search

_pool: asyncpg.Pool | None = None


@app.on_event("startup")
async def startup():
    global _pool
    _pool = await asyncpg.create_pool(
        settings.database_url,
        min_size=2,
        max_size=10,
    )
    # Reranker load unchanged
    ...


@app.on_event("shutdown")
async def shutdown():
    if _pool:
        await _pool.close()


@app.post("/search")
async def search(request: SearchRequest) -> dict:
    # Embed the query — unchanged
    query_embedding = embedder.encode(request.query).tolist()

    # Stage 1: hybrid search — now uses pgvector
    candidates = await pgvector_hybrid_search(
        query=request.query,
        domain=request.domain,
        query_embedding=query_embedding,
        pool=_pool,
        n_results=settings.reranker_candidates,
    )

    # Stage 2: reranker — completely unchanged
    results = rerank_with_fallback(
        query=request.query,
        candidates=candidates,
        cross_encoder=_reranker,
        top_n=request.n_results,
    )
    ...
```

---

## Migration Steps

Run these in order. Each step is independently verifiable.

**Step 1 — Stand up Postgres**
```bash
docker compose up postgres -d
docker compose exec postgres psql -U devrag -c "SELECT extversion FROM pg_extension WHERE extname = 'vector';"
# Expected: 0.8.2 or later
```

**Step 2 — Run migrations**
```bash
# migrations/ are auto-run by docker-entrypoint-initdb.d on first start
# Verify schema:
docker compose exec postgres psql -U devrag -c "\d chunks"
```

**Step 3 — Run eval harness against ChromaDB (save baseline)**
```bash
uv run python eval/run_eval.py --domain devops
# Note the results JSON path printed at the end
```

**Step 4 — Implement `retrieve_pgvector.py`**
Run its unit tests — they use a test Postgres instance via `pytest-asyncio`
and `asyncpg`.

**Step 5 — Re-ingest one domain into Postgres**
```bash
docker compose exec dev-rag uv run python -m dev_rag.ingest \
  --source /data/docker-deep-dive.pdf \
  --domain devops \
  --backend pgvector
```

**Step 6 — Swap the backend in `api.py`** and run the full test suite.

**Step 7 — Run eval harness against pgvector**
```bash
uv run python eval/run_eval.py --domain devops \
  --compare eval/results/<chromadb-baseline>.json
```

**Step 8 — Compare, document the delta, and commit or revert.**

The delta goes into ADR-003 as the measured evidence for or against pgvector.
If Retrieval@3 is within ±2 points, the choice comes down to operational
preference. If pgvector is meaningfully better, update ADR-003 to reflect the
final decision.

---

## New Files Summary

```
dev-rag/
├── src/dev_rag/
│   ├── retrieve_pgvector.py     # NEW — replaces retrieve_sparse + retrieve_hybrid
│   └── api.py                   # MODIFIED — asyncpg pool, pgvector search call
├── migrations/
│   ├── 001_initial_schema.sql   # MODIFIED — add pgvector schema
│   └── 003_pgvector.sql         # NEW — chunks + sources tables, HNSW index
├── tests/
│   └── test_pgvector_search.py  # NEW — tests using test Postgres instance
└── docker-compose.yml           # MODIFIED — Postgres replaces ChromaDB service
```

Files **removed** after successful migration:
- `src/dev_rag/retrieve_sparse.py`
- `src/dev_rag/retrieve_hybrid.py`
- `migrations/002_add_fts5.sql`
- `chroma_db/` directory

---

## What the Eval Harness Comparison Will Show

The `--compare` delta report will answer three questions:

1. **Does pgvector retrieval quality match ChromaDB?** Retrieval@3 within ±2
   points means the migration is quality-neutral and the operational benefits
   of pgvector are free.

2. **Does unified hybrid search improve on the two-database approach?**
   The pgvector hybrid SQL is tighter than the Python RRF across ChromaDB +
   SQLite FTS5. It should be equal or better, not worse.

3. **Is there a latency difference?** Postgres adds a network hop that
   in-process ChromaDB doesn't have. For personal-scale use this should be
   negligible (sub-5ms on localhost), but worth confirming.

The delta report will include all seven metrics. Put the numbers in ADR-003
and the migration is fully documented.

---

*Add this document to `planning/` alongside `hybrid-search-spec.md`,
`reranker-spec.md`, `headroom-integration-spec.md`, and
`rag-document-update-strategy.md`.*
