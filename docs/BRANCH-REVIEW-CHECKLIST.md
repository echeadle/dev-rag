# Branch Review Checklist

How Ed reviews a feature branch before merging to main. Steps 1–4 apply to
any branch; the live steps are adapted per phase — the pattern is always
"run it in its default state, run it in its changed state, compare."
A phase-specific section is added at each phase close.

- **Phase 3 review** (feat/phase3-reranker): steps below, live off/on curl A/B.
- **Phase 4 review** (feat/phase4-eval): see "Phase 4 — Eval Harness Review"
  at the bottom of this file.
- **Fourth-book ingest** (feat/ingest-ansible-real-life): see "Fourth-Book
  Ingest Review" at the bottom — data/measurement review + the reranker A/B
  that reopened ADR-012.

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

---

# Fourth-Book Ingest Review (feat/ingest-ansible-real-life)

**What this review verifies.** This branch ingests the fourth book (Ansible
for Real-Life Automation) into the devops corpus and re-baselines the eval.
There is **no code change** — the only tracked edits are per-question notes in
`devops_questions.yaml` and two new baseline JSONs; the corpus itself
(chunks/embeddings/ChromaDB/SQLite) is gitignored and lives in your local
stores from the ingest run. So the review is about *data and measurement
integrity*, not logic. Four things to check. First, **corpus parity**: the new
book brings the stores to 1495/1495/1495 with the new book queryable. Second,
**negative ground truth**: the three no-answer questions (Podman/Nomad/GitLab
CI) must still hold now that an Ansible book covering container management and
CI/CD landed — I re-verified by reading the hits, and updated the 007 + 027
notes to say why they still hold. Third, **the RRF re-baseline**: R@3 left the
ceiling for the first time (100→92) — a recorded erosion from cross-book
competition, not a bug. Fourth, **the reranker A/B**, which is the headline:
that R@3 headroom let the reranker recover the erosion, reopening ADR-012.

**What "pass" looks like.** The suite is still 139 green (no code changed).
Health shows devops 1495/1495 in sync. The RRF eval reproduces R@1 84.0%, R@3
92.0%, MRR 89.0%, composite 87.8%, with the two erosion failures
(devops-020, devops-para-001b) both topped by the RLA book. The optional
reranker A/B reproduces R@1 +12, R@3 +8, MRR +9 vs the RRF 4-book baseline —
and **its composite is *lower* (82.6%), by design**: with the reranker on,
negative precision flips from n/a to 0% (FBL-006) and enters the score, so the
composite is not comparable across the two states. Read the retrieval metrics,
not the composite, for the reranker delta.

## Steps

1. `git checkout feat/ingest-ansible-real-life`
2. `git diff main --stat` — expect **one tracked file changed**
   (`data/evaluation/devops_questions.yaml`, +12) plus two untracked baselines
   under `eval/baselines/` (`*_hybrid_rrf_4books.json`, `*_reranker_c10_4books.json`).
3. `git diff main -- data/evaluation/devops_questions.yaml` — the 007 + 027
   note additions: read them against the claim that all three negatives still
   hold (incidental mentions only; the book's CI/CD chapter is Jenkins-based).
4. `uv run pytest` — expect **139 passed** (both `tests/` and `mcp/tests/`).
5. Confirm the corpus loaded at parity (no re-ingest needed — the stores are
   already populated from the ingest run):
   ```bash
   sqlite3 data/dev_rag.db \
     "SELECT domain, count(*) FROM chunks WHERE status='active' GROUP BY domain;
      SELECT 'fts', count(*) FROM chunks_fts;"
   ```
   — expect `devops|1495` and `fts|1495`.
6. Confirm the new book is queryable (verify stage against the live stores):
   ```bash
   uv run python -m dev_rag.ingest.pipeline \
       --source data/books/ansible-for-real-life-automation.pdf \
       --domain devops --start-stage 8 \
       --query "How do you integrate Ansible with Jenkins to automate a CI/CD pipeline?"
   ```
   — expect `[8 verify] parity OK (1495); top hit
   ansible-for-real-life-automation_0211 ...` (an RLA chunk in the top-5).
7. Start the server with defaults:
   ```bash
   uv run uvicorn dev_rag.api:app --host 127.0.0.1 --port 8000
   ```
8. In a second terminal — reproduce the RRF baseline (deterministic):
   ```bash
   uv run python eval/run_eval.py --domain devops --no-save \
       --compare eval/baselines/2026-07-06_hybrid_rrf_4books.json
   ```
   — expect R@1 84.0%, R@3 92.0%, MRR 89.0%, Composite 87.8%, deltas +0.0%
   across the board, and two failures: `devops-020` and `devops-para-001b`,
   both top-1 `ansible-for-real-life-automation.pdf` (the recorded erosion).
9. Ctrl-C the server.
10. OPTIONAL (~13 min) — reproduce the reranker A/B that reopened ADR-012:
    ```bash
    RERANKER_ENABLED=true RERANKER_CANDIDATES=10 uv run uvicorn dev_rag.api:app --host 127.0.0.1 --port 8000
    ```
    wait for `Application startup complete` (the `Loading weights: ... 393/393`
    bar; health should show `"reranker_enabled": true`), then in the second
    terminal:
    ```bash
    uv run python eval/run_eval.py --domain devops --no-save \
        --compare eval/baselines/2026-07-06_hybrid_rrf_4books.json
    ```
    — expect **R@1 +12.0%, R@3 +8.0%, MRR +9.0%**, paraphrase 0→100, and
    three F marks: `devops-007`, `devops-018`, `devops-027` (the FBL-006
    negatives — the reranker confidently ranks near-miss content #1 for
    out-of-scope questions). **Composite reads 82.6% (lower) on purpose** —
    negative precision became computable (0%) and entered the score; this is
    not a regression, and composites are not comparable across the n/a↔0%
    boundary. Compare only R@1/R@3/MRR.
11. Ctrl-C the server.
12. OPTIONAL — spot-check a negative's ground truth (why 027 still holds
    despite the new CI/CD content):
    ```bash
    grep -o -i "gitlab" data/chunks/ansible-for-real-life-automation_chunks.json | wc -l
    ```
    — 9 incidental hits; none is a GitLab-CI pipeline procedure (the book's
    CI/CD chapter is Jenkins). See the devops-027 note.
13. If satisfied:
    ```bash
    git checkout main
    git merge --no-ff feat/ingest-ansible-real-life
    git push origin main
    ```
    After merging, the open decision is **ADR-012 (reranker default)** — the
    reopen criterion (R@3 delta ≥ +3) is now met at +8, but latency is still
    ~100×. That call is yours; it is recorded in `docs/TODO.md` and
    `current_context.md`, not flipped.
