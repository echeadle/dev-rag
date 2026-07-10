# Current Context — dev-rag
_Last updated: 2026-07-09_

## Active File
None — `main` is clean and fully pushed. No feature branch in progress.

## Current Step
Nothing in progress. Today's session (in order): merged Phase 5b
(unified `search_all` cross-domain ranking via scoped `force_rerank`),
then ingested 4 more books (Mastering Ansible, Practices of the Python
Pro, Bourne's RAG book — opened the `ai` domain, Mastering Ubuntu
Server), removed the `travel` domain entirely (Ed's call — no travel
books planned, that's a web-search task), then ingested Securing DevOps.
All merged to `main` and pushed. Corpus: 10 books / 5334 chunks / 3
domains (devops: 7 books/3797 chunks, python: 2 books/929 chunks,
ai: 1 book/608 chunks).

## Next Action
Pick the next unit of work from `docs/TODO.md`. Ready-to-ingest with no
blockers: **The Art of Unit Testing, 3rd Edition** (Osherove & Khorikov)
— python domain, 3rd book, already owned, just needs placing in
`data/books/`. Everything else needs a purchase (Rothman/Kimothi, AI
domain) or shelf-title confirmation (additional Ansible book), or is
explicitly low priority/gated (Stable Diffusion — waits on Oryx Pro).

## Done When
N/A — no task in progress.

## Blockers
None.

## Housekeeping (optional, not blocking)
8 local feature branches are sitting around, all already merged into
`main` — safe to delete whenever convenient
(`git branch --merged main` to list them), not done automatically since
branch deletion wasn't asked for.

## Phase
Corpus-building track, between books. No active implementation phase.
