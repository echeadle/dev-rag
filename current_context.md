# Current Context — dev-rag
_Last updated: 2026-07-08 (Phase 5 in progress)_

## Active Files
data/books/Five_Lines_of_Code.pdf, data/chunks/five_lines_of_code_chunks.json,
data/evaluation/python_questions.yaml (python-004/005/006 expected_source),
eval/baselines/2026-07-08_python_6q.json, CLAUDE.md, docs/TODO.md

## Current Step
On branch `feat/phase5-python-domain`, NOT yet merged. Ingested Five Lines
of Code (Clausen) under `domain=python` — 532 chunks, 338 pages — proving
the multi-domain architecture (already fully generic, no code changes
needed) works with a second real, populated domain. Steps 1–8 of the plan
done and verified live (pipeline stage-8 self-verify passed, `/health`
shows `python: 532/532 in_sync`, live MCP `search_python` query confirmed
real content, `expected_source` populated for python-004/005/006 against
real chunk text, first python eval baseline saved).

## What's left (plan steps 9–10)
1. Append the Branch Review Checklist section (context + numbered verify
   steps) to `docs/BRANCH-REVIEW-CHECKLIST.md`, plus its index bullet —
   required before the final commit per CLAUDE.md's hard rule.
2. Run `uv run pytest` — expect 143 passed (no pipeline code changed,
   this is a regression check).
3. Ed reviews and merges `feat/phase5-python-domain` → `main`, pushes.

## Phase 5 result summary
- Corpus: 5 books / 2027 chunks / 2 populated domains (devops 1495,
  python 532; travel/ai still 0).
- First python eval baseline: `eval/baselines/2026-07-08_python_6q.json`
  — R@1/R@3/R@5/MRR all 100%, composite 85.3%.
- chunk_match 50% (below 70% target): python-003 (GIL question) has no
  answer in this book — a genuine corpus-coverage gap (book is
  refactoring/optimization-focused, TypeScript examples not Python
  internals), not a retrieval defect. Not in scope to fix here.
- Correction recorded in docs/TODO.md: the book's code examples are
  TypeScript, not Python as an earlier doc note assumed — principles are
  language-agnostic, same pattern as Art of Unit Testing's JS examples.

## Prior thread — FBL-006 / Slice A / ADR-012 (closed 2026-07-08)
Reranker's "0% negative precision" was a units bug (logit-space threshold
on a sigmoid score), fixed with a `weak_match` soft flag. Shipped, merged
to main (9fca9d0, 28cb936). ADR-012 reranker-default decision: **stays
OFF** (single-user MCP tool, latency cost outweighs quality gain as
default; `RERANKER_ENABLED=true` available per-run). Full detail in
DEV-RAG-ARCHITECTURE.md and docs/TODO.md — not repeated here.

## Prior thread — structure+enrich (Phase 1b), deferred 2026-07-08
FBL-004 cost estimate cleared (~$6–13/pass), but the concrete
justification (fixing eval failure devops-020) turned out to already be
solved by the gated reranker, and the spec's `structure.py` has an
unimplemented boundary-detection TODO stub. **Deferred** until a real,
currently-unfixed eval failure points at an actual chunk-boundary defect.
Full detail in docs/TODO.md and IMPLEMENTATION-ORDER.md.

## Next Action
Finish Phase 5 (branch review section, test run, Ed's merge — see above).
After that: no queued thread. Remaining backlog (not started, no
immediate justification): GraphRAG (no spec yet, P8), pgvector (P7),
headroom-ai (deferred), remaining Python books (Practices of the Python
Pro, Art of Unit Testing — both owned, titles not yet shelf-confirmed).

## Blockers
None on Phase 5. Parked: structure+enrich (Phase 1b), GraphRAG P8,
pgvector P7, headroom-ai.

## Phase
Corpus: 5 books / 2027 chunks / 2 domains populated (devops, python).
FBL-006 + ADR-012 closed. Structure+enrich deferred. Phase 5 (python
domain) in progress on `feat/phase5-python-domain` — awaiting branch
review section + Ed's merge.
