# Current Context — dev-rag
_Last updated: 2026-07-09_

## Active File
data/books/Securing_DevOps.pdf ingest (no source code touched — pure
data addition), docs/TODO.md, CLAUDE.md, eval/baselines/.

## Current Step
Ingested Securing DevOps (7th DevOps book) on branch
`feat/ingest-securing-devops`, NOT yet merged. 708 chunks, 401 pages
(390 kept), `devops` domain now 3797/3797 in_sync. Ran to completion
cleanly (no environment kill this time). Stage-8 verify passed first
try. Existing negatives re-checked live — all hold. **New erosion
pattern, distinct from the Ansible-competition pattern seen before:**
this is the first book specifically about DevOps *security*, so it now
genuinely, deservedly competes with Docker Deep Dive's security chapter
on security-themed questions (not semantic drift — actual topical
merit, verified by close score margins). New baseline
`eval/baselines/2026-07-09_hybrid_rrf_7books_39q.json`: R@1 -3.8,
source_precision -16.7 (first contest ever for that category),
composite -0.8.

## Next Action
1. Write Branch Review Checklist section (ingest-style).
2. Ed reviews + merges.

## Done When
- [x] Securing DevOps ingested, corpus parity confirmed (3797/3797/3797)
- [x] Stage-8 verify passing
- [x] Existing negatives (Podman/GitLab/Istio/Pulumi) re-checked live
- [x] New 7-book baseline promoted; erosion investigated and explained
- [x] 146 tests still green (no code changed)
- [ ] Branch Review Checklist section written
- [ ] Ed reviews + merges

## Blockers
None. Still not placed in data/books/: Art of Unit Testing,
Rothman/Kimothi (AI, not yet purchased), Stable Diffusion book,
additional Ansible titles (need shelf confirmation).

## Phase
Corpus: 10 books / 5334 chunks / 3 domains (devops, python, ai). No
active implementation phase — corpus-building track.
