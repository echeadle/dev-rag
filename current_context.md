# Current Context — dev-rag
_Last updated: 2026-07-08_

## Active Files
src/dev_rag/settings.py (reranker_min_score), src/dev_rag/api.py (weak_match),
eval/scorer.py (weak_match gate), mcp/mcp_server.py (⚠️ annotation),
data/evaluation/devops_questions.yaml (devops-035/036),
eval/baselines/2026-07-06_{hybrid_rrf,reranker_c10}_4books_39q.json,
scripts/fbl006_diagnose.py

## Current Step
SLICE A (FBL-006 negative gating) MERGED to main (9fca9d0, then 28cb936)
and pushed to origin. Checklist steps 1–8 run live, Ed approved the merge,
feature branch deleted. 143 tests green. ADR-012 reranker-default decision
made (2026-07-08): **stays OFF** — see below. FBL-006 / Slice A is fully
closed; no open items remain on this thread.

## What Slice A found and shipped
A0 diagnosis overturned the FBL-006 premise: the reranker's "0% negative
precision" was a **units bug**, not a blind model. `CrossEncoder.predict()`
returns a SIGMOID probability in (0,1), but eval/scorer.py gated negatives
with `reranker_score < 0.0` (raw-logit space) — a probability can never be
< 0, so the negative branch could never fire. (The dense branch already used
the correct `< 0.5`.)

Diagnostic (scripts/fbl006_diagnose.py, 5 negatives + 10 positives, reranker
@10 on the live 4-book corpus): at a 0.5 sigmoid threshold, 4/5 negatives
score below it (Nomad 0.008, Istio 0.010, Podman 0.242, Pulumi 0.317); only
devops-027 GitLab CI leaks (0.655, above 3 real positives — the corpus's
Jenkins chapter is strong bait). No clean separation exists, so the honest
tool is a soft flag, not a hard drop.

Shipped (A1): settings-driven `weak_match` flag. `settings.reranker_min_score`
(default 0.5 = sigmoid midpoint = logit 0). api.py sets `weak_match` per
result when the reranker ran; mcp_server.py annotates "⚠️ weak match";
eval/scorer.py reads the shipped flag (so the metric measures the real gate,
not a scorer knob). It is a FLAG, not a drop — ranking/R@k unchanged by
construction. Grew eval 37→39q: added devops-035 (Istio, orthogonal control)
and devops-036 (Pulumi, near-domain), both grep-verified absent (0 hits in
data/chunks/*.json).

## A2 validation (matched 39q baselines saved)
| Metric | RRF 39q | reranker 39q gated | delta |
|---|---|---|---|
| R@1 | 84.6 | 96.2 | +11.5 |
| R@3 | 92.3 | 100 | +7.7 |
| MRR | 89.4 | 98.1 | +8.7 |
| Neg precision | n/a | 80.0 (4/5) | — |
| Composite | 88.3 | 94.7 | +6.4 |
Baselines: `2026-07-06_hybrid_rrf_4books_39q.json` (new official, supersedes
37q) and `2026-07-06_reranker_c10_4books_39q.json`. Guardrail SHOWN, not
asserted: gated retrieval (96.2/100/98.1/92.6) ≈ pre-gate reranker run
(96/100/98/92.3) — the flag left ranking untouched. Read the per-metric deltas
as the rigorous comparison; composite (88.3→94.7) is only DIRECTIONAL (the runs
weight the negative term differently), not a precise gain.

## ADR-012 decision (2026-07-08)
Ed reviewed the reopen data — R@3 +7.7 and negative precision 80%, clearing
the ADR's own +3 R@3 trigger — against ~100× latency (~15–20 s/query on CPU)
and the one residual leak (devops-027 GitLab CI). **Decision: default stays
OFF.** Rationale: this is a single-user tool used interactively via MCP,
where search may be called many times per session — the latency cost
outweighs the quality gain as a default. `RERANKER_ENABLED=true` remains
available per-run for high-precision or suspected-near-domain-bait searches.
Not a standing open item — reopen only on a material change (GPU inference,
caching, further corpus growth). `settings.reranker_enabled` unchanged
(`False`), so no code diff — recorded in ADR-012 (DEV-RAG-ARCHITECTURE.md)
and docs/TODO.md.

## Next Action
None queued. FBL-006 / Slice A / ADR-012 thread is fully closed. Parked
backlog (not started): structure+enrich (FBL-004), GraphRAG (no spec yet,
P8), pgvector (P7), headroom-ai (deferred). Pick the next thread with Ed
when ready.

## Done When (Slice A) — status
- [x] A0 diagnosis: units bug found; 0.5 separates 4/5 negatives (n=5)
- [x] weak_match gate in API + MCP + scorer (real behavior, not metric-gaming)
- [x] eval grown to 39q / 5 negatives (grep-verified absent)
- [x] matched 39q RRF + gated-reranker baselines saved
- [x] 143 tests green
- [x] ADR-012 / TODO / CLAUDE / RUNBOOK updated
- [x] BRANCH-REVIEW-CHECKLIST Slice A section written
- [x] Ed reviews + merges (9fca9d0, pushed to origin/main)
- [x] ADR-012 reranker-default decision made (stays OFF)

## Blockers
None. Parked: structure+enrich (FBL-004), GraphRAG P8, pgvector P7,
headroom-ai.

## Phase
Corpus: 4 books / 1495 chunks. Eval: 39 questions / 5 negatives. FBL-006
resolved and merged to main. ADR-012 decided (reranker OFF by default).
No active phase — awaiting Ed's pick of the next thread.
