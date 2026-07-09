# dev-rag Implementation Checklist

**Version:** 1.0  
**Date:** June 2026  
**Purpose:** Step-by-step checklist for implementing dev-rag from the existing
codebase to a fully working system with hybrid search, reranker, and evaluation
harness. Work through this in Claude Code, ticking off each item as you go.

---

## Starter Package Versioning

The `dev-rag-starter-vX.Y.zip` file follows this convention:

| Change type | Version bump | Example |
|-------------|-------------|---------|
| Major architectural addition (new spec, new domain, new pipeline) | Major (X) | v3 → v4 |
| Breaking fixes (contract bugs, deprecated APIs, type mismatches) | Major (X) | v1 → v2 |
| Corrections (restored missing content, small fixes, label updates) | Minor (Y) | v3 → v3.1 |
| Small additions (new eval questions, new TODO items) | No new zip — update files individually | — |

**Version history:**
- v1 — Initial starter package (MCP server, specs, scaffold)
- v2 — Opus review fixes (OBS-001 through OBS-012 resolved)
- v3 — Staged ingest pipeline (ADR-013, Phase 1a)
- v3.1 — Corrections (ADR-010 restored, `ai` domain label fix)

---

## Day One — First Time Setup

*Do this once when you get home. After this, use "Before You Start" for every subsequent session.*

- [ ] Download `dev-rag-starter-v3.1.zip` to your laptop
- [ ] Unzip it:
  ```bash
  unzip dev-rag-starter-v3.1.zip
  cd dev-rag
  ```
- [ ] Copy the environment template and add your Anthropic API key:
  ```bash
  cp .env.example .env
  # Edit .env and set ANTHROPIC_API_KEY=your-key-here
  ```
- [ ] Initialise git and make the first commit:
  ```bash
  git init
  git add .
  git commit -m "Initial commit — dev-rag-starter-v3.1"
  ```
- [ ] Create a new private repository on GitHub named `dev-rag`
- [ ] Push to GitHub:
  ```bash
  git remote add origin git@github.com:YOUR_USERNAME/dev-rag.git
  git branch -M main
  git push -u origin main
  ```
- [ ] Verify `.env` is not tracked:
  ```bash
  git status
  # .env should NOT appear — it is covered by .gitignore
  ```
- [ ] Install dependencies:
  ```bash
  uv sync
  ```
- [ ] Start Docker services:
  ```bash
  docker compose up -d
  docker compose ps   # verify dev-rag service is healthy
  ```
- [ ] Confirm API is responding:
  ```bash
  curl http://localhost:8000/health
  ```
- [ ] Open Claude Code in the `dev-rag` directory:
  ```bash
  claude .
  ```
- [ ] Run `/init` in Claude Code to load project context

**Checkpoint:** Repository on GitHub, API running, Claude Code connected, `.env` safe. ✓  
Continue to Phase 1a (staged ingest pipeline).

---

## Before You Start

*Run this at the beginning of every subsequent work session.*

- [ ] Pull the latest code from GitHub:
  ```bash
  git pull origin main
  ```
- [ ] Open Claude Code in the `dev-rag` project directory
- [ ] Confirm existing tests still pass: `uv run pytest`
- [ ] Review `planning/` folder — all specs are there

---

## Phase 1a — Thin-Slice Ingest Pipeline ✅ COMPLETE 2026-07-05

*Goal (as rescoped 2026-07-04, see `docs/plans/dev-rag-phase1a-plan.md`): a
thin vertical slice — local PDF → retrievable dense chunks. LLM stages
(3 structure, 5 enrich) deferred; see "Ingest Structure + Enrich" below.*
*Spec: `planning/ingest-pipeline-spec.md`*

- [x] Create `src/dev_rag/ingest/` package replacing the `ingest.py` stub
- [x] Implement `extract.py` — PDF → markdown via **pymupdf4llm** (upgraded
      mid-phase from plain PyMuPDF: real tables, `##` headings)
- [x] Run Stage 1 on Docker Deep Dive, inspect `data/raw/` output
- [x] Implement `clean.py` — noise removal (TOC, page numbers, blank/short pages;
      no header heuristic — pymupdf4llm strips headers/footers itself)
- [x] Run Stage 2, inspect `data/cleaned/` — 273 kept / 7 removed, verified
- [x] Implement `chunk.py` — fixed 1500/200 window, word-boundary snapped
      (semantic section chunking deferred with Stage 3)
- [x] Run Stage 4, inspect `data/chunks/` — 311 chunks, avg 1491 chars
- [x] Implement `embed.py` — BGE-M3 dense (dim 1024, normalized, CPU)
- [x] Implement `load.py` — ChromaDB `devops_content` + SQLite + FTS5 triggers,
      content_hash idempotency, count-parity assertion
- [x] Implement `verify.py` — store-level smoke test after ingest
- [x] Implement `pipeline.py` — orchestrator with `--start-stage`/`--stop-stage`/`--dry-run`
- [x] Run full pipeline on Docker Deep Dive end-to-end (parity 311/311/311)
- [x] Run full test suite: `uv run pytest` (70 passed)

**Checkpoint:** Docker Deep Dive ingested and retrievable — the founding query
("production-safe way to store secrets in Docker?") returns the book's secrets
section (p269) from a direct ChromaDB query. ✓

---

## Ingest Structure + Enrich — DEFERRED from Phase 1a (unscheduled)

*The former Phase 1a stages 3 and 5. NOT the same thing as "Phase 1b" below
(MCP wiring) — the phase1a plan's "defer to 1b" phrasing meant this section.
Schedule deliberately: after the eval baseline (Phase 4) can measure whether
enrichment earns its cost, and gated on the FBL-004 cost estimate.*

- [x] FBL-004 cost estimate ✅ 2026-07-08 — real corpus (1495 chunks, 4 books):
      ~$12.56 sync / ~$6.28 via Batch API for a full enrichment pass (worst
      case ~$26/~$13). Cost is a non-issue at this scale — the cost gate is
      cleared. See docs/TODO.md for the full breakdown.

**Section DEFERRED (Ed's call, 2026-07-08) — do not start.** The cost gate
cleared, but investigating a narrower first slice (structure-aware
chunking only) found the concrete justification (eval failure
`devops-020`) is already fixed by the gated reranker — it's source
competition between books now, not a chunking defect. Also: the spec's
`structure.py` (below) is LLM-based, not regex — its boundary-detection
logic is an unfinished TODO stub in the spec, not ready to wire up. Full
reasoning in docs/TODO.md. **Re-open only if a new eval failure genuinely
points at a chunk-boundary problem the reranker can't fix.**

- [ ] Implement `structure.py` — LLM-based chapter/section detection per
      `planning/ingest-pipeline-spec.md` Stage 3 (its boundary-detection
      logic is currently an unimplemented TODO stub in the spec itself —
      not regex over markdown headings, that was a stale assumption)
- [ ] Implement semantic chunking at section boundaries (spec Stage 4 proper)
- [ ] Implement `enrich.py` — summaries, keywords, synthetic questions, code
- [ ] Add enrichment columns to SQLite schema (`migrations/00X_enriched_schema.sql`)
- [ ] Re-ingest, compare against the fixed-window baseline via the eval harness

---

## Phase 1b — Wire Up MCP Server

*Goal: Claude Code can query the running dev-rag API from the terminal.*

- [ ] Copy `mcp/mcp_server.py` into the project if not already present
- [ ] Install MCP server dependencies: `uv add mcp httpx`
- [ ] Start the dev-rag API: `docker compose up -d`
- [ ] Confirm API is healthy: `curl http://localhost:8000/health`
- [ ] Register MCP server with Claude Code:
  ```bash
  claude mcp add --transport stdio dev-rag \
    --env DEV_RAG_BASE_URL=http://localhost:8000 \
    -- python mcp/mcp_server.py
  ```
- [ ] Verify registration: `claude mcp list` — should show `dev-rag ✓ Connected`
- [ ] Run MCP server tests: `uv run pytest mcp/tests/`
- [ ] Ingest one test document to confirm end-to-end works:
  ```bash
  docker compose exec dev-rag uv run python -m dev_rag.ingest \
    --source /data/your-first-book.pdf --domain devops
  ```
- [ ] Run a test query from Claude Code: `search_devops("docker secrets")`

**Checkpoint:** You can query the system from Claude Code. ✓

---

## Phase 2 — Hybrid Search

*Goal: BM25 + dense vectors fused with RRF. Spec: `planning/hybrid-search-spec.md`*

- [ ] Run migration: `migrations/002_add_fts5.sql` against SQLite
- [ ] Verify FTS5 table created: `sqlite3 dev_rag.db ".tables"` — should include `chunks_fts`
- [ ] Re-ingest one document to populate FTS5 via trigger
- [ ] Verify trigger fired: `sqlite3 dev_rag.db "SELECT count(*) FROM chunks_fts;"`
- [ ] Implement `src/dev_rag/retrieve_sparse.py`
- [ ] Run sparse tests in isolation: `uv run pytest tests/test_hybrid_search.py::test_bm25*`
- [ ] Implement `src/dev_rag/retrieve_hybrid.py`
- [ ] Run RRF tests: `uv run pytest tests/test_hybrid_search.py::test_rrf*`
- [ ] Add `search_mode` parameter to `/search` route in `api.py`
- [ ] Run full test suite: `uv run pytest` — all tests should pass
- [ ] Test manually: compare `search_mode=dense` vs `search_mode=hybrid` on:
  - `--network=host flag behaviour`
  - `docker compose secrets: syntax`
  - `COPY --chown directive`

**Checkpoint:** Hybrid search is live and passing all tests. ✓

---

## Phase 3 — Reranker ✅ 2026-07-06

*Goal: Cross-encoder second pass over hybrid results. Spec: `planning/reranker-spec.md`*

- [x] Dependency already present (`sentence-transformers>=3.0.0` — no add needed)
- [x] Implement `src/dev_rag/reranker.py`
- [x] Run reranker tests (all mocked — no model download needed):
  `uv run pytest tests/test_reranker.py` (12 passed; + 2 real-endpoint e2e)
- [x] Add startup model load to `api.py` (lifespan, OBS-010 — not compose;
  runs via `uv run uvicorn`, see runbook §5b)
- [x] Start API and confirm model downloads and loads ("Reranker loaded" seen)
- [x] Wire reranker into `/search` route — Stage 1 candidates raised to 50
  (dense/sparse backends widened too, or the pool can't fill)
- [x] Run full test suite: `uv run pytest` (127 passed)
- [x] Verified live against the 583-chunk corpus; `/search` returns
  reranker model + per-result `reranker_score`

**Checkpoint:** Two-stage retrieval (hybrid + reranker) is live. ✓
**Deployment note:** shipped `reranker_enabled=False` by default — measured
~15 s/query @10 candidates (~112 s @50) on CPU vs ~0.15 s RRF-only.
`RERANKER_ENABLED=true` per-run; Phase 4 eval decides the default.

---

## Phase 4 — Evaluation Harness ✅ 2026-07-06

*Goal: Objective baseline score before any further changes.*
*Spec: `planning/dev-rag-evaluation-strategy.md`*

- [x] `data/evaluation/` directory (existed with 43 question bodies)
- [x] Implement `eval/loader.py`
- [x] `eval/runner.py` (already real; added search_mode/base_url passthrough)
- [x] `eval/scorer.py` (already real; FBL-002 + FBL-005 fixed here)
- [x] Implement `eval/reporter.py`
- [x] Implement `eval/run_eval.py`
- [x] `data/evaluation/devops_questions.yaml` (29 bodies existed; grown to 36)
- [x] Run harness: `uv run python eval/run_eval.py --domain devops`
- [x] Baseline saved: `eval/baselines/2026-07-06_hybrid_rrf.json` (tracked)
- [x] Baseline scores recorded below

**Baseline scores (2026-07-06, hybrid RRF, 36 questions / 25 ground-truthed):**

| Metric | Baseline | + reranker@10 |
|--------|----------|---------------|
| Retrieval@1 | 92.0% | 96.0% |
| Retrieval@3 | 100% | 100% |
| MRR | 95.3% | 98.0% |
| Chunk Match | 84.6% | 88.5% |
| Negative Precision | n/a (FBL-005: RRF) | 0.0% (FBL-006) |
| Composite Score | 94.1% | 81.6% (not comparable — see ADR-012) |

**Checkpoint:** Eval harness running, baseline established. ✓
Reranker default stays OFF per ADR-012 measured table (R@3 delta 0).

---

## Phase 4b — Grow Eval Question Set ✅ 2026-07-06

*Goal: 25 questions with `expected_source` populated before trusting --compare deltas.*
*Decision: Athens, June 2026 — minimum threshold before gating migrations.*

- [x] Real source filenames confirmed: `dockerdeepdive.pdf`,
  `A_DEVELOPERS_ESSENTIAL_GUIDE_TO_DOCKER_COMPOSE.pdf`
- [x] Every expected_source verified against chunk artifacts (grep
  data/chunks/*.json) — never guessed from titles
- [x] Grown to 36 devops questions (7 added: 6 verified single-book
  positives + GitLab-CI negative replacing converted devops-019)
- [x] ≥3 questions per major category
- [x] Harness run: `questions_with_expected_source: 25` confirmed
- [x] Official baseline saved: `eval/baselines/2026-07-06_hybrid_rrf.json`

**Checkpoint:** 25+ questions, baseline trustworthy for delta comparisons. ✓

---

## Phase 5 — Python Domain

*Goal: Third corpus ready for Python books. Decision: ADR-011.*

- [ ] Add `python` to valid domain values in `settings.py`
- [ ] Confirm `search_python` tool already present in `mcp/mcp_server.py` ✓
  *(already implemented — nothing to do here)*
- [ ] Create `data/evaluation/python_questions.yaml` with initial questions
- [ ] Ingest first Python book:
  ```bash
  docker compose exec dev-rag uv run python -m dev_rag.ingest \
    --source /data/your-python-book.pdf --domain python
  ```
- [ ] Verify: `search_python("descriptors")` returns results from Claude Code
- [ ] Run eval harness with Python questions:
  `uv run python eval/run_eval.py --domain python`

**Checkpoint:** Python domain live and queryable. ✓

---

## Phase 5b — Unified search_all Ranking

*Goal: search_all produces a single reranked list across all domains.*
*Decision: Athens, June 2026 — implement before adding more domains.*

- [ ] Update `_handle_search_all()` in `mcp_server.py` to pass the merged
  per-domain candidates through the reranker before returning results
- [ ] Add `n_results` per domain to fetch enough candidates (e.g. 20 per
  domain = 60 total candidates → reranker returns top 10)
- [ ] Update `test_search_all_unified_endpoint` to assert results are
  ordered by `relevance_score` descending, not by domain
- [ ] Test manually: `search_all("Docker secrets and Python context managers")`
  — results should interleave domains by relevance, not batch by domain
- [ ] Run full test suite: `uv run pytest`

**Checkpoint:** `search_all` returns unified relevance-ranked results. ✓

---

## ~~Phase 6 — Headroom Compression~~ (DEFERRED — see `docs/TODO.md` Deferred section)

~~*Goal: Token reduction on MCP server output.*~~
~~*Spec: `planning/headroom-integration-spec.md`*~~

- ~~Install Headroom: `uv add headroom`~~
- ~~Implement `mcp/compress.py`~~
- ~~Run compress tests: `uv run pytest mcp/tests/test_compress.py`~~
- ~~Add `from compress import compress_text, compression_stats` to `mcp_server.py`~~
- ~~Add `compress_text()` call in `_handle_domain_search()`~~
- ~~Add `compress_text()` call in `_handle_search_all()`~~
- ~~Add compression stats to `_handle_health()`~~
- ~~Run full MCP server tests: `uv run pytest mcp/tests/`~~
- ~~Run a query from Claude Code and check `rag_health` for compression stats~~
- ~~Confirm answer quality is preserved at default ratio (0.4)~~

**Checkpoint:** deferred — no longer gates Phase 7. Revisit only after a working,
evaluated RAG baseline; see `docs/TODO.md` Deferred section.

---

## Phase 7 — pgvector Migration

*Goal: Replace ChromaDB + SQLite with single Postgres instance.*
*Spec: `planning/pgvector-migration-spec.md`*

- [ ] **Save ChromaDB baseline first:**
  `uv run python eval/run_eval.py --domain devops`
  Note the results JSON path.

- [ ] Add Postgres service to `docker-compose.yml`
- [ ] Run `migrations/003_pgvector.sql`
- [ ] Verify pgvector version ≥ 0.8.2:
  ```sql
  SELECT extversion FROM pg_extension WHERE extname = 'vector';
  ```
- [ ] Add `asyncpg` dependency: `uv add asyncpg`
- [ ] Implement `src/dev_rag/retrieve_pgvector.py`
- [ ] Add asyncpg pool to `api.py` startup
- [ ] Swap retrieval backend in `/search` route
- [ ] Re-ingest one domain into Postgres
- [ ] Run full test suite: `uv run pytest`
- [ ] **Run eval harness and compare:**
  ```bash
  uv run python eval/run_eval.py --domain devops \
    --compare eval/results/<chromadb-baseline>.json
  ```
- [ ] Record delta scores:

| Metric | ChromaDB | pgvector | Delta |
|--------|----------|----------|-------|
| Retrieval@3 | | | |
| MRR | | | |
| Composite Score | | | |

- [ ] Update ADR-003 with measured delta
- [ ] If delta is acceptable: remove `retrieve_sparse.py`, `retrieve_hybrid.py`,
  `migrations/002_add_fts5.sql`, and `chroma_db/` directory
- [ ] Re-ingest all domains into Postgres

**Checkpoint:** pgvector live, ChromaDB retired, delta documented. ✓

---

## After Each Phase

Always do these three things after completing a phase:

1. **Run the full test suite:** `uv run pytest` — no regressions
2. **Run the eval harness:** `uv run python eval/run_eval.py` — no score drops
3. **Commit:** `git add -A && git commit -m "Phase N complete: <description>"`

---

## Planning Documents Reference

| Document | Purpose |
|----------|---------|
| `DEV-RAG-ARCHITECTURE.md` | ADRs — why every decision was made |
| `planning/hybrid-search-spec.md` | Phase 2 implementation detail |
| `planning/reranker-spec.md` | Phase 3 implementation detail |
| `planning/dev-rag-evaluation-strategy.md` | Phase 4 implementation detail |
| `planning/headroom-integration-spec.md` | Phase 6 implementation detail |
| `planning/pgvector-migration-spec.md` | Phase 7 implementation detail |
| `planning/rag-document-update-strategy.md` | Document update pipeline reference |

---

*Planning phase complete as of June 2026 (Athens). Implementation begins at home.*
