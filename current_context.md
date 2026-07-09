# Current Context — dev-rag
_Last updated: 2026-07-09_

## Active File
data/books/Practices_of_the_Python_Pro.pdf ingest (no source code touched
— pure data addition), docs/TODO.md, CLAUDE.md, eval/baselines/.

## Current Step
Ingested Practices of the Python Pro (2nd python-domain book) on branch
`feat/ingest-practices-python-pro`, NOT yet merged. 397 chunks, 250
pages (237 kept), `python` domain now 929/929 in_sync, `devops`
unaffected at 2072. Stage-8 verify passed first try. Tried adding a new
"added-value" eval question (matching devops-034's precedent) but parked
it — genuine semantic overlap between the two python books meant every
candidate query (coupling, type hints, cProfile, pytest) still retrieved
Five Lines of Code first on dense search, even where BM25 correctly
favored the new book. Declined to cherry-pick a winning phrasing.
Existing 6-question baseline reproduces clean, 100% unchanged. New
baseline `eval/baselines/2026-07-09_python_2books_6q.json`.

## Next Action
1. Write Branch Review Checklist section (ingest-style).
2. Ed reviews + merges.

## Done When
- [x] Practices of the Python Pro ingested, corpus parity confirmed (929/929/929)
- [x] Stage-8 verify passing
- [x] python-003 (GIL) negative re-checked live, still holds
- [x] Added-value eval question attempted, parked with a documented reason
- [x] Existing 6q python baseline reproduces at 100%, no regressions
- [x] 147 tests still green (no code changed)
- [ ] Branch Review Checklist section written
- [ ] Ed reviews + merges

## Blockers
None. Parked: structure+enrich (deferred), GraphRAG (no spec, P8),
pgvector (P7), headroom-ai, added-value python-domain eval question
(see above), Art of Unit Testing / Mastering Ubuntu Server / Securing
DevOps / Bourne (AI domain) — none yet placed in data/books/.

**Doc hygiene note found while updating docs/TODO.md:** the "Practices
of the Python Pro" bullet had an orphaned fragment attached below it
("cryptography, TLS, authentication, OAuth 2.0, attack resistance...")
that reads like it belongs to a different, since-deleted book entry (a
security/crypto title, not Practices of the Python Pro). Left as-is —
not guessing what the missing title was. Worth Ed's eye next time he's
in docs/TODO.md.

## Phase
Corpus: 7 books / 3001 chunks / 2 domains populated (devops, python).
No active implementation phase — corpus-building track.
