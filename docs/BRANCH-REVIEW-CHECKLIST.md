# Branch Review Checklist

How Ed reviews a feature branch before merging to main. Steps 1–4 apply to
any branch; the live steps are adapted per phase — the pattern is always
"run it in its default state, run it in its changed state, compare."
A phase-specific section is added at each phase close.

- **Phase 3 review** (feat/phase3-reranker): steps below, live off/on curl A/B.
- **Phase 4 review** (feat/phase4-eval): see "Phase 4 — Eval Harness Review"
  at the bottom of this file.

## Steps (generic + Phase 3 example)

1. Check out the branch:
   ```bash
   git checkout feat/phase3-reranker
   ```

2. See which files changed:
   ```bash
   git diff main..feat/phase3-reranker --stat
   ```

3. Read the full diff:
   ```bash
   git diff main..feat/phase3-reranker
   ```

4. Run the whole suite:
   ```bash
   uv run pytest
   ```
   Expect the count the branch's commit message states (Phase 3: **127 passed**),
   with BOTH `tests/` and `mcp/tests/` collected.

5. Start the server with defaults:
   ```bash
   uv run uvicorn dev_rag.api:app --host 127.0.0.1 --port 8000
   ```

6. In a second terminal — health check:
   ```bash
   curl -s http://127.0.0.1:8000/health | python3 -m json.tool
   ```
   Expect `"reranker_enabled": false`.

7. Baseline search (fast path):
   ```bash
   curl -s -X POST http://127.0.0.1:8000/search \
     -H 'Content-Type: application/json' \
     -d '{"query": "How do bind mount permissions work in Docker?", "domain": "devops", "n_results": 3}' \
     | python3 -m json.tool
   ```
   Expect ~0.15 s (after the first query's ~10 s embedder load) and
   `"reranker_score": null` on every result.

8. Stop the server (Ctrl-C).

9. Start the server with the feature enabled (one command; the NAME=value
   pairs are env vars for that process only — defaults return on restart):
   ```bash
   RERANKER_ENABLED=true RERANKER_CANDIDATES=10 uv run uvicorn dev_rag.api:app --host 127.0.0.1 --port 8000
   ```
   Wait for `Application startup complete` before querying — the reranker
   loads eagerly first (you'll see a `Loading weights: ... 393/393` progress
   bar; first-ever run also downloads ~2.2 GB). The app's own
   "Reranker loaded" INFO log does NOT appear under uvicorn's default
   logging config — confirm instead with the step 6 health check, which
   should now show `"reranker_enabled": true`.

10. Repeat the step 7 curl.
    Expect ~15 s, a numeric `"reranker_score"` on every result, and
    `"reranker": "BAAI/bge-reranker-v2-m3"` in the response.

11. Stop the server (Ctrl-C).

12. If satisfied, merge and push:
    ```bash
    git checkout main
    git merge --no-ff feat/phase3-reranker
    git push origin main
    ```

## Notes

- Env var names have NO `DEV_RAG_` prefix (`RERANKER_ENABLED`, not
  `DEV_RAG_RERANKER_ENABLED`) — see runbook §5b.
- No-curl option: with the server up, http://127.0.0.1:8000/docs gives a
  browser UI for firing searches (expand POST /search → "Try it out").
- After merging, update `current_context.md` if the merge closes a phase.

---

# Phase 4 — Eval Harness Review (feat/phase4-eval)

**What this review verifies.** The branch turns the eval harness from stubs
into working code and establishes the project's first objective baseline.
Three things need checking. First, the *scorer fixes*: expected_source
matching is now exact everywhere (FBL-002), and negative precision is
mode-aware — it reports "n/a" on plain hybrid runs instead of a fake pass
(FBL-005). Second, the *ground truth*: 36 devops questions of which 25 carry
an `expected_source` verified against actual chunk text — this is what makes
every future `--compare` delta trustworthy. Third, *reproducibility*: running
the harness yourself should reproduce the committed baseline numbers, since
retrieval is deterministic for a fixed corpus and settings.

**What "pass" looks like.** The suite shows 139 green. Your live run matches
the baseline: R@1 92%, R@3 100%, MRR 95.3%, composite 94.1%, and Negative
Precision prints the n/a explanation. The optional reranker run reproduces
the A/B result (R@1 +4, R@3 +0) and shows three F marks — those are the
FBL-006 negatives failing honestly, not a bug in the harness.

## Steps

1. `git checkout feat/phase4-eval`
2. `git diff main..feat/phase4-eval --stat`
3. `git diff main..feat/phase4-eval` — worth extra attention:
   `eval/scorer.py` (the two fixes) and
   `data/evaluation/devops_questions.yaml` (labels + per-question notes)
4. `uv run pytest` — expect **139 passed**
5. `uv run uvicorn dev_rag.api:app --host 127.0.0.1 --port 8000`
6. In a second terminal — reproduce the baseline:
   ```bash
   uv run python eval/run_eval.py --domain devops --no-save
   ```
   — expect R@1 92.0%, R@3 100.0%, MRR 95.3%, Composite 94.1%, and
   `Negative Precision  n/a  (RRF has no relevance scale — FBL-005 ...)`
7. Compare your run against the committed official baseline:
   ```bash
   uv run python eval/run_eval.py --domain devops --no-save \
       --compare eval/baselines/2026-07-06_hybrid_rrf.json
   ```
   — expect deltas of +0.0% across the board (deterministic retrieval)
8. Ctrl-C the server
9. OPTIONAL (~9 min) — reproduce the reranker A/B:
   ```bash
   RERANKER_ENABLED=true RERANKER_CANDIDATES=10 uv run uvicorn dev_rag.api:app --host 127.0.0.1 --port 8000
   ```
   wait for `Application startup complete`, then in the second terminal:
   ```bash
   uv run python eval/run_eval.py --domain devops --no-save \
       --compare eval/baselines/2026-07-06_hybrid_rrf.json
   ```
   — expect R@1 +4.0%, R@3 +0.0%, three F marks (the FBL-006 negatives),
   Negative Precision 0.0%
10. Ctrl-C the server
11. OPTIONAL — spot-check one question's ground truth, e.g. devops-024:
    ```bash
    grep -c "depends_on" data/chunks/a_developers_essential_guide_to_docker_compose_chunks.json
    grep -c "depends_on" data/chunks/dockerdeepdive_chunks.json
    ```
    — the labeled book should clearly win
12. If satisfied:
    ```bash
    git checkout main
    git merge --no-ff feat/phase4-eval
    git push origin main
    ```
