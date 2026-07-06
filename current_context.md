# Current Context — dev-rag
_Last updated: 2026-07-06_

## Active Files
eval/{loader,reporter,run_eval,scorer,runner}.py, tests/test_eval.py,
data/evaluation/devops_questions.yaml, eval/baselines/, docs/RUNBOOK.md §5c

## Current Step
PHASE 4 + 4b COMPLETE on feat/phase4-eval (NOT merged, NOT pushed — Ed
reviews via docs/BRANCH-REVIEW-CHECKLIST.md, merges). Suite 139 (+12 eval).
- Harness real e2e: loader/reporter/run_eval implemented; scorer FBL-002
  (exact match) + FBL-005 (mode-aware negatives; n/a under plain RRF) fixed;
  runner passes search_mode + base_url; results JSON self-describing config.
- 4b: 36 devops questions (7 new), 25 expected_source VERIFIED against
  data/chunks/*.json. devops-019 converted negative→positive (Compose book
  ch12 = Terraform+ECS); devops-027 GitLab-CI is the new negative.
- OFFICIAL BASELINE eval/baselines/2026-07-06_hybrid_rrf.json:
  R@1 92 / R@3 100 / MRR 95.3 / chunk 84.6 / composite 94.1.
- Reranker A/B (_reranker_c10.json): R@1 +4, R@3 +0, MRR +2.7 @ ~100×
  latency → DEFAULT STAYS OFF (ADR-012 measured table filled; its own
  <+3-R@3 criterion triggered — RRF already at R@3 ceiling on 2 books).
- NEW FINDING FBL-006 (docs/TODO.md): reranker logits don't reject
  near-domain negatives — Podman/Nomad/GitLab all drew positive logits;
  negative precision 0%. Composites not comparable across those runs.
- Docs updated: RUNBOOK §5c, TODO (P4/P4b/FBL-002/005/OBS-003 closed,
  FBL-006 opened), IMPLEMENTATION-ORDER tables, ADR-012, CLAUDE.md.

## Next Action
1. Ed: review feat/phase4-eval (checklist steps 1-4; live step = runbook
   §5c eval run), merge to main.
2. Then pick: ingest next book (Ansible for DevOps — data/books has the
   PDF; book-specific --query required), or Phase 5 python domain, or
   FBL-006 negative-gating experiment.

## Done When (Phase 4 + 4b) — ALL MET
- [x] Harness runs e2e; 12 tests incl. real-endpoint e2e; suite 139 green
- [x] 25+ questions with verified expected_source; baseline saved + tracked
- [x] Reranker A/B recorded; ADR-012 filled; default decision documented

## Blockers
None. Parked: FBL-006, structure+enrich (FBL-004), GraphRAG P8 (now
unblocked by baseline), pgvector P7, headroom-ai.

## Phase
Phase 4 + 4b COMPLETE, pending Ed's review + merge. Corpus growth or
Phase 5 next.
