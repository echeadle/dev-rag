# Current Context — dev-rag
_Last updated: 2026-07-06_

## Active Files
data/books/ansible-for-real-life-automation.pdf (ingested), eval/baselines/,
data/evaluation/devops_questions.yaml (007/027 notes), docs/TODO.md,
docs/BRANCH-REVIEW-CHECKLIST.md

## Current Step
FOURTH BOOK ingested on branch `feat/ingest-ansible-real-life` (not yet
merged — awaiting Ed's checklist review):
- Ansible for Real-Life Automation (Madapparambath): 413 chunks -> corpus
  parity 1495/1495/1495. Screenshot-heavy Packt book (480 pages -> 413
  chunks, thinner text than page count). Stage-8 verify passed FIRST TRY
  with a book-specific Jenkins-CI/CD --query (top hit its own chunk, dist 0.206).
- Negative re-check (read the hits, didn't count): all 3 HOLD. Nomad 0
  mentions; Podman 4 incidental "use containers.podman instead" asides;
  GitLab 9 incidental (Git-server option + a CI-tools list) — the book's
  CI/CD chapter is Jenkins-based. Notes updated in the YAML for 007 + 027.
- 4-BOOK RRF re-baseline `eval/baselines/2026-07-06_hybrid_rrf_4books.json`:
  R@1 84 (-4), R@3 92 (-8, OFF THE CEILING for the first time), MRR 89,
  paraphrase 0 (-100), composite 87.8. All erosion traces to ONE cause:
  the RLA book's Ansible/Docker-container/Ansible-Vault content competes
  with the Docker books. Three shifts, all recorded not fixed: devops-020
  (Docker image push), devops-para-001b (secrets paraphrase — keyword-free
  variant now pulls RLA Vault content, breaking the one paraphrase group),
  devops-025 (pre-existing).

## The reranker finding (this session's headline)
R@3 leaving the ceiling reopened the reranker question with REAL headroom.
Ran the A/B (reranker vs RRF on the IDENTICAL 4-book corpus, candidates=10):
`eval/baselines/2026-07-06_reranker_c10_4books.json`.
- Comparable metrics all jumped: R@1 84->96 (+12), R@3 92->100 (+8, ceiling
  recovered), R@5 96->100, MRR 89->98 (+9), chunk_match 80.8->92.3,
  paraphrase 0->100. The reranker RECOVERS exactly the erosion the 4th book
  caused (devops-020 + para-001b fixed).
- Composite fell 87.8->82.6 but that is NOT comparable and NOT a regression:
  on RRF, neg-precision/hallucination are n/a (FBL-005) and excluded; with
  the reranker they become computable (0% / 100%, per FBL-006) and enter the
  score. Every comparable metric improved — mechanical proof of new penalty
  terms, not a quality drop.
- INSIGHT: reranker value is corpus-dependent. Same candidates=10 as the
  earlier A/B that saw R@3 delta 0; the headroom only appeared once
  cross-book competition did.
- ADR-012 REOPENS: its own reopen criterion (R@3 delta >= +3) is now met
  (+8). Latency is still ~100x (~21 s/query @10). So the TRADEOFF genuinely
  reopens — this is Ed's ADR call, recorded not flipped. Default stays OFF
  pending his decision.
- FBL-006 new mechanism data: the reranker's top-1 for devops-007 is now the
  RLA Podman-aside chunk — the 4th book handed the reranker a fresh
  near-miss to confidently mis-rank.

## Next Action
Ed reviews `feat/ingest-ansible-real-life` via the new
docs/BRANCH-REVIEW-CHECKLIST.md section, then merges. THEN decide ADR-012
(reranker default) with the reopen data in hand. Blind spot to close later
(own baseline): no eval question targets the RLA book's unique content, so
this eval could only measure erosion, not the value it added.

## Done When (fourth-book ingest) — status
- [x] 413 chunks live, parity 1495; verify passed with book query
- [x] Negatives re-verified post-ingest (read the hits); 007 + 027 notes updated
- [x] 4-book RRF baseline saved + reranker A/B run + reranker baseline saved
- [x] 139 tests green (no code changed — YAML notes + baselines only)
- [ ] Branch-review section written + committed; Ed reviews + merges
- [ ] ADR-012 reranker-default decision (Ed, post-merge)

## Blockers
None. Parked: FBL-006 (now with fresh data), structure+enrich (FBL-004),
GraphRAG P8, pgvector P7, headroom-ai.

## Phase
Corpus building: 4 books / 1495 chunks live. Eval baseline current
(RRF + reranker A/B). Reranker default decision reopened by measured headroom.
