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

## Tests — the full suite is 106 (as of Phase 2 close, 2026-07-05)
```
uv run pytest              # expect 106 passed (84 in tests/ + 22 in mcp/tests/)
```
The 22 `mcp/tests/` include the fixtures/consumer-alignment tests guarding the two
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

These are still stubs, not working code:
- `reranker.py` (Phase 3), `graph.py`, `agent.py` (unwired — nothing imports
  it), `mcp/compress.py` (no-op). MCP server calls the real API now but is
  not yet smoke-tested end-to-end.
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
