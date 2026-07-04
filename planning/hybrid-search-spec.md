# dev-rag Hybrid Search — Implementation Spec

**Version:** 1.0  
**Date:** June 2026  
**Status:** Ready to implement — next step after MCP server wiring

---

## Why Hybrid Search

Pure dense vector search is no longer the professional baseline for RAG in 2026.
It is excellent at semantic similarity but has a systematic weakness: exact token
matching. DevOps queries frequently contain tokens that must be matched precisely:

- Flag names: `--network=host`, `--cap-drop=ALL`, `--read-only`
- Directive names: `COPY --chown`, `HEALTHCHECK`, `ARG`, `BuildKit`
- Error strings: `permission denied`, `connection refused`, `no such file`
- Version-specific syntax: `docker compose` vs `docker-compose`
- Tool names: `containerd`, `runc`, `cgroups`, `namespaces`

BGE-M3 will embed `--network=host` into a vector space where it sits near
"host networking mode" — good for semantic queries. But if the chunk text
literally contains `--network=host` and the query also contains `--network=host`,
BM25 will match it with perfect precision that the embedding cannot improve on.

Hybrid search captures both signals. RRF (Reciprocal Rank Fusion) combines the
two ranked lists without requiring score normalisation, which matters because
cosine similarity scores and BM25 scores live on completely different scales.

---

## Architecture

### Current (dense only)

```
Query
  │
  ▼
BGE-M3 embed
  │
  ▼
ChromaDB ANN search
  │
  ▼
Top-k chunks → FastAPI → MCP → Claude Code
```

### After this spec (hybrid)

```
Query
  ├──► BGE-M3 embed ──► ChromaDB ANN search ──► dense_results (ranked list)
  │
  └──► SQLite FTS5 BM25 ──────────────────────► sparse_results (ranked list)
                │
                ▼
          RRF fusion (per domain)
                │
                ▼
          fused_results (single re-ranked list)
                │
                ▼
          FastAPI → MCP → Claude Code
```

### Migration path (future)

When pgvector replaces ChromaDB, BM25 moves from SQLite FTS5 to Postgres
`tsvector` + `GIN` index. The RRF fusion logic stays identical — only the
data source changes. This is why the fusion layer is kept separate from both
retrieval backends.

---

## Component Design

### 1. SQLite FTS5 Index

FTS5 is SQLite's full-text search engine. It is already available — SQLite is
already in the stack for metadata. The FTS5 virtual table indexes chunk text
and supports BM25 scoring natively via the `bm25()` function.

**Schema additions to `schema.sql`:**

```sql
-- Existing chunks metadata table (already present)
-- chunk_id TEXT PRIMARY KEY
-- source_id TEXT
-- domain TEXT
-- source TEXT
-- page_number INTEGER
-- content_hash TEXT
-- version TEXT
-- status TEXT
-- ingest_timestamp TEXT

-- New: FTS5 virtual table for BM25 search
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    chunk_id UNINDEXED,   -- carry-through for joining back to chunks table
    domain UNINDEXED,     -- carry-through for domain filtering
    content,              -- the text that gets indexed and searched
    tokenize = 'porter ascii'  -- porter stemmer: "running" matches "run"
);

-- Trigger: keep FTS index in sync with chunk inserts
CREATE TRIGGER IF NOT EXISTS chunks_fts_insert
AFTER INSERT ON chunks BEGIN
    INSERT INTO chunks_fts(chunk_id, domain, content)
    VALUES (new.chunk_id, new.domain, new.content);
END;

-- Trigger: keep FTS index in sync with chunk deletes
CREATE TRIGGER IF NOT EXISTS chunks_fts_delete
AFTER DELETE ON chunks BEGIN
    DELETE FROM chunks_fts WHERE chunk_id = old.chunk_id;
END;
```

**Why `porter ascii` tokenizer:**  
Porter stemming reduces words to their root form so "configuring" matches
"configuration" and "configured". The `ascii` component handles the
technical-document character set cleanly. For a DevOps corpus this is
the right balance — aggressive enough to catch morphological variants,
conservative enough not to mangle flag names and identifiers.

**⚠️ OBS-006 (Opus review): Exact flag-token caveat**  
Porter stemming and the default punctuation split mean that `--network=host`
is indexed as `network` and `host` (the `--` and `=` are stripped). The
"exact flag matching" claim in the hybrid search rationale is therefore
weaker than stated — flag *words* are matched, not flag *syntax*. Verify
the planned ablation queries (`--network=host`, `COPY --chown`, `BuildKit`)
against real ingested content before relying on BM25 for exact-syntax recall.
If flag-syntax precision is required, evaluate `unicode61` with custom
`tokenchars` or an unstemmed secondary column as an alternative tokenizer.

---

### 2. BM25 retrieval function

```python
# src/dev_rag/retrieve_sparse.py

import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass
class SparseResult:
    chunk_id: str
    domain: str
    content: str
    bm25_score: float   # negative in SQLite (lower = better match); we negate


def bm25_search(
    query: str,
    domain: str,
    db_path: Path,
    n_results: int = 20,   # fetch more than needed; RRF will trim
) -> list[SparseResult]:
    """
    Run BM25 full-text search against the SQLite FTS5 index.

    SQLite FTS5 bm25() returns negative scores (more negative = better match).
    We negate them so higher scores are better, consistent with dense search.

    Args:
        query:     Natural-language or keyword query string
        domain:    Restrict search to this domain (devops | travel)
        db_path:   Path to the SQLite database file
        n_results: Number of results to return

    Returns:
        List of SparseResult ordered by descending BM25 score (best first)
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    try:
        rows = conn.execute(
            """
            SELECT
                chunk_id,
                domain,
                content,
                -bm25(chunks_fts) AS score   -- negate: higher is better
            FROM chunks_fts
            WHERE chunks_fts MATCH ?
              AND domain = ?
            ORDER BY score DESC
            LIMIT ?
            """,
            (query, domain, n_results),
        ).fetchall()
    except sqlite3.OperationalError as e:
        # FTS5 syntax error from user query (e.g. unbalanced quotes)
        # Fall back to a sanitised query rather than crashing
        sanitised = _sanitise_fts_query(query)
        rows = conn.execute(
            """
            SELECT chunk_id, domain, content, -bm25(chunks_fts) AS score
            FROM chunks_fts
            WHERE chunks_fts MATCH ?
              AND domain = ?
            ORDER BY score DESC
            LIMIT ?
            """,
            (sanitised, domain, n_results),
        ).fetchall()
    finally:
        conn.close()

    return [
        SparseResult(
            chunk_id=row["chunk_id"],
            domain=row["domain"],
            content=row["content"],
            bm25_score=row["score"],
        )
        for row in rows
    ]


def _sanitise_fts_query(query: str) -> str:
    """
    Strip FTS5 special characters that cause syntax errors.
    Used as a fallback when the raw query fails to parse.
    """
    # Remove FTS5 operators and unbalanced quotes
    for char in ['"', "'", "(", ")", "*", "^", "OR", "AND", "NOT"]:
        query = query.replace(char, " ")
    return " ".join(query.split())   # collapse whitespace
```

---

### 3. RRF Fusion

Reciprocal Rank Fusion combines ranked lists without requiring score
normalisation. The formula for each document is:

```
RRF_score(doc) = Σ  1 / (k + rank_in_list_i)
```

where `k` is a constant (typically 60) that dampens the influence of
very-high-ranked results. Results are then sorted by descending RRF score.

The key insight is that only **rank** matters, not the raw score. This is
exactly why RRF works across BM25 and cosine similarity — those scores are
not comparable, but ranks always are.

```python
# src/dev_rag/retrieve_hybrid.py

from dataclasses import dataclass
from pathlib import Path

from .retrieve_sparse import bm25_search, SparseResult


RRF_K = 60   # standard constant; controls rank-score dampening


@dataclass
class HybridResult:
    chunk_id: str
    domain: str
    content: str
    source: str
    rrf_score: float
    dense_rank: int | None    # rank in dense results (None if not present)
    sparse_rank: int | None   # rank in BM25 results (None if not present)
    dense_score: float | None
    bm25_score: float | None


def reciprocal_rank_fusion(
    dense_results: list[dict],    # from ChromaDB: [{"chunk_id", "content", "source", "score"}, ...]
    sparse_results: list[SparseResult],
    k: int = RRF_K,
) -> list[HybridResult]:
    """
    Fuse dense (vector) and sparse (BM25) ranked lists using RRF.

    Both lists are ranked independently. RRF assigns each document a score
    based on its position in each list, then sums across lists. Documents
    that rank well in both lists score highest.

    Documents that appear in only one list still get an RRF score from
    that list alone — they are not discarded. This is important: BM25 may
    surface an exact-token match that the dense search missed entirely.

    Args:
        dense_results:  Ranked list from ChromaDB (index 0 = best)
        sparse_results: Ranked list from FTS5 BM25 (index 0 = best)
        k:              RRF dampening constant (default 60)

    Returns:
        Fused list sorted by descending RRF score
    """
    scores: dict[str, dict] = {}

    # Process dense results
    for rank, result in enumerate(dense_results, start=1):
        chunk_id = result["chunk_id"]
        scores[chunk_id] = {
            "chunk_id":    chunk_id,
            "domain":      result.get("domain", ""),
            "content":     result.get("content", ""),
            "source":      result.get("source", ""),
            "rrf_score":   1.0 / (k + rank),
            "dense_rank":  rank,
            "sparse_rank": None,
            "dense_score": result.get("score"),
            "bm25_score":  None,
        }

    # Process sparse results — add to existing or create new entry
    for rank, result in enumerate(sparse_results, start=1):
        chunk_id = result.chunk_id
        rrf_contribution = 1.0 / (k + rank)

        if chunk_id in scores:
            # Document found in both lists — sum the RRF contributions
            scores[chunk_id]["rrf_score"]   += rrf_contribution
            scores[chunk_id]["sparse_rank"]  = rank
            scores[chunk_id]["bm25_score"]   = result.bm25_score
        else:
            # Document only in BM25 results — still included
            scores[chunk_id] = {
                "chunk_id":    chunk_id,
                "domain":      result.domain,
                "content":     result.content,
                "source":      "",   # will be enriched from SQLite metadata
                "rrf_score":   rrf_contribution,
                "dense_rank":  None,
                "sparse_rank": rank,
                "dense_score": None,
                "bm25_score":  result.bm25_score,
            }

    # Sort by descending RRF score
    fused = sorted(scores.values(), key=lambda x: x["rrf_score"], reverse=True)
    return [HybridResult(**r) for r in fused]


async def hybrid_search(
    query: str,
    domain: str,
    chroma_collection,      # ChromaDB collection object
    db_path: Path,
    n_results: int = 10,
    dense_candidates: int = 20,   # fetch more from each source before fusion
    sparse_candidates: int = 20,
) -> list[HybridResult]:
    """
    Run hybrid search: dense + BM25, fused with RRF.

    Fetches more candidates than needed from each retrieval backend
    (dense_candidates, sparse_candidates) so that RRF has enough
    material to work with. Returns the top n_results after fusion.

    Args:
        query:             Search query
        domain:            Domain to search within (devops | travel)
        chroma_collection: ChromaDB collection for this domain
        db_path:           SQLite database path
        n_results:         Final number of results to return after fusion

    Returns:
        Fused and ranked list of HybridResult, length <= n_results
    """
    # --- Dense retrieval ---
    chroma_response = chroma_collection.query(
        query_texts=[query],
        n_results=dense_candidates,
        where={"domain": domain},
        include=["documents", "metadatas", "distances"],
    )

    dense_results = []
    if chroma_response["ids"] and chroma_response["ids"][0]:
        for i, chunk_id in enumerate(chroma_response["ids"][0]):
            meta = chroma_response["metadatas"][0][i]
            dense_results.append({
                "chunk_id": chunk_id,
                "content":  chroma_response["documents"][0][i],
                "source":   meta.get("source", ""),
                "domain":   meta.get("domain", domain),
                "score":    1 - chroma_response["distances"][0][i],  # cosine: distance → similarity
            })

    # --- Sparse (BM25) retrieval ---
    sparse_results = bm25_search(
        query=query,
        domain=domain,
        db_path=db_path,
        n_results=sparse_candidates,
    )

    # --- RRF fusion ---
    fused = reciprocal_rank_fusion(dense_results, sparse_results)

    return fused[:n_results]
```

---

### 4. Ingest changes — populate FTS5 at ingest time

The FTS5 trigger handles inserts automatically, but the ingest pipeline
needs to write to the `chunks` table (with `content` column) so the
trigger fires.

**Addition to `ingest.py`:**

```python
def store_chunk_metadata(
    chunk: PageChunk,
    domain: str,
    source_id: str,
    db_path: Path,
) -> None:
    """
    Write chunk to the SQLite chunks table.
    The FTS5 trigger (chunks_fts_insert) fires automatically,
    populating chunks_fts without any additional code here.
    """
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        INSERT OR REPLACE INTO chunks
            (chunk_id, source_id, domain, source, page_number,
             content, content_hash, version, status, ingest_timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', datetime('now'))
        """,
        (
            chunk.chunk_id,
            source_id,
            domain,
            chunk.book,
            chunk.page,
            chunk.text,          # content column triggers FTS5 insert
            chunk.content_hash,
            chunk.version or "",
        ),
    )
    conn.commit()
    conn.close()
```

---

### 5. FastAPI route changes

The `/search` endpoint gains a `search_mode` parameter:

```python
# src/dev_rag/api.py  (additions)

from enum import Enum
from .retrieve_hybrid import hybrid_search

class SearchMode(str, Enum):
    dense  = "dense"    # current behaviour — vector only
    sparse = "sparse"   # BM25 only (useful for debugging)
    hybrid = "hybrid"   # dense + BM25 + RRF (new default)


class SearchRequest(BaseModel):
    query: str
    domain: str
    n_results: int = 5
    search_mode: SearchMode = SearchMode.hybrid   # hybrid is new default


@app.post("/search")
async def search(request: SearchRequest) -> dict:
    collection = get_collection(request.domain)   # existing helper

    if request.search_mode == SearchMode.hybrid:
        results = await hybrid_search(
            query=request.query,
            domain=request.domain,
            chroma_collection=collection,
            db_path=settings.sqlite_db_path,
            n_results=request.n_results,
        )
        return {
            "results": [
                {
                    "chunk_id":    r.chunk_id,
                    "source":      r.source,
                    "domain":      r.domain,
                    "content":     r.content,
                    "rrf_score":   r.rrf_score,
                    "dense_rank":  r.dense_rank,
                    "sparse_rank": r.sparse_rank,
                }
                for r in results
            ],
            "search_mode": "hybrid",
            "query": request.query,
        }

    elif request.search_mode == SearchMode.dense:
        # Existing dense-only path — unchanged
        ...

    elif request.search_mode == SearchMode.sparse:
        # BM25 only — useful for debugging and ablation
        from .retrieve_sparse import bm25_search
        results = bm25_search(
            query=request.query,
            domain=request.domain,
            db_path=settings.sqlite_db_path,
            n_results=request.n_results,
        )
        return {
            "results": [
                {
                    "chunk_id":  r.chunk_id,
                    "source":    "",
                    "domain":    r.domain,
                    "content":   r.content,
                    "bm25_score": r.bm25_score,
                }
                for r in results
            ],
            "search_mode": "sparse",
            "query": request.query,
        }
```

---

### 6. New tests

```python
# tests/test_hybrid_search.py

import pytest
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

from dev_rag.retrieve_sparse import bm25_search, _sanitise_fts_query
from dev_rag.retrieve_hybrid import reciprocal_rank_fusion, HybridResult


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def fts_db(tmp_path: Path) -> Path:
    """In-memory SQLite with FTS5 and a handful of test chunks."""
    db = tmp_path / "test.db"
    conn = sqlite3.connect(db)
    conn.executescript("""
        CREATE TABLE chunks (
            chunk_id TEXT PRIMARY KEY,
            domain   TEXT,
            content  TEXT,
            source   TEXT
        );

        CREATE VIRTUAL TABLE chunks_fts USING fts5(
            chunk_id UNINDEXED,
            domain   UNINDEXED,
            content,
            tokenize = 'porter ascii'
        );

        CREATE TRIGGER chunks_fts_insert AFTER INSERT ON chunks BEGIN
            INSERT INTO chunks_fts(chunk_id, domain, content)
            VALUES (new.chunk_id, new.domain, new.content);
        END;

        INSERT INTO chunks VALUES
            ('c1', 'devops', 'Docker secrets store sensitive data securely', 'docker-deep-dive.pdf'),
            ('c2', 'devops', 'Use --network=host to share the host network namespace', 'docker-deep-dive.pdf'),
            ('c3', 'devops', 'Running containers as root is a security risk', 'docker-security.pdf'),
            ('c4', 'devops', 'Bridge networks are the default Docker network mode', 'docker-deep-dive.pdf'),
            ('c5', 'travel', 'Heraklion airport has accessible drop-off zones', 'crete-guide.pdf');
    """)
    conn.commit()
    conn.close()
    return db


# ── BM25 tests ────────────────────────────────────────────────────────────────

def test_bm25_returns_results(fts_db):
    results = bm25_search("Docker secrets", domain="devops", db_path=fts_db)
    assert len(results) > 0
    assert results[0].chunk_id == "c1"


def test_bm25_domain_filter(fts_db):
    """Travel query should not return devops results."""
    results = bm25_search("accessible", domain="travel", db_path=fts_db)
    assert all(r.domain == "travel" for r in results)


def test_bm25_exact_flag_match(fts_db):
    """Exact CLI flag should be retrievable by BM25."""
    results = bm25_search("--network=host", domain="devops", db_path=fts_db)
    assert any(r.chunk_id == "c2" for r in results)


def test_bm25_empty_query_fallback(fts_db):
    """Malformed FTS5 query should not raise — sanitiser kicks in."""
    results = bm25_search('"unbalanced', domain="devops", db_path=fts_db)
    # Should not raise; may return empty list
    assert isinstance(results, list)


def test_bm25_no_cross_domain_bleed(fts_db):
    """DevOps query should not return travel results."""
    results = bm25_search("Docker network", domain="devops", db_path=fts_db)
    assert all(r.domain == "devops" for r in results)


def test_sanitise_fts_query():
    assert '"' not in _sanitise_fts_query('"bad query"')
    assert "AND" not in _sanitise_fts_query("docker AND secrets")


# ── RRF fusion tests ──────────────────────────────────────────────────────────

def _make_dense(items: list[tuple[str, float]]) -> list[dict]:
    """Helper: build dense result list from (chunk_id, score) pairs."""
    return [
        {"chunk_id": cid, "content": f"content {cid}", "source": "test.pdf",
         "domain": "devops", "score": score}
        for cid, score in items
    ]


def _make_sparse(items: list[tuple[str, float]]) -> list:
    from dev_rag.retrieve_sparse import SparseResult
    return [
        SparseResult(chunk_id=cid, domain="devops",
                     content=f"content {cid}", bm25_score=score)
        for cid, score in items
    ]


def test_rrf_document_in_both_lists_ranks_highest():
    """A document appearing in both lists should outscore one appearing in only one."""
    dense  = _make_dense([("c1", 0.9), ("c2", 0.8), ("c3", 0.7)])
    sparse = _make_sparse([("c2", 5.0), ("c4", 4.0), ("c1", 3.0)])
    fused  = reciprocal_rank_fusion(dense, sparse)

    # c1 and c2 both appear in both lists — they should outscore c3 and c4
    fused_ids = [r.chunk_id for r in fused]
    assert fused_ids.index("c1") < fused_ids.index("c3")
    assert fused_ids.index("c2") < fused_ids.index("c4")


def test_rrf_bm25_only_result_included():
    """A document only in BM25 results should still appear in fused output."""
    dense  = _make_dense([("c1", 0.9), ("c2", 0.8)])
    sparse = _make_sparse([("c3", 9.0), ("c1", 5.0)])  # c3 not in dense
    fused  = reciprocal_rank_fusion(dense, sparse)

    assert any(r.chunk_id == "c3" for r in fused)


def test_rrf_scores_are_positive_and_descending():
    dense  = _make_dense([("c1", 0.9), ("c2", 0.7)])
    sparse = _make_sparse([("c2", 4.0), ("c1", 3.0)])
    fused  = reciprocal_rank_fusion(dense, sparse)

    assert all(r.rrf_score > 0 for r in fused)
    scores = [r.rrf_score for r in fused]
    assert scores == sorted(scores, reverse=True)


def test_rrf_rank_fields_populated():
    dense  = _make_dense([("c1", 0.9)])
    sparse = _make_sparse([("c1", 4.0)])
    fused  = reciprocal_rank_fusion(dense, sparse)

    c1 = next(r for r in fused if r.chunk_id == "c1")
    assert c1.dense_rank  == 1
    assert c1.sparse_rank == 1


def test_rrf_empty_sparse_returns_dense_order():
    dense  = _make_dense([("c1", 0.9), ("c2", 0.7)])
    fused  = reciprocal_rank_fusion(dense, [])
    assert [r.chunk_id for r in fused] == ["c1", "c2"]


def test_rrf_empty_dense_returns_sparse_order():
    sparse = _make_sparse([("c3", 5.0), ("c4", 3.0)])
    fused  = reciprocal_rank_fusion([], sparse)
    assert [r.chunk_id for r in fused] == ["c3", "c4"]
```

---

## New Files Summary

```
dev-rag/
├── src/dev_rag/
│   ├── retrieve_sparse.py    # NEW — BM25 via SQLite FTS5
│   ├── retrieve_hybrid.py    # NEW — RRF fusion + hybrid_search()
│   └── api.py                # MODIFIED — search_mode param, hybrid route
├── migrations/
│   └── 002_add_fts5.sql      # NEW — FTS5 table + triggers
└── tests/
    └── test_hybrid_search.py # NEW — 11 tests
```

---

## Settings additions

```python
# src/dev_rag/settings.py  (additions)

class Settings(BaseSettings):
    # ... existing fields ...

    # Hybrid search
    search_mode: str = "hybrid"          # dense | sparse | hybrid
    rrf_k: int = 60                      # RRF dampening constant
    dense_candidates: int = 20           # candidates fetched from ChromaDB before fusion
    sparse_candidates: int = 20          # candidates fetched from FTS5 before fusion
    fts_tokenizer: str = "porter ascii"  # FTS5 tokenizer
```

---

## Implementation Order

Do these steps in order — each is independently testable before moving on:

1. **Run `002_add_fts5.sql`** — add FTS5 table and triggers to SQLite
2. **Re-ingest one document** — verify FTS5 trigger populates `chunks_fts`
3. **Implement `retrieve_sparse.py`** — run its tests in isolation
4. **Implement `retrieve_hybrid.py`** — run RRF unit tests (no live server needed)
5. **Modify `api.py`** — wire `hybrid_search()` into the `/search` route
6. **Run the full test suite** — all 120 existing + 11 new should pass
7. **Run the eval harness** — establish hybrid baseline score
8. **Compare** `search_mode=dense` vs `search_mode=hybrid` using `--compare`

Step 7 and 8 are where the work pays off — you'll see exactly how much
Retrieval@3 and MRR improve from adding BM25. That number goes in the ADR.

---

## Ablation queries to run manually after implementation

These queries are specifically chosen to stress-test BM25's contribution.
Run them with `search_mode=dense` and `search_mode=hybrid` and compare:

```
--network=host flag behaviour
COPY --chown directive in Dockerfiles
docker compose secrets: syntax
BuildKit secret mount syntax
permission denied when bind mounting
containerd vs dockerd architecture
```

If hybrid consistently surfaces more precise results on these, BM25 is earning
its place. If there's no difference, the corpus may not contain enough
exact-token content to make BM25 worthwhile — which is itself a useful signal.

---

## Migration note for pgvector

When ChromaDB is replaced by pgvector, the BM25 layer moves to:

```sql
-- Add tsvector column to chunks table
ALTER TABLE chunks ADD COLUMN tsv tsvector
    GENERATED ALWAYS AS (to_tsvector('english', content)) STORED;

CREATE INDEX chunks_tsv_idx ON chunks USING GIN(tsv);

-- Hybrid query (dense + lexical, fused in SQL with RRF)
WITH dense AS (
    SELECT chunk_id, ROW_NUMBER() OVER (ORDER BY embedding <=> $1) AS rank
    FROM chunks WHERE domain = $2
    ORDER BY embedding <=> $1 LIMIT 20
),
sparse AS (
    SELECT chunk_id, ROW_NUMBER() OVER (ORDER BY ts_rank(tsv, q) DESC) AS rank
    FROM chunks, to_tsquery('english', $3) q
    WHERE tsv @@ q AND domain = $2
    ORDER BY ts_rank(tsv, q) DESC LIMIT 20
)
SELECT
    COALESCE(d.chunk_id, s.chunk_id) AS chunk_id,
    (COALESCE(1.0/(60+d.rank), 0) + COALESCE(1.0/(60+s.rank), 0)) AS rrf_score
FROM dense d FULL OUTER JOIN sparse s USING (chunk_id)
ORDER BY rrf_score DESC
LIMIT $4;
```

The Python RRF logic in `retrieve_hybrid.py` is replaced by this SQL — but
the `HybridResult` dataclass and the FastAPI route stay identical.

---

*Add this document to `planning/` alongside `rag-document-update-strategy.md`
and `PRD-docker.md`.*
