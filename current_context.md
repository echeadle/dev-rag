# Current Context — dev-rag
_Last updated: 2026-07-06_

## Active Files
data/evaluation/devops_questions.yaml (devops-034 added), tests/test_eval.py,
eval/baselines/2026-07-06_hybrid_rrf_4books_37q.json, docs/TODO.md

## Current Step
FOURTH BOOK ingested — `feat/ingest-ansible-real-life` MERGED to main
(287ba01) after Ed's checklist review + his own step-2 fix (0cf4944), pushed:
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

## Slice C (DONE — MERGED to main 7e6c5f3)
Closed the "added value" blind spot: added devops-034, the first eval
positive that targets the RLA book's unique content.
- Question: "How do you set up a multibranch pipeline in Jenkins to run
  Ansible automation?" (ch12). Verified: "multibranch"/"Jenkinsfile" are
  EXCLUSIVE to RLA (0 chunks in the other 3 books); live RRF pre-check top-5
  all RLA. Scores 1.0/1.0/1.0/1.0 (R@1/R@3/MRR/chunk_match).
- test_eval.py `real` set updated to include the RLA filename (the test
  encoded the blind spot — it asserted expected_sources were only the two
  Docker books). 139 tests green.
- NEW OFFICIAL RRF BASELINE (37 questions):
  `eval/baselines/2026-07-06_hybrid_rrf_4books_37q.json` — R@1 84.6, R@3 92.3,
  MRR 89.4, composite 88.3. Supersedes `_hybrid_rrf_4books.json` (36q) as the
  --compare target. The known erosion failures (devops-020, para-001b) persist.
- The reranker baseline `_reranker_c10_4books.json` is now 36q and MISMATCHED
  to the 37q RRF baseline. Deliberately NOT re-run here — slice A re-runs the
  reranker anyway (FBL-006 gating), so the 37q reranker baseline is produced there.

## Next Action — Slice A: FBL-006 negative gating (PLAN — execute on a branch)
Goal: let the reranker say "no confident answer / weak match" instead of
ranking a near-miss #1 for out-of-scope questions (Podman/Nomad/GitLab CI),
so negative precision stops being 0%. This is the unblocker for the ADR-012
reranker-default decision. FIRST create branch `feat/fbl006-negative-gating`.

Core risk that shapes the plan: in reranker mode `relevance_score` IS the
cross-encoder logit, and these near-misses get POSITIVE logits (the reranker
sees "Podman" in the RLA aside and thinks it's relevant). The reranker may
simply not separate near-miss negatives from real answers by logit magnitude.
So LEAD WITH DIAGNOSIS, not implementation.

- **A0 Diagnose (read-only, GO/NO-GO). Do first.** Reranker server up
  (RERANKER_ENABLED=true RERANKER_CANDIDATES=10). Query the 3 negatives
  (devops-007/018/027) + ~10 positives; record top-1 relevance_score (=logit)
  for each. Decision: is there a threshold T with the 3 negatives below and
  positives above, and at what cost in wrongly-rejected positives?
    - Clean separation -> gate path (A1-gate).
    - Overlap -> threshold is the wrong tool -> pivot (A1-pivot).
- **A1-gate:** add a settings threshold (e.g. RERANKER_MIN_LOGIT; default =
  current behavior, nothing changes unless enabled). Apply in the
  retrieval/API layer so REAL responses are flagged/withheld as weak — NOT
  only in eval/scorer.py (moving just the scorer threshold games the metric).
- **A1-pivot (if not separable):** surface a "weak match" confidence flag in
  the API/MCP response instead of hard-dropping, OR document FBL-006 as a
  real reranker limitation. Either is an honest finding that directly informs
  the ADR-012 decision (confident hallucination on out-of-scope = a real cost
  against default-ON).
- **A2 Validate + baseline:** re-run reranker eval on the 37q set with the
  gate — negatives rejected (neg precision up) WITHOUT dropping positives
  (R@1/R@3 must hold; that's the guardrail). Save
  `_reranker_c10_4books_37q.json` (the matched 37q reranker baseline C
  deferred). Update ADR-012 data + docs + a BRANCH-REVIEW-CHECKLIST section.

Guardrails: default OFF / unchanged unless enabled; don't overfit T to 3
negatives (flag small-n; consider adding 1-2 labelled negatives in A0); never
move the eval threshold in isolation. Consider a Plan-agent pass on A2's
implementation once A0 says the gate is viable.

Still open regardless: ADR-012 decision itself (Ed) — reopen data in hand
(R@3 +8 with reranker), latency ~100x. FBL-006 result feeds this.

## Done When (fourth-book ingest) — status
- [x] 413 chunks live, parity 1495; verify passed with book query
- [x] Negatives re-verified post-ingest (read the hits); 007 + 027 notes updated
- [x] 4-book RRF baseline saved + reranker A/B run + reranker baseline saved
- [x] 139 tests green (no code changed — YAML notes + baselines only)
- [x] Branch-review section written; Ed reviewed + merged (287ba01) + pushed
- [ ] ADR-012 reranker-default decision (Ed, next — the reopen data is in hand)

## Blockers
None. Parked: FBL-006 (now with fresh data), structure+enrich (FBL-004),
GraphRAG P8, pgvector P7, headroom-ai.

## Phase
Corpus building: 4 books / 1495 chunks live. Eval now has 37 questions incl.
the first RLA positive (devops-034). Official RRF baseline = the 37q file.
Next: slice A (FBL-006 gating) → then the ADR-012 reranker-default decision.
