# Current Context — dev-rag
_Last updated: 2026-07-05_

## Active Files
src/dev_rag/ingest/pipeline.py, tests/test_ingest/test_pipeline.py,
docs/RUNBOOK.md, docs/TODO.md

## Current Step
Big day, all merged + pushed to origin/main (through cc29b5d):
1. MCP smoke slice merged: e2e stdio tests, /collections endpoint, .mcp.json;
   live-checked from a real Claude Code session. reranker_enabled default
   flipped to False (was advertising a Phase 3 stub).
2. Second book ingested: Compose book (Gkatziouras), 272 chunks -> devops
   parity 583/583/583. Stage 8 verify initially failed — DEFAULT_QUERY was
   a Deep Dive question; data was fine, re-ran stage 8 with a Compose query.
3. Root-cause fix: --query now REQUIRED whenever stage 8 runs (fails fast at
   CLI); --dry-run / early --stop-stage exempt. Runbook §3/§4 updated.
   Suite now 113 (was 111; +2 CLI tests).

## Next Action
Phase 3 reranker (bge-reranker-v2-m3, planning/ spec) — the two-book overlap
makes its value measurable now: even a Compose-specific query ranks Deep
Dive's Compose chapter (p136) top. Alt slice: ingest Ansible for DevOps.

## Done When (Phase 3 — to confirm when starting)
- [ ] reranker.py real, wired behind reranker_enabled (flip default to True)
- [ ] e2e test against the real endpoint (per CLAUDE.md stub rule)
- [ ] before/after comparison on cross-book queries recorded

## Blockers
None. Parked: eval baseline P4 (FBL-002/FBL-005 + OBS-003), structure+enrich
(FBL-004 cost gate), GraphRAG P8, headroom-ai.

## Phase
Corpus: 2 books / 583 chunks live. Phase 3 (reranker) is next.
