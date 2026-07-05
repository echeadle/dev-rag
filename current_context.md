# Current Context — dev-rag
_Last updated: 2026-07-04_

## Active Files
docs/plans/dev-rag-phase1a-plan.md, planning/ingest-pipeline-spec.md,
src/dev_rag/ingest.py (-> becoming src/dev_rag/ingest/ package), pyproject.toml,
migrations/001_initial_schema.sql, migrations/002_add_fts5.sql

## Current Step
OBS-007 DECIDED (2026-07-04): the spec wins.
- planning/ingest-pipeline-spec.md supersedes src/dev_rag/ingest.py; the sliding-window
  stub is retired. The docstring's "fixed-size chunking is fine" instinct is kept but
  RELOCATED: it is the Stage-4 quality signal (eval question devops-008 triggers
  structure-aware chunking), NOT a reason to skip the pipeline.
- Phase 1a is scoped to a THIN VERTICAL SLICE (not all 8 spec stages):
  extract -> clean(basic) -> chunk(simple) -> embed -> load -> verify.
  Stage 3 (LLM structure) and Stage 5 (LLM enrich) deferred to Phase 1b.
- Full plan + Claude Code kickoff: docs/plans/dev-rag-phase1a-plan.md (committed to main).

(Prior: OPUS review CLOSED — review/opus-fixes merged to main; 11/12 findings already
fixed + a hardening pass.)

## Decisions Log (Phase 1a)
- Embedding: sentence-transformers, SentenceTransformer("BAAI/bge-m3"), DENSE ONLY
  (sparse channel is FTS5/BM25 per hybrid-search-spec.md -> no FlagEmbedding). dim 1024.
- torch: CPU build (System76 Darter Pro, no GPU) — pinned to a pytorch-cpu index in
  pyproject.toml ([[tool.uv.index]] + [tool.uv.sources]).
- Load DEFINES the storage contract (retrieve.py is an empty stub): Chroma collection
  "{domain}_content"; SQLite data/dev_rag.db per migrations 001+002. The 002 trigger
  auto-populates chunks_fts on insert -> hybrid-ready with NO re-ingest in Phase 2.
- Verify is STORE-LEVEL (direct Chroma/SQLite), NOT via /search or /health
  (those are Phase 2 / OBS-009).

## Next Action
Run Phase 1a per docs/plans/dev-rag-phase1a-plan.md on a NEW branch feat/phase1a-ingest.
Gated, stage-by-stage: one commit per stage, stop-and-inspect after each. Do not push.

## Done When
- [ ] Docker Deep Dive (data/books/) ingested via the thin-slice pipeline
- [ ] chunks in ChromaDB (devops_content) + SQLite (data/dev_rag.db), count parity holds
- [ ] store-level verify passes: a direct ChromaDB query returns Docker Deep Dive chunks
- [ ] all stages committed on feat/phase1a-ingest; existing suite still green + new stage tests

## Blockers
None. Deferred / out of scope until later: OBS-003 expected_source & OBS-006 FTS5 tokenizer
(need an ingested corpus), OBS-009 real parity counts, headroom (removed; headroom-ai
deferred), GraphRAG (no spec), agent.py (unwired).

## Phase
Entering Phase 1a (thin-slice ingest). Phase 0 (review/hardening) closed.
Note: IMPLEMENTATION-ORDER.md still lists 1a as "extract,clean,structure,chunk,enrich" —
this vertical slice defers structure+enrich to 1b; relabel when convenient.
