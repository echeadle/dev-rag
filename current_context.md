# Current Context — dev-rag
_Last updated: 2026-07-09_

## Active File
data/evaluation/python_questions.yaml, eval/baselines/2026-07-08_python_6q.json

## Current Step
Phase 5 (python domain) on branch `feat/phase5-python-domain`, NOT yet
merged. Ingested Five Lines of Code under `domain=python` (532 chunks) —
proved the multi-domain architecture needed zero code changes. First
python eval baseline: R@1/R@3/R@5/MRR/chunk_match/composite all **100%**
(`python-003`, the GIL question, reclassified `no_answer: true` after
grep-verifying the book never covers it — matches the devops-007
negative-test convention). `/health`: `python 532/532`, `devops 1495/1495`.

## Next Action
1. `uv run pytest` — expect 143 passed (regression check, no code changed).
2. Ed reviews `docs/BRANCH-REVIEW-CHECKLIST.md`'s "Phase 5" section + merges.

## Done When
- [x] Book ingested, `/health` and MCP query verified live
- [x] `expected_source`/`no_answer` populated and grep/query-verified, not guessed
- [x] First python eval baseline saved, all metrics 100%
- [x] Branch Review Checklist section written
- [ ] Ed reviews + merges

## Blockers
None on Phase 5. Parked (no active justification): structure+enrich
(deferred 2026-07-08 — see docs/TODO.md), GraphRAG (no spec, P8),
pgvector (P7), headroom-ai, remaining Python books (Practices of the
Python Pro, Art of Unit Testing — owned, titles not shelf-confirmed).
Prior closed threads (FBL-006/ADR-012, structure+enrich decision): full
detail lives in DEV-RAG-ARCHITECTURE.md and docs/TODO.md.

## Phase
Corpus: 5 books / 2027 chunks / 2 domains populated (devops, python).
Phase 5 done pending Ed's merge — no active phase after that.
