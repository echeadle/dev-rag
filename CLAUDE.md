# CLAUDE.md — dev-rag

Project conventions for any Claude (Code or chat) session working in this repo.
Read this before running commands or editing files.

> Reflects the `review/opus-fixes` cleanup: headroom removed (so `uv sync`
> resolves) and `mcp/tests` in the default test path (so a bare `pytest` runs
> all 29). If those aren't merged yet, see "If the branch isn't applied yet" below.

## What this is
A **personal, single-user, local** RAG system — not a production SaaS. Scale is
personal (thousands of docs, one user, local inference). Optimize for clarity and
correctness at that scale; **do not introduce enterprise patterns.**

Stack: Python 3.12, FastAPI, Pydantic AI, ChromaDB (→ pgvector planned), SQLite
FTS5, BGE-M3 embeddings, bge-reranker-v2-m3, NetworkX, Docker Compose, MCP server.

## Toolchain — uv only
- **Use `uv` exclusively. Never call `pip` directly.** Use `uv run …`, `uv add …`,
  `uv sync`.
- **Python 3.12** (pinned). If setting up fresh: `uv python pin 3.12`.
- **Setup:**
  ```
  uv sync                  # resolves cleanly
  ```

## Tests — the full suite is 143 (as of Slice A / FBL-006 close, 2026-07-06)
```
uv run pytest              # expect 143 passed (116 in tests/ + 27 in mcp/tests/)
```
The `mcp/tests/` include the fixtures/consumer-alignment tests guarding the two
High review findings (OBS-001/002). **If a bare run reports only the `tests/`
count**, `testpaths` in `pyproject.toml` has regressed to `["tests"]` and is
skipping `mcp/tests` — restore `mcp/tests` to `testpaths` (or run
`uv run pytest tests mcp/tests`). The `tests/` count grows as pipeline stages
are implemented; the invariant to watch is that BOTH directories are collected.
Ingest tests never load real BGE-M3 — the model is always mocked.

## Hard rules
- **Do not revert the canonical `relevance_score` field.** OBS-001 was fixed the
  review's recommended way: one canonical relevance field across producer, all
  consumers, and fixtures. Reverting fixtures to `rrf_score`/`reranker_score`
  reintroduces the exact bug. `rrf_score` may remain only as an optional debug field.
- **ADRs are final.** Architectural decisions live in `DEV-RAG-ARCHITECTURE.md`
  (ADR-001…012). Don't reverse them without flagging a genuine, un-considered risk.
- **Session close:** update `current_context.md` before ending a session (a Stop
  hook checks this).
- **Branch close:** before the final commit on any feature branch, append that
  branch's review section (context paragraphs + numbered steps with expected
  outputs) to `docs/BRANCH-REVIEW-CHECKLIST.md` and add its index bullet at the
  top of that file. A branch without its review section is not ready for Ed's
  review or merge. This is how Ed learns what was done and verifies it himself
  — never skip it because a change "seems small."
- **Code straight to main:** a small isolated code fix committed directly to
  main still gets a short entry (2–3 verify steps with expected output) in
  `docs/BRANCH-REVIEW-CHECKLIST.md` under "Small Fixes Log", in the same
  commit. Docs-only changes are exempt.

## Current state — ingest + hybrid search real (important context)
**Implemented and proven:**
- **Phase 1a (2026-07-05):** `src/dev_rag/ingest/` — thin-slice pipeline
  (extract via pymupdf4llm → clean → chunk 1500/200 → embed BGE-M3 dense →
  load → verify), run as `python -m dev_rag.ingest.pipeline`. Docker Deep Dive
  ingested: 311 chunks, ChromaDB + SQLite + FTS5 at parity. LLM structure/
  enrich deferred (see IMPLEMENTATION-ORDER.md "Ingest Structure + Enrich").
- **Phase 2 (2026-07-05):** `retrieve.py` (dense), `retrieve_sparse.py` (BM25,
  OR-joined terms), `retrieve_hybrid.py` (RRF), `/search` live in all three
  modes with canonical `relevance_score` (per-mode scales — see api.py
  docstring), `/health` real parity counts. E2E tests hit the real endpoint.
  OBS-006 resolved: porter ascii kept (ablation in hybrid-search-spec.md).
- **MCP smoke (2026-07-05):** MCP server smoke-tested e2e over real stdio;
  `.mcp.json` registers it for Claude Code sessions; `/collections` real counts.
  Corpus: 4 books, 1495 chunks (Deep Dive 311 + Compose guide 272 + Ansible
  for DevOps 499 + Ansible for Real-Life Automation 413, last ingested
  2026-07-06 on `feat/ingest-ansible-real-life`). Current official RRF baseline
  is `eval/baselines/2026-07-06_hybrid_rrf_4books_39q.json` (39 questions, 5
  negatives; R@1 84.6 / R@3 92.3 / MRR 89.4) — supersedes the 37q file (Slice A
  added devops-035/036). The 4th book pushed R@3 off the ceiling and reopened
  the reranker default; the matched gated reranker baseline is
  `_reranker_c10_4books_39q.json` — see ADR-012 and the FBL-006 Slice A note below.
- **Phase 3 (2026-07-06):** `reranker.py` real — bge-reranker-v2-m3 wired into
  hybrid mode with OBS-002 fallback, proven live. **Disabled by default**: on
  CPU it costs ~15 s/query @10 candidates (~112 s @50) vs ~0.15 s RRF-only.
  `RERANKER_ENABLED=true` (no `DEV_RAG_` prefix) enables it per-run. See
  runbook §5b.
- **Phase 4 + 4b (2026-07-06):** eval harness real end-to-end (loader/
  reporter/run_eval implemented; FBL-002/FBL-005 scorer fixes; OBS-003
  resolved — 36 devops questions, 25 with expected_source VERIFIED against
  chunk text). Official baseline `eval/baselines/2026-07-06_hybrid_rrf.json`:
  R@1 92 / R@3 100 / MRR 95.3 / composite 94.1. Reranker A/B: R@3 delta 0 →
  default stays OFF (ADR-012 measured table). **When adding eval questions,
  verify expected_source against data/chunks/*.json — never guess from
  titles.** Runbook §5c.
- **Slice A / FBL-006 (2026-07-06):** the reranker's "0% negative precision"
  was a **units bug** — `CrossEncoder.predict()` returns a sigmoid probability
  in (0,1) but the scorer gated with `reranker_score < 0.0` (logit space), so
  it could never fire. Fixed with a settings-driven `weak_match` flag
  (`settings.reranker_min_score`, default 0.5; API + MCP surface it, scorer
  reads it — a SOFT flag, ranking/R@k unchanged). Eval grew to **39q / 5
  negatives** (added devops-035 Istio, devops-036 Pulumi, grep-verified
  absent). Matched 39q baselines `_hybrid_rrf_4books_39q.json` /
  `_reranker_c10_4books_39q.json`: gated reranker gives neg precision 0→80%
  (4/5) with R@1 96.2 / R@3 100. Residual leak devops-027 (GitLab CI). The
  ADR-012 reranker-default decision is still Ed's (reopen data + latency).

These are still stubs, not working code:
- `graph.py`, `agent.py` (unwired — nothing imports it), `mcp/compress.py`
  (no-op).
So contract/fixture/test guarantees are **correct by construction**, not yet proven
against a live pipeline. When implementing a stub, follow the matching `planning/`
spec and add an **end-to-end test hitting the real endpoint** — hand-written
fixtures can't guard a producer that doesn't exist yet.

## Known open items (not bugs to fix blindly)
- **OBS-003** eval `expected_source`: placeholders must become real filenames
  post-ingest (Phase 4b, with FBL-002 + FBL-005 scorer fixes — see docs/TODO.md).
- *(OBS-006 and OBS-009 resolved in Phase 2 — see "Current state" above.)*
- **Context compression (Headroom):** deferred / removed from the build path — see
  the "Deferred" section in `docs/TODO.md`. **Do NOT re-add `headroom`** — the real
  library is `headroom-ai` (imported as `headroom`); bare `headroom` is an unrelated
  CLI. Only revisit after a working, evaluated baseline.
- **GraphRAG:** referenced across the codebase but has **no spec** yet — decide
  scope before implementing `graph.py`.

## Key reference docs
- `docs/RUNBOOK.md` — **how to run everything that currently works** (ingest
  pipeline, store checks, what's still stubbed). Keep it updated every phase.
- `docs/reviews/OPUS-REVIEW.md` — original architecture review
- `docs/reviews/OPUS-REVIEW-VERIFICATION.md` — per-finding re-verification (current)
- `DEV-RAG-ARCHITECTURE.md`, `IMPLEMENTATION-ORDER.md`, `docs/TODO.md`, `planning/*.md`

## If the branch isn't applied yet
Until `review/opus-fixes` is merged: `uv sync` fails on the old `headroom>=0.3.0`
pin — set up with `uv venv --python 3.12 && uv pip install '.[dev]'`, and run tests
with `uv run pytest tests mcp/tests`.
