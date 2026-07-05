# Current Context — dev-rag
_Last updated: 2026-07-05_

## Active Files
docs/plans/dev-rag-phase2-plan.md (NEW — reviewed spec, reconciled, ready),
planning/hybrid-search-spec.md, docs/RUNBOOK.md, docs/TODO.md

## Current Step
Phase 1a MERGED to main (Ed ran verify himself, then merged; 18 commits).
Corpus live: Docker Deep Dive, 311 chunks, parity 311/311/311, verified.
docs/RUNBOOK.md added — how to run everything; update it every phase.

Phase 2 (hybrid search) PLANNED: docs/plans/dev-rag-phase2-plan.md.
Key reconciliations vs the spec (spec predates 1a — plan OVERRIDES it):
OBS-001 relevance_score mapping per mode; dense must embed queries itself
(query_embeddings, collections have no bound embed fn); bm25 JOINs sources
for filename + filters active; fixtures via real migrations.
Folds in FBL-001 (003 migration), OBS-006 ablation, OBS-009 /health counts,
and the e2e-test-on-real-endpoint rule. NEW: FBL-005 (eval negative-precision
threshold breaks under RRF scale) — parked to Phase 4, in TODO.

## Next Action
Start Phase 2 on branch feat/phase2-hybrid-search using the kickoff prompt at
the bottom of docs/plans/dev-rag-phase2-plan.md. Stage 0 = migration 003
(FBL-001 FTS UPDATE trigger). Gated: one commit per stage, stop-and-inspect.

## Done When (Phase 2)
- [ ] /search returns real results in dense|sparse|hybrid with relevance_score
- [ ] e2e test hits real endpoint (temp stores via real migrations)
- [ ] FBL-001 closed (003 migration), OBS-009 closed (/health real counts)
- [ ] OBS-006 ablation run + recorded; suite green; runbook updated

## Blockers
None. Parked: eval baseline (Phase 4, incl FBL-002+FBL-005), structure+enrich
(FBL-004 cost gate), second book ingest (anytime, ~15 min, better after P2),
reranker (P3), GraphRAG (P8), headroom-ai, agent.py.

## Phase
Phase 1a COMPLETE + merged. Phase 2 (hybrid search) planned, not started.
