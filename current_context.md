# Current Context — dev-rag
_Last updated: 2026-07-05_

## Active Files
src/dev_rag/ingest/ (complete thin-slice package: extract, clean, chunk, embed,
load, verify, pipeline), docs/reviews/FABLE-REVIEW-2026-07-05.md, docs/TODO.md

## Current Step
PHASE 1a COMPLETE on feat/phase1a-ingest (11 commits, not pushed). All 8 plan
tasks done; suite 70 passed. Docker Deep Dive is LIVE and retrievable:
- 311 chunks (1500/200 window) in ChromaDB devops_content + SQLite + FTS5,
  parity 311/311/311, idempotent re-load verified (0 inserted, 311 skipped)
- store-level verify passes: the founding query ("production-safe way to store
  secrets in Docker?") returns the book's secrets section (p269) as top hits
- MID-PHASE UPGRADE: extraction switched to pymupdf4llm (markdown output —
  real tables, ## headings on 208/311 chunks). Headings make Phase 1b
  structure detection near-free (regex, not LLM).
- Fable review done: docs/reviews/FABLE-REVIEW-2026-07-05.md; FBL-001..004
  tracked in docs/TODO.md (FTS UPDATE trigger @P2, scorer mismatch @P4b,
  doc drift @1a-close, enrich cost estimate before 1b)

## Next Action
1. FBL-003 doc-drift cleanup commit (dup ADR-010, CLAUDE.md test count now 70,
   IMPLEMENTATION-ORDER 1a/1b relabel, plan's chunks-column list vs 001)
2. Ed: review branch, run it, merge feat/phase1a-ingest -> main, push
3. Then decide next phase. NOTE naming fix (FBL-003): "structure+enrich" is
   its own deferred section in IMPLEMENTATION-ORDER.md, NOT "Phase 1b" (1b =
   MCP wiring there). FBL-004 cost estimate required before starting it.

## Done When
- [x] Docker Deep Dive ingested via thin-slice pipeline
- [x] chunks in ChromaDB (devops_content) + SQLite, count parity holds
- [x] store-level verify passes (direct ChromaDB query returns DDD chunks)
- [x] all stages committed on feat/phase1a-ingest; suite green (70 passed)

## Blockers
None. Deferred: OBS-003/OBS-006 (need corpus — now exists, revisit @P2/P4b),
OBS-009 real parity counts, headroom-ai, GraphRAG (no spec), agent.py,
multi-extractor LLM selection (decided against 2026-07-05, see TODO Deferred).

## Phase
Phase 1a (thin-slice ingest) COMPLETE, pending merge. Next options: deferred
structure+enrich (markdown headings make structure near-free; FBL-004 cost
gate first) or Phase 2 (hybrid search — FTS5 already populated, no re-ingest)
or Phase 1b (MCP wiring per IMPLEMENTATION-ORDER).
