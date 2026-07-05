"""
dev-rag sparse retrieval — BM25 via SQLite FTS5.

Adapted from planning/hybrid-search-spec.md §2 per the Phase 2 plan:
- JOINs chunks -> sources so results carry the source filename (the
  spec assumed `source` lived on the chunks table; it lives on sources
  per migrations/001).
- Filters chunks.status = 'active' (belt-and-braces: migration 003's
  UPDATE trigger already evicts non-active rows from the FTS index).

SQLite's bm25() returns negative scores (more negative = better); they
are negated so higher-is-better, consistent with dense search.

OBS-006 caveat: the `porter ascii` tokenizer strips punctuation, so
`--network=host` matches as the words `network` + `host`, not the exact
flag syntax. The ablation queries (plan stage 5) measure whether that
is good enough.
"""
import logging
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .settings import settings

log = logging.getLogger(__name__)

_SQL = """
    SELECT
        f.chunk_id,
        f.domain,
        f.content,
        s.source_path AS source,
        -bm25(chunks_fts) AS score      -- negate: higher is better
    FROM chunks_fts f
    JOIN chunks  c ON c.chunk_id  = f.chunk_id
    JOIN sources s ON s.source_id = c.source_id
    WHERE chunks_fts MATCH ?
      AND f.domain = ?
      AND c.status = 'active'
    ORDER BY score DESC
    LIMIT ?
"""


@dataclass
class SparseResult:
    chunk_id: str
    domain: str
    content: str
    source: str          # filename, joined from sources
    bm25_score: float


def bm25_search(
    query: str,
    domain: str,
    db_path: Path | None = None,
    n_results: int | None = None,
) -> list[SparseResult]:
    """
    BM25 full-text search, best match first.

    The query is always reduced to sanitised terms joined with OR.
    Two reasons (deviation from the spec, found at the stage gate):
    - FTS5 raw syntax chokes on technical queries (`--network=host`).
    - FTS5's implicit AND between words means natural-language questions
      ("what is the production-safe way to ...") almost never match a
      single chunk verbatim — sparse recall collapses to zero. OR keeps
      recall high; bm25() still ranks chunks matching more (and rarer)
      terms first, and RRF fusion handles the rest.
    A query that sanitises to nothing returns [].
    """
    db_path = db_path or settings.sqlite_db_path
    n_results = n_results or settings.sparse_candidates

    terms = _sanitise_fts_query(query).split()
    if not terms:
        return []
    match_expr = " OR ".join(terms)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        try:
            rows = conn.execute(_SQL, (match_expr, domain, n_results)).fetchall()
        except sqlite3.OperationalError:
            log.warning("FTS query unusable after sanitising: %r", query)
            return []
    finally:
        conn.close()

    return [
        SparseResult(
            chunk_id=row["chunk_id"],
            domain=row["domain"],
            content=row["content"],
            source=row["source"],
            bm25_score=row["score"],
        )
        for row in rows
    ]


def _sanitise_fts_query(query: str) -> str:
    """
    Reduce a query to plain search terms FTS5 can always parse:
    strip punctuation/operators, drop bare AND/OR/NOT (whole words only,
    so 'android' survives), collapse whitespace.
    """
    query = re.sub(r"[^\w\s]", " ", query)
    query = re.sub(r"\b(AND|OR|NOT)\b", " ", query)
    return " ".join(query.split())
