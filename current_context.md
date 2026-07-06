# Current Context — dev-rag
_Last updated: 2026-07-05_

## Active Files
data/books/A_DEVELOPERS_ESSENTIAL_GUIDE_TO_DOCKER_COMPOSE.pdf (ingested),
docs/TODO.md, src/dev_rag/ingest/pipeline.py (DEFAULT_QUERY note)

## Current Step
SECOND BOOK INGESTED (2026-07-05, after MCP smoke merge + push):
- Docker Compose book (Gkatziouras): 264 pages -> 272 chunks (avg 1490
  chars) -> corpus parity 583/583/583 (was 311).
- Stage 8 verify failed on first run: DEFAULT_QUERY is a Docker-secrets
  question that Deep Dive owns, so the new book missed top-5. Data was
  fine; re-ran `--start-stage 8 --query "<compose question>"` -> passed.
  Lesson recorded in docs/TODO.md: pass a book-specific --query per ingest.
- Even on the Compose query, Deep Dive p136 is top hit (its own Compose
  chapter) — cross-book competition is now real; reranker value measurable.
- TODO.md updated: Phase 1b marked complete, both Docker books checked off.

## Next Action
1. Commit TODO.md + current_context.md (docs-only, main is fine).
2. Optional quick win: live MCP search against the grown corpus (bind mount
   permissions query should now hit the Compose book).
3. Next slice: Phase 3 reranker — corpus now has the two-book overlap that
   makes it measurable. (Alt: third book, Ansible for DevOps.)

## Done When (second-book ingest) — ALL MET
- [x] Compose book ingested to devops, parity 583/583/583
- [x] Stage 8 verify passed (with book-specific query)
- [x] Lesson + book checkboxes recorded in docs/TODO.md

## Blockers
None. Parked: eval baseline P4 (FBL-002/FBL-005 scorer fixes + OBS-003),
structure+enrich (FBL-004 cost gate), GraphRAG P8, headroom-ai.

## Phase
Corpus building: 2 books live (583 chunks). Phase 3 (reranker) is next.
