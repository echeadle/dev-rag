# Current Context — dev-rag
_Last updated: 2026-07-05_

## Active Files
src/dev_rag/{retrieve,retrieve_sparse,retrieve_hybrid,api}.py,
migrations/003_fts_update_trigger.sql, docs/RUNBOOK.md, docs/TODO.md

## Current Step
PHASE 2 (hybrid search) COMPLETE on feat/phase2-hybrid-search (8 commits,
NOT pushed — Ed reviews, runs, merges). Suite 106 passed.
- /search LIVE in dense|sparse|hybrid with canonical relevance_score
  (per-mode scales: RRF ~0.03 / cosine 0-1 / BM25 unbounded — api.py docstring)
- /health real parity counts, drift -> degraded (OBS-009 closed)
- FBL-001 closed (003 migration: FTS UPDATE trigger, tested)
- OBS-006 closed: ablation on live corpus, porter ascii KEPT; hybrid ≥ dense
  on all 6 queries, one clear sparse win (compose secrets). Recorded in
  planning/hybrid-search-spec.md.
- Design deviation (documented in retrieve_sparse.py): BM25 queries are
  sanitised + OR-joined — FTS5's implicit AND zeroed recall on sentences.
- e2e tests hit the real endpoint (temp stores via real migrations);
  tests/test_api.py isolates via autouse fixture (never real BGE-M3).
- Runbook §5: uvicorn + curl verified live (first query ~9s model load,
  then ~105ms hybrid / ~4ms sparse).

## Next Action
1. Ed: review feat/phase2-hybrid-search, try runbook §5 (uvicorn + curl),
   merge to main.
2. Then pick: MCP wiring+smoke (makes Claude Code sessions query the corpus —
   small, high payoff), Phase 3 reranker, or ingest second book
   (Docker Compose PDF — also fills the "bind mount permissions" corpus gap
   the ablation exposed).

## Done When (Phase 2) — ALL MET
- [x] /search real results in all 3 modes with relevance_score
- [x] e2e test on real endpoint; 22 mcp fixture tests untouched & green
- [x] FBL-001 (003 migration) + OBS-009 closed
- [x] OBS-006 ablation run + recorded; suite green (106); runbook updated

## Blockers
None. Parked: eval baseline P4 (FBL-002/FBL-005 scorer fixes + OBS-003),
structure+enrich (FBL-004 cost gate), reranker P3, GraphRAG P8, headroom-ai.

## Phase
Phase 2 COMPLETE, pending Ed's review + merge. MCP server now has a real
API behind it but is not yet smoke-tested.
