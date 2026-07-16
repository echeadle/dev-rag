# Current Context — dev-rag
_Last updated: 2026-07-16_

## Active File
`feat/ingest-claude-code-production-agents` — not yet merged. Ready for
Ed's review via `docs/BRANCH-REVIEW-CHECKLIST.md`'s "Claude Code
Production Agents Ingest Review" section.

## Current Step
2nd book in the `ai` domain ingested: *Claude Code: Building Production
Agents That Actually Scale* (Thomas De Vos, Leanpub 2026) — Ed dropped the
PDF into `data/books/` himself. 691 chunks, 518 pages (501 kept), `ai`
domain now 1299/1299 in_sync (Bourne 608 + this book 691). Stage-8 verify
passed first try (dist=0.342). Re-ran all 7 existing `ai_questions.yaml`
questions — unchanged, still top-1 Bourne, zero erosion: this book's
subject (Claude Code/agent/MCP engineering) is genuinely orthogonal to
Bourne's RAG-theory content, confirmed empirically not just predicted.
Added `ai-008`, the domain's first eval question with a real
`expected_source` (grep-verified against the live top-1 chunk before
writing the fixture) — scores 100% R@1/R@3/R@5/MRR, composite 95.1%. New
baseline `eval/baselines/2026-07-16_ai_2books_8q.json`. No `src/` changes
— data + eval fixture only, same shape as every prior ingest branch. Full
detail in `docs/BRANCH-REVIEW-CHECKLIST.md` and `CLAUDE.md`'s
current-state log.

## Next Action
Ed reviews the branch (steps in `docs/BRANCH-REVIEW-CHECKLIST.md`'s new
section) and decides whether to merge. After merge/cleanup, the same two
standing candidates from before this ingest are still open: (a) continue
corpus building (AI domain backlog now has Rothman → Kimothi → Alto in
that order, or an Ansible shelf-title to confirm for DevOps), or (b)
write the GraphRAG spec so `graph.py`/`search_graph` can start.

## Done When
- [x] Book ingested, stage-8 verify passed
- [x] Existing eval questions re-checked for regressions (none)
- [x] Added-value eval question added and verified
- [x] Baseline promoted
- [x] Docs updated (TODO.md, CLAUDE.md, BRANCH-REVIEW-CHECKLIST.md)
- [ ] Ed reviews and merges the branch

## Blockers
None. Waiting on Ed's review/merge decision.

## Housekeeping (optional, not blocking)
None outstanding. Background uvicorn server (started for eval testing) was
stopped cleanly (killed by the PID captured at launch, per the CLAUDE.md
Lessons rule).

## Phase
AI-domain corpus building — 2nd book ingested, branch open for review.
