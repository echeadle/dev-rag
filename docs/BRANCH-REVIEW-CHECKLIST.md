# Branch Review Checklist

How Ed reviews a feature branch before merging to main. Steps 1–4 apply to
any branch; the live steps are adapted per phase — the pattern is always
"run it in its default state, run it in its changed state, compare."
A phase-specific section is added at each phase close.

**Rule: write the review section BEFORE the branch's final commit.** Appending
the branch's section here (context paragraphs + numbered steps with expected
outputs, plus an index bullet below) is part of finishing the branch, not a
follow-up — a branch without its section is not ready for review or merge.
This applies to EVERY branch that writes code: the sections are how Ed learns
what was done and verifies it independently. Small code fixes committed
directly to main get a short entry (2–3 steps) in the "Small Fixes Log" at the
bottom of this file, in the same commit. Docs-only changes are exempt.
(Also stated in CLAUDE.md "Hard rules".)

- **Phase 3 review** (feat/phase3-reranker): steps below, live off/on curl A/B.
- **Phase 4 review** (feat/phase4-eval): see "Phase 4 — Eval Harness Review"
  at the bottom of this file.
- **Fourth-book ingest** (feat/ingest-ansible-real-life): see "Fourth-Book
  Ingest Review" at the bottom — data/measurement review + the reranker A/B
  that reopened ADR-012.
- **Eval RLA positive** (feat/eval-rla-positive): see "Eval RLA Positive
  Review" at the bottom — adds devops-034, closes the added-value blind spot.
- **Slice A / FBL-006** (feat/fbl006-negative-gating): see "Slice A — FBL-006
  Negative Gating" — negative-gating units-bug fix + reranker default decision.
- **Phase 5 / Python domain** (feat/phase5-python-domain): see "Phase 5 —
  Python Domain" at the bottom — second domain populated for the first
  time, no pipeline code changes, first python eval baseline.
- **Phase 5b / Unified search_all** (feat/phase5b-unified-search-all): see
  "Phase 5b — Unified search_all Ranking" at the bottom — force_rerank
  scoped to search_all only, genuine cross-domain score sorting, and a
  live-measured latency correction to the original plan.
- **Mastering Ansible ingest** (feat/ingest-mastering-ansible): see
  "Mastering Ansible Ingest Review" at the bottom — 5th DevOps book, a
  stage-8 verify-query retry, and live re-verification that the new
  book's Podman content doesn't crack an existing negative test.

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
There is **no code change** — the tracked edits are per-question notes in
`devops_questions.yaml`, two new baseline JSONs, and doc updates (CLAUDE.md,
current_context.md, TODO.md, this checklist); the corpus itself
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
2. `git diff main --stat` — expect **7 files changed, no code**: the eval
   notes (`data/evaluation/devops_questions.yaml`, +12), the two committed
   baselines under `eval/baselines/` (`*_hybrid_rrf_4books.json`,
   `*_reranker_c10_4books.json`, ~532 lines each), and four doc updates
   (`CLAUDE.md`, `current_context.md`, `docs/TODO.md`, this checklist).
   Anything under `src/`, `mcp/`, `tests/`, or `eval/*.py` in the stat is
   unexpected — stop and ask why.
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

---

# Eval RLA Positive Review (feat/eval-rla-positive)

**What this review verifies.** A small ground-truth change: it adds
**devops-034**, the first eval question whose expected source is an Ansible
book, closing the "added value" blind spot (before this, no question pointed
at an Ansible book, so a new book could only register as *erosion*). The
question targets content **exclusive** to the RLA book — a Jenkins multibranch
pipeline running Ansible (`multibranch`/`Jenkinsfile` appear in 0 chunks of
the other three books). One test changes: `test_eval.py`'s `real` set of
expected-source filenames gains the RLA filename (the test literally encoded
the blind spot). The RRF baseline is re-cut on the now-37-question set.

**What "pass" looks like.** 139 green. devops-034 scores 1.0 on
R@1/R@3/MRR/chunk_match with top-1 `ansible-for-real-life-automation.pdf`. The
37q RRF aggregate reproduces R@1 84.6%, R@3 92.3%, MRR 89.4%, Composite 88.3%.

## Steps

1. `git checkout feat/eval-rla-positive`
2. `git diff main --stat` — expect **7 files**: 6 modified (this checklist
   file included) + 1 new baseline (`_hybrid_rrf_4books_37q.json`). The only
   *code* change is one line in `tests/test_eval.py`; the rest are the new
   eval question and doc updates.
3. `git diff main -- data/evaluation/devops_questions.yaml` — read the
   devops-034 block and its verification note (exclusivity + live pre-check).
4. Confirm the exclusivity claim yourself:
   ```bash
   for b in dockerdeepdive a_developers_essential_guide_to_docker_compose \
            ansible-for-devops ansible-for-real-life-automation; do
     printf "%-45s %s\n" "$b" \
       "$(grep -o -i multibranch data/chunks/${b}_chunks.json | wc -l)"
   done
   ```
   — only `ansible-for-real-life-automation` is non-zero.
5. `uv run pytest` — expect **139 passed**.
6. `uv run uvicorn dev_rag.api:app --host 127.0.0.1 --port 8000`
7. In a second terminal — reproduce the 37q baseline:
   ```bash
   uv run python eval/run_eval.py --domain devops --no-save \
       --compare eval/baselines/2026-07-06_hybrid_rrf_4books_37q.json
   ```
   — expect R@1 84.6%, R@3 92.3%, MRR 89.4%, +0.0% deltas, and devops-034
   NOT among the failures (the two failures stay devops-020 + para-001b).
8. Ctrl-C the server.
9. If satisfied:
   ```bash
   git checkout main
   git merge --no-ff feat/eval-rla-positive
   git push origin main
   ```
   Note: the reranker baseline is still 36q and is intentionally refreshed to
   37q in the next slice (FBL-006), not here.

---

# Slice A — FBL-006 Negative Gating (feat/fbl006-negative-gating)

**What this review verifies.** FBL-006 was recorded as "the reranker gives 0%
negative precision — it can't reject out-of-scope queries." A0 diagnosis
overturned that: the 0% was a **units bug**, not a blind model.
`CrossEncoder.predict()` for bge-reranker-v2-m3 returns a **sigmoid
probability in (0,1)**, but `eval/scorer.py` gated negatives with
`reranker_score < 0.0` — a raw-logit cutoff a probability can never satisfy,
so the negative branch could never fire. (The sibling dense branch already
used the correct `< 0.5`.) The fix is a settings-driven **`weak_match`** flag:
when the reranker ran, a hit below `settings.reranker_min_score` (default 0.5 =
sigmoid midpoint = logit 0) is flagged low-confidence. It is a **soft flag,
not a drop** — ranking and R@k are unchanged by construction; the API and MCP
surface the flag and the eval scorer reads it (so the metric measures the gate
that ships, not a scorer-local knob). The eval set grew 37→39q with two
grep-verified-absent negatives (devops-035 Istio, devops-036 Pulumi).

**What "pass" looks like.** 143 green. The matched 39q A/B: RRF gives
R@1 84.6 / R@3 92.3 / negative precision n/a; the gated reranker gives
R@1 96.2 / R@3 100 / MRR 98.1 / **negative precision 80% (4/5)**. Read the
per-metric deltas as the real comparison; composite (88.3→94.7) is only
directional (the runs weight the negative term differently). The gate is a
flag, not a drop, so ranking is provably untouched: gated retrieval
(96.2/100/98.1) matches the pre-gate reranker run (96/100/98). The one residual
leak is devops-027 (GitLab CI, 0.655) — reported, not tuned away (catching it
would false-reject real positives).

## Steps

1. `git checkout feat/fbl006-negative-gating`
2. `git diff main --stat` — expect **17 files changed**: code
   (`settings.py`, `api.py`, `eval/scorer.py`, `mcp/mcp_server.py`, three test
   files), the two new negatives in the YAML, two new baselines, the diagnostic
   script `scripts/fbl006_diagnose.py`, and doc updates (this file, CLAUDE.md,
   ADR-012, TODO, RUNBOOK, current_context).
3. **Read the units-bug fix.** `git diff main -- eval/scorer.py` — the negative
   branch changes from `reranker_score < 0.0` to reading the shipped
   `weak_match` flag. Confirm the reasoning in the docstring.
4. **Confirm the gate is real behavior, not metric-gaming.**
   `git diff main -- src/dev_rag/api.py src/dev_rag/settings.py` — `weak_match`
   is computed in the API response (`reranker_score < settings.reranker_min_score`),
   and `mcp_server.py` annotates "⚠️ weak match". The scorer reads that same
   shipped field.
5. **Verify the two new negatives are genuinely absent** (same bar as the
   original three):
   ```bash
   for b in dockerdeepdive a_developers_essential_guide_to_docker_compose \
            ansible-for-devops ansible-for-real-life-automation; do
     for term in istio pulumi; do
       printf "%-45s %-8s %s\n" "$b" "$term" \
         "$(grep -o -i "$term" data/chunks/${b}_chunks.json | wc -l)"
     done
   done
   ```
   — all counts 0.
6. `uv run pytest` — expect **143 passed**.
7. Reproduce the **RRF** 39q baseline (reranker OFF):
   ```bash
   uv run uvicorn dev_rag.api:app --host 127.0.0.1 --port 8000   # terminal 1
   uv run python eval/run_eval.py --domain devops --no-save \
       --compare eval/baselines/2026-07-06_hybrid_rrf_4books_39q.json   # terminal 2
   ```
   — expect R@1 84.6 / R@3 92.3 / MRR 89.4, +0.0% deltas, negative precision
   n/a, failures devops-020 + para-001b. Ctrl-C the server.
8. Reproduce the **gated reranker** 39q baseline (slow — ~10–13 min on CPU):
   ```bash
   RERANKER_ENABLED=true RERANKER_CANDIDATES=10 \
       uv run uvicorn dev_rag.api:app --host 127.0.0.1 --port 8000   # terminal 1
   uv run python eval/run_eval.py --domain devops --no-save \
       --compare eval/baselines/2026-07-06_hybrid_rrf_4books_39q.json   # terminal 2
   ```
   — expect R@1 96.2 / R@3 100 / MRR 98.1, **negative precision 80.0%**,
   the ONLY failure devops-027 (GitLab CI). Optional: `scripts/fbl006_diagnose.py`
   re-prints the per-question logits (why devops-027 leaks at 0.655). Ctrl-C.
9. If satisfied:
   ```bash
   git checkout main
   git merge --no-ff feat/fbl006-negative-gating
   git push origin main
   ```
   Note: the ADR-012 reranker-default decision stays OFF pending your call —
   the reopen data (R@3 +7.7, neg precision 80%) is now clean, weighed against
   ~100× latency and the one residual near-domain leak.

---

# Phase 5 — Python Domain (feat/phase5-python-domain)

**What this review verifies.** The corpus was 100% DevOps; `python`,
`travel`, and `ai` domains were empty. Phase 5's goal was to prove the
multi-domain architecture works with a second real, populated domain —
not just mechanically accept a `domain` parameter. Investigation before
writing any plan confirmed the architecture was **already fully generic**
(per-domain ChromaDB collections created dynamically at ingest time,
domain-scoped SQLite/FTS5 filtering, domain-agnostic `/search` and
`search_python` MCP tool, domain-driven `/health`). **This branch changes
zero pipeline/retrieval/API code** — it's a content ingest + eval-fixture
update, reusing the exact pipeline invocation pattern already proven on
the 4 DevOps books.

**Book:** *Five Lines of Code* (Clausen) — 338 pages, 532 chunks, avg 1493
chars. Ed confirmed this over the other two owned candidates (Practices of
the Python Pro, Art of Unit Testing) because `data/evaluation/
python_questions.yaml` already had 3 questions (python-004/005/006)
pre-written against it, with an OBS-003 note waiting for ingestion.

**What "pass" looks like.** 143 green (no pipeline code changed — this is
a regression check, not new coverage). `/health` shows `python: 532/532
in_sync: true`, `devops` unaffected at 1495. Live `search_python` MCP
query returns real book content. First python eval baseline
(`eval/baselines/2026-07-08_python_6q.json`, 6 questions): R@1/R@3/R@5/MRR/
chunk_match/composite all **100%**. `python-003` (the GIL question) is
reclassified `no_answer: true` rather than a normal factual question —
grep-verified the book (refactoring/optimization, **TypeScript** examples,
not Python internals) never mentions the GIL, matching the devops-007
(Podman) negative-test convention instead of silently failing chunk_match
forever with no marker distinguishing an expected gap from a regression.

## Steps

1. `git checkout feat/phase5-python-domain`
2. `git diff main --stat` — expect **5 tracked files changed**:
   `data/evaluation/python_questions.yaml` (expected_source populated for
   3 questions), `docs/TODO.md`, `CLAUDE.md`, `current_context.md`, this
   file. Plus one **new tracked file**: `eval/baselines/
   2026-07-08_python_6q.json`. Note: the PDF itself and all pipeline
   artifacts (`data/raw/`, `data/cleaned/`, `data/chunks/`,
   `data/embeddings/` for `five_lines_of_code`) are gitignored — same as
   every existing book — so they won't appear in the diff at all. They
   already exist locally on this machine from the ingest run; the health
   check and eval steps below verify them without needing to re-ingest.
   **No `src/` or `mcp/` files should appear in the diff** — confirms no
   pipeline code changed.
3. **Confirm `expected_source` was verified, not guessed.**
   `git diff main -- data/evaluation/python_questions.yaml` — each of
   python-004/005/006 has a comment citing what was actually checked
   (real chunk text grep, or a live `search_python` query result), per
   the repo's standing rule against guessing `expected_source` from titles.
   `python-003` has a comment too, citing the grep that verified "GIL"
   is genuinely absent (0 matches) before reclassifying it `no_answer: true`.
4. `uv run pytest` — expect **143 passed** (unchanged from before this
   branch — confirms no regression from the new domain's data).
5. **Reproduce the health check:**
   ```bash
   uv run uvicorn dev_rag.api:app --host 127.0.0.1 --port 8000   # terminal 1
   curl -s localhost:8000/health | python3 -m json.tool            # terminal 2
   ```
   — expect `python.chroma_chunks == python.sqlite_chunks == 532`,
   `in_sync: true`, `devops` still `1495/1495`, `stores_in_sync: true`.
6. **Reproduce the python eval baseline:**
   ```bash
   uv run python eval/run_eval.py --domain python --no-save \
       --compare eval/baselines/2026-07-08_python_6q.json   # same terminal 2
   ```
   — expect R@1/R@3/R@5/MRR/chunk_match/composite all 100%, +0.0% deltas
   vs the baseline. Ctrl-C the server (terminal 1).
7. **Optional live spot-check via MCP** (from a Claude Code session with
   the dev-rag MCP server registered): ask `search_python` "What is the
   five-line rule and why does limiting function length improve code
   quality?" — expect the top hit to be from `Five_Lines_of_Code.pdf`,
   quoting the book's actual "Rule: FIVE LINES" section.
8. If satisfied:
   ```bash
   git checkout main
   git merge --no-ff feat/phase5-python-domain
   git push origin main
   ```
   Note: `python-001/002/003` (generic Python questions) intentionally stay
   `expected_source: null` — they were never gated on this specific book,
   and python-003's GIL question genuinely isn't answerable by it. That's
   not a defect to chase inside this branch.

---

# Phase 5b — Unified search_all Ranking (feat/phase5b-unified-search-all)

**What this review verifies.** `_handle_search_all` in `mcp/mcp_server.py`
had two real problems: its "try unified endpoint first" call was dead
code (`/search` requires `domain`, always 422s), and its fallback split
`n_results // 4` evenly across all 4 hardcoded domains regardless of
population, then just concatenated each domain's own sorted results in a
fixed order — not a real cross-domain ranking. RRF scores aren't
comparable across domains (they "encode rank, not relevance," per the
`weak_match` docstring), so fixing this required the reranker, whose
cross-encoder score *is* domain-agnostic. Ed's call: scope this to
`search_all` only, not a global ADR-012 reversal — a new `force_rerank`
field on `SearchRequest`, independent of `settings.reranker_enabled`,
lets `search_all` opt in while `search_devops`/`search_python`/etc. stay
fast and RRF-only by default.

**A real finding changed the plan mid-implementation.** The original plan
assumed `search_all`'s parallel per-domain fan-out (`asyncio.gather`)
would keep total latency to ~one reranked call's worth (~20s), since
requests are sent concurrently. Live testing showed this is wrong: the
server is single-process, and reranking is synchronous CPU-bound work, so
concurrent requests to it serialize rather than overlap — 2 domains
measured ~40-50s, not ~20s. An attempted fix (`asyncio.to_thread` to let
requests overlap via GIL release) was tried and measured **worse**
(50s vs 40s) — this workload is CPU-bound, not GIL-bound, so the fix was
reverted. The honest, corrected cost is **~20s × populated domain
count**, documented in the tool description and `SEARCH_ALL_TIMEOUT`
(raised to 150s).

**What "pass" looks like.** 147 tests green (was 143 — 4 new, 3 updated
for `/health`-driven domain discovery). Single-domain search completely
unaffected: `reranker: null`, ~0.15-0.2s. `search_all` on the current
2-domain corpus (devops, python): only those 2 domains queried (not
travel/ai), results genuinely sorted by `relevance_score` across domains
(not domain-concatenated), total latency ~40-50s.

**⚠️ Gotcha for live MCP testing:** the MCP server is a long-running
stdio process registered once per Claude Code session — it does **not**
hot-reload `mcp_server.py` on file changes. If you test `search_all` via
the actual registered MCP tool without restarting your Claude Code
session (or the MCP server process) after pulling this branch, you will
silently be running the OLD code with no error. Restart your session (or
manually kill the `mcp_server.py` process(es) and let Claude Code
respawn them) before trusting a live MCP test.

## Steps

1. `git checkout feat/phase5b-unified-search-all`
2. `git diff main --stat` — expect 5 code files (`mcp/mcp_server.py`,
   `mcp/tests/test_mcp_server.py`, `src/dev_rag/api.py`,
   `src/dev_rag/settings.py`, `tests/test_api_e2e.py`) plus docs
   (`CLAUDE.md`, `docs/TODO.md`, `docs/RUNBOOK.md`, `current_context.md`,
   this file).
3. **Read the force_rerank addition.**
   `git diff main -- src/dev_rag/api.py src/dev_rag/settings.py` —
   `SearchRequest.force_rerank`, `lifespan()` now loads the reranker
   unconditionally, `use_reranker = settings.reranker_enabled or
   request.force_rerank` gates both the candidate-pool-widening and the
   actual rerank call, and `force_rerank_candidates` (10) is used instead
   of `reranker_candidates` (50) when force_rerank — not the default — is
   the reason reranking is happening. Confirm the comment explaining why
   (50 candidates measures ~112s/query, would blow past any reasonable
   timeout).
4. **Read the search_all rewrite.** `git diff main -- mcp/mcp_server.py`
   — confirm the dead unified-endpoint call is gone, domain population is
   read from `/health`'s `store_parity`, and results are `.sort()`ed by
   `relevance_score` before formatting (not just concatenated).
5. `uv run pytest` — expect **147 passed**.
6. **Confirm single-domain search is unaffected** (default, no
   force_rerank):
   ```bash
   uv run uvicorn dev_rag.api:app --host 127.0.0.1 --port 8000   # terminal 1
   curl -s -X POST localhost:8000/search -H "Content-Type: application/json" \
       -d '{"query": "docker secrets", "domain": "devops", "n_results": 3}' \
       | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['reranker'])"
   ```
   — expect `None`, and the call should complete in well under a second.
7. **Confirm force_rerank works on a direct /search call:**
   ```bash
   curl -s -X POST localhost:8000/search -H "Content-Type: application/json" \
       -d '{"query": "docker secrets", "domain": "devops", "n_results": 3, "force_rerank": true}' \
       | python3 -m json.tool
   ```
   — expect `reranker_score` populated on each result, `"reranker":
   "BAAI/bge-reranker-v2-m3"` in the response, and this call takes
   ~15-25s (not instant, not ~112s).
8. **Confirm search_all's dynamic discovery and cross-domain sort** — per
   the gotcha above, test via direct import rather than the live MCP tool
   unless you've restarted your session:
   ```bash
   DEV_RAG_BASE_URL=http://localhost:8000 uv run python -c "
   import asyncio, sys; sys.path.insert(0, 'mcp')
   import mcp_server
   asyncio.run(mcp_server._handle_search_all({'query': 'docker secrets management', 'n_results': 4}))
   " 2>&1 | tail -5
   ```
   — expect only `devops`/`python` sources (not travel/ai), results in
   descending score order, total wall time ~40-50s. Ctrl-C the server
   (terminal 1).
9. If satisfied:
   ```bash
   git checkout main
   git merge --no-ff feat/phase5b-unified-search-all
   git push origin main
   ```

---

# Mastering Ansible Ingest Review (feat/ingest-mastering-ansible)

**What this review verifies.** This branch ingests the 5th DevOps book
(Mastering Ansible, Freeman) — completing the Ansible trilogy (learn →
apply → master) alongside Ansible for DevOps and Ansible for Real-Life
Automation. **No code change** — the corpus itself (chunks/embeddings/
ChromaDB/SQLite) is gitignored and lives in your local stores from the
ingest run; the tracked edits are a new eval baseline JSON and three doc
updates (CLAUDE.md, current_context.md, docs/TODO.md). So, like prior
ingest branches, this is a review of *data and measurement integrity*.

Two things worth double-checking beyond the routine parity check. First,
**the stage-8 verify query needed a retry**: my first attempt ("How do
you write a custom Ansible module in Python?") scored its entire top-5
from `ansible-for-real-life-automation.pdf`, not the new book — the data
had loaded correctly (parity 2072/2072/2072), the query just wasn't
distinctive enough for a domain with three competing Ansible books. I
re-verified with a "Vault IDs" query (44 mentions in this book vs. one
passing mention in RLA) and it passed cleanly. Second, **this book adds
real Podman content** — an 18-mention `ansible-bender` section on
building containers with Podman/Buildah, more substantial than the other
books' brief asides — which could plausibly have broken the
`devops-007` Podman negative-test question. I checked this live (not by
assumption): the new book's Podman content does not crack the top 10 for
that question; the existing incidental RLA hits still rank higher.
GitLab CI / Istio / Pulumi negatives are unaffected by construction (0
mentions, grep-verified).

**What "pass" looks like.** 147 tests still green (no code changed).
Health shows devops 2072/2072 in sync, python unaffected at 532. The RRF
eval reproduces R@1 84.6%, R@3 96.2%, MRR 89.7%, composite 90.0% — R@3
and composite both **improved** over the 4-book baseline (+3.8 and +1.7
respectively), with only one failure (`devops-020`), which is the
pre-existing, already-documented Ansible source-competition issue (not
new).

## Steps

1. `git checkout feat/ingest-mastering-ansible`
2. `git diff main --stat` — expect **4 files changed, no code**: the new
   baseline `eval/baselines/2026-07-09_hybrid_rrf_5books_39q.json`
   (untracked → added) and three doc updates (`CLAUDE.md`,
   `current_context.md`, `docs/TODO.md`). Anything under `src/`, `mcp/`,
   `tests/`, or `eval/*.py` in the stat is unexpected — stop and ask why.
3. `uv run pytest` — expect **147 passed** (unchanged from Phase 5b —
   confirms no code drifted).
4. Confirm the corpus loaded at parity (no re-ingest needed):
   ```bash
   sqlite3 data/dev_rag.db \
     "SELECT domain, count(*) FROM chunks WHERE status='active' GROUP BY domain;
      SELECT 'fts', count(*) FROM chunks_fts;"
   ```
   — expect `devops|2072`, `python|532`, `fts|2604`.
5. Confirm the new book is queryable (verify stage against the live stores):
   ```bash
   uv run python -m dev_rag.ingest.pipeline \
       --source data/books/MASTERING_ANSIBLE.pdf \
       --domain devops --start-stage 8 \
       --query "How do you use Vault IDs to manage multiple Ansible Vault passwords?"
   ```
   — expect `[8 verify] parity OK (2072); top hit mastering_ansible_...`
   (a Mastering Ansible chunk in the top-5, low distance).
6. Start the server with defaults:
   ```bash
   uv run uvicorn dev_rag.api:app --host 127.0.0.1 --port 8000
   ```
7. In a second terminal — reproduce the RRF baseline (deterministic):
   ```bash
   uv run python eval/run_eval.py --domain devops --no-save \
       --compare eval/baselines/2026-07-06_hybrid_rrf_4books_39q.json
   ```
   — expect R@1 84.6% (+0.0), R@3 96.2% (+3.8), MRR 89.7% (+0.3),
   composite 90.0% (+1.7), one failure: `devops-020` (pre-existing,
   Ansible source competition — not new).
8. OPTIONAL — spot-check the Podman negative directly:
   ```bash
   curl -s -X POST localhost:8000/search -H "Content-Type: application/json" \
       -d '{"query": "What are the best practices for managing Podman rootless containers in production?", "domain": "devops", "n_results": 10}' \
       | python3 -c "import json,sys; [print(r['source']) for r in json.load(sys.stdin)['results']]"
   ```
   — expect all 10 sources to be `ansible-for-real-life-automation.pdf` /
   `ansible-for-devops.pdf` (never `MASTERING_ANSIBLE.pdf`).
9. Ctrl-C the server.
10. If satisfied:
    ```bash
    git checkout main
    git merge --no-ff feat/ingest-mastering-ansible
    git push origin main
    ```

---

# Small Fixes Log

Short verify entries for code fixes committed directly to main (no feature
branch). Newest first. Format: date, commit, one line on what changed, 2–3
numbered steps with expected output.

*(none yet)*
