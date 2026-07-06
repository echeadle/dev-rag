# Current Context — dev-rag
_Last updated: 2026-07-06_

## Active Files
data/books/ansible-for-devops.pdf (ingested), eval/baselines/,
data/evaluation/devops_questions.yaml (027 note), docs/TODO.md

## Current Step
Phase 4+4b MERGED to main (f856341) after Ed's full checklist review
(both server states reproduced to the decimal). Then THIRD BOOK ingested:
- Ansible for DevOps (Geerling): 499 chunks -> corpus 1082/1082/1082.
  Stage-8 verify passed FIRST TRY with book-specific --query (the
  required-query fix doing its job).
- Negative re-check: devops-027 GitLab CI still valid (3 incidental
  mentions only) but bait is stronger now (Jenkins chapter, GH Actions).
  Note updated in the YAML.
- 3-BOOK RE-BASELINE eval/baselines/2026-07-06_hybrid_rrf_3books.json:
  R@1 88 (-4), R@3 100 (held), MRR 93.3, composite 93.5. Single regression:
  devops-025 (env_file) Compose chunk slipped #1->#2 behind Deep Dive —
  first real cross-book competition; recorded, not "fixed".
- This baseline supersedes _hybrid_rrf.json for future --compare runs.

## Next Action
Pick next slice:
1. Ingest Ansible book 2 of 3 (Ansible for Real-Life Automation) — put PDF
   in data/books/, book-specific --query required.
2. Phase 5 python domain, or FBL-006 negative-gating experiment.
3. (Watch: if R@1 keeps sliding as books land, reranker default question
   reopens with real headroom.)

## Done When (third-book ingest) — ALL MET
- [x] 499 chunks live, parity 1082; verify passed with book query
- [x] Negatives re-verified post-ingest; 027 note updated
- [x] 3-book baseline saved + docs updated

## Blockers
None. Parked: FBL-006, structure+enrich (FBL-004), GraphRAG P8,
pgvector P7, headroom-ai.

## Phase
Corpus building: 3 books / 1082 chunks live. Eval baseline current.
