# Current Context — dev-rag
_Last updated: 2026-07-09_

## Active File
data/books/UNLOCKING_DATA_WITH_GENERATIVE_AI_AND_RAG.pdf ingest (no
source code touched — pure data addition), data/evaluation/ai_questions.yaml
(header comment updated only), docs/TODO.md, CLAUDE.md, eval/baselines/.

## Current Step
Ingested Bourne's RAG book on branch `feat/ingest-bourne-rag-ai-domain`,
NOT yet merged. **This opens the AI domain for the first time** — 608
chunks, 346 pages (334 kept), `ai` domain now 608/608 in_sync, other
domains unaffected. Stage-8 verify passed first try. The 7-question
`ai_questions.yaml` eval set already existed (pre-written, gated on
nothing) — ran unmodified, all 7 questions retrieve top-1 from this
book. New baseline `eval/baselines/2026-07-09_ai_1book_7q.json`.

## Next Action
1. Write Branch Review Checklist section (ingest-style).
2. Ed reviews + merges.

## Done When
- [x] Bourne's RAG book ingested, AI domain corpus parity confirmed (608/608/608)
- [x] Stage-8 verify passing
- [x] Existing ai_questions.yaml eval set run against real content for the first time
- [x] ai-005's chunk_match miss investigated, confirmed a scoring artifact not a gap
- [x] 147 tests still green (no code changed)
- [ ] Branch Review Checklist section written
- [ ] Ed reviews + merges

## Blockers
None. Parked (from the prior session): the Practices-of-the-Python-Pro
added-value eval question. Still not placed in data/books/: Art of Unit
Testing, Mastering Ubuntu Server, Securing DevOps, RAG-Driven Generative
AI (Rothman), A Simple Guide to RAG (Kimothi), Stable Diffusion book.

**Doc hygiene note (carried over, still unresolved):** docs/TODO.md's
"Practices of the Python Pro" bullet still has an orphaned fragment
below it ("cryptography, TLS, authentication, OAuth 2.0...") that reads
like a different, since-deleted book entry. Not touched — needs Ed's
input on what the missing title was.

## Phase
Corpus: 8 books / 3609 chunks / **3 domains populated** (devops, python,
ai — travel still empty). No active implementation phase —
corpus-building track.
