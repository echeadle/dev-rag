# Current Context — dev-rag
_Last updated: 2026-07-06_

## Active Files
src/dev_rag/{reranker,api,settings}.py, tests/test_reranker.py,
tests/{test_api,test_api_e2e}.py, mcp/tests/test_mcp_e2e.py, docs/RUNBOOK.md

## Current Step
PHASE 3 (reranker) MERGED to main + pushed (827b36d, 2026-07-06) after
Ed's live off/on review. Suite 127 passed on merged main (+12 unit +2 e2e).
docs/BRANCH-REVIEW-CHECKLIST.md added during review (reusable).
- reranker.py real: RankedResult, rerank(), rerank_with_fallback() (OBS-002:
  every path returns RankedResult; reranker_score=None marks fallback).
- api.py: lifespan eager-load when enabled (OBS-010); hybrid = two-stage
  (RRF pool -> cross-encoder -> caller's n_results; backends widened to
  fill the pool); SearchResult grew reranker_score debug field.
- Verified live on 583-chunk corpus: reranker re-orders candidates, Compose
  book reaches top-3 on Compose query, sweeps bind-mount query.
- DECISION (Ed, 2026-07-06): ships DEFAULT OFF. Measured CPU latency
  ~1.5-2 s/pair: ~15 s/query @10 candidates, ~112 s @50, vs ~0.15 s
  RRF-only; informal quality delta modest. RERANKER_ENABLED=true per-run
  (NO DEV_RAG_ prefix — spec's env name wrong; runbook §5b documents).
- Suite guards: test_api.py + mcp e2e pin reranker off; e2e reranker tests
  inject FakeCrossEncoder. Real models never load in tests (18 s suite).
- Docs updated: RUNBOOK §5b, TODO Phase 3, IMPLEMENTATION-ORDER, CLAUDE.md
  (stub list, test count 127, current state).

## Next Action
Phase 4 eval harness (FBL-002/FBL-005 scorer fixes + OBS-003
expected_source) — it decides the reranker default with real numbers.
Alt: ingest Ansible for DevOps (remember book-specific --query).

## Done When (Phase 3) — ALL MET
- [x] reranker.py real, wired, OBS-002 fallback proven (unit + e2e + live)
- [x] e2e tests hit the real endpoint (CLAUDE.md stub rule)
- [x] Before/after recorded (TODO.md); latency measured, default decided

## Blockers
None. Parked: smaller reranker model (bge-reranker-base) until Phase 4 eval;
structure+enrich (FBL-004 cost gate), GraphRAG P8, headroom-ai.

## Phase
Phase 3 COMPLETE + merged. Phase 4 (eval) is next.
