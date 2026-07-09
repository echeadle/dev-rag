# Current Context — dev-rag
_Last updated: 2026-07-09_

## Active File
src/dev_rag/api.py (force_rerank), mcp/mcp_server.py (_handle_search_all),
src/dev_rag/settings.py (force_rerank_candidates)

## Current Step
Phase 5b (unified search_all ranking) on branch
`feat/phase5b-unified-search-all`, NOT yet merged. `search_all` now
genuinely ranks across domains (reranker score is domain-agnostic; RRF is
not) instead of concatenating per-domain blocks. Scoped to `search_all`
only via a new `force_rerank` request field — ADR-012's single-domain
default (reranker OFF) is untouched, verified live (0.16s, unreranked).
**Real-world finding, corrects the original plan:** tried offloading
rerank to a thread so concurrent per-domain fan-out calls would overlap —
measured WORSE (CPU-bound, not GIL-bound; reverted). `search_all`'s true
cost is ~20s × populated domain count (~40-50s today at 2 domains), not a
flat ~20s. Timeout and tool description updated to say so honestly.

## Next Action
Ed reviews via docs/BRANCH-REVIEW-CHECKLIST.md ("Phase 5b — Unified
search_all Ranking" section, 9 steps) and merges.

## Done When
- [x] force_rerank added, scoped to search_all only, ADR-012 unaffected
- [x] search_all discovers populated domains via /health, sorts by score
- [x] Latency measured live and corrected honestly (not just assumed)
- [x] 147 tests green (4 new + 3 updated)
- [x] Branch Review Checklist section written
- [ ] Ed reviews + merges

## Blockers
None. Parked: structure+enrich (deferred), GraphRAG (no spec, P8),
pgvector (P7), headroom-ai, remaining Python books (titles unconfirmed).

## Phase
Corpus: 5 books / 2027 chunks / 2 domains populated (devops, python).
Phase 5b done pending Ed's merge — no active phase after that.
