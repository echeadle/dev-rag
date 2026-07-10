# Current Context — dev-rag
_Last updated: 2026-07-09_

## Active File
data/books/MasteringUbuntuServer.pdf ingest (no source code touched —
pure data addition), docs/TODO.md, CLAUDE.md, eval/baselines/.

## Current Step
Ingested Mastering Ubuntu Server (6th DevOps book) on branch
`feat/ingest-mastering-ubuntu-server`, NOT yet merged. 1017 chunks, 583
pages (567 kept), `devops` domain now 3089/3089 in_sync. **Operational
incident, recovered cleanly:** the background ingest was killed by the
environment right at the stage 6→7 boundary (~33 min into embedding, no
crash) — the embeddings JSON had already been written, so
`--start-stage 7` resumed without re-embedding. Documented as a Lesson
in CLAUDE.md + a backlog item (embed-stage checkpointing) in
docs/TODO.md. All existing negatives clean. **Genuine, documented
erosion:** `devops-para-001b` flipped from passing to failing — verified
live, a recurrence of the same Ansible-vs-Docker corpus-competition
pattern already recorded when RLA was first ingested. New baseline
`eval/baselines/2026-07-09_hybrid_rrf_6books_39q.json`: R@3 96.2→92.3%
(-3.8), MRR -0.5, composite -1.7.

## Next Action
1. Write Branch Review Checklist section (ingest-style).
2. Ed reviews + merges.

## Done When
- [x] Mastering Ubuntu Server ingested, corpus parity confirmed (3089/3089/3089)
- [x] Recovered from a background-task kill without re-running embedding
- [x] Existing negatives (Podman/GitLab/Istio/Pulumi) re-checked live
- [x] New 6-book baseline promoted; erosion investigated and understood, not just noted
- [x] 147 tests still green (no code changed)
- [ ] Branch Review Checklist section written
- [ ] Ed reviews + merges

## Blockers
None. Parked: Practices-of-Python-Pro added-value eval question (prior
session), embed-stage checkpointing (new backlog item, not urgent).
Still not placed in data/books/: Securing DevOps, Art of Unit Testing,
Rothman/Kimothi (AI, not yet purchased), Stable Diffusion book.

**Doc hygiene note (carried over, still unresolved):** docs/TODO.md's
"Practices of the Python Pro" bullet still has an orphaned fragment
below it ("cryptography, TLS, authentication, OAuth 2.0...") — needs
Ed's input on what the missing title was.

## Phase
Corpus: 9 books / 4626 chunks / 3 domains populated (devops, python,
ai — travel still empty). No active implementation phase —
corpus-building track.
