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

## Phase 1a — Staged Ingest Pipeline

*Goal: Clean, structured, enriched chunks before anything hits the embedder.*
*Spec: `planning/ingest-pipeline-spec.md`*

- [ ] Create `src/dev_rag/ingest/` package replacing the `ingest.py` stub
- [ ] Implement `extract.py` — PDF → raw text using PyMuPDF
- [ ] Run Stage 1 on Docker Deep Dive, inspect `data/raw/` output
- [ ] Implement `clean.py` — noise removal (TOC, headers, page numbers)
- [ ] Run Stage 2, inspect `data/cleaned/` — verify right pages removed
- [ ] Implement `structure.py` — LLM chapter/section detection
- [ ] Run Stage 3, inspect `data/structured/` — verify section boundaries
- [ ] Implement `chunk.py` — semantic chunking at section boundaries
- [ ] Run Stage 4, inspect `data/chunks/` — verify chunk quality and size
- [ ] Implement `enrich.py` — summaries, keywords, synthetic questions, code
- [ ] Run Stage 5, inspect `data/enriched/` — verify enrichment quality
- [ ] Add enrichment columns to SQLite schema (`migrations/003_enriched_schema.sql`)
- [ ] Implement `load.py` — write enriched chunks to ChromaDB + SQLite
- [ ] Implement `verify.py` — smoke test after ingest
- [ ] Implement `pipeline.py` — orchestrator with `--start-stage`/`--stop-stage`
- [ ] Run full pipeline on Docker Deep Dive end-to-end
- [ ] Run full test suite: `uv run pytest tests/test_ingest/`

**Checkpoint:** Docker Deep Dive cleanly ingested with enriched metadata. ✓

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

## Phase 3 — Reranker

*Goal: Cross-encoder second pass over hybrid results. Spec: `planning/reranker-spec.md`*

- [ ] Add dependency: `uv add sentence-transformers`
- [ ] Implement `src/dev_rag/reranker.py`
- [ ] Run reranker tests (all mocked — no model download needed):
  `uv run pytest tests/test_reranker.py`
- [ ] Add startup model load to `api.py`
- [ ] Start API and confirm model downloads and loads:
  `docker compose up -d` — watch logs for "Reranker loaded"
- [ ] Wire reranker into `/search` route — increase Stage 1 candidates to 50
- [ ] Run full test suite: `uv run pytest`
- [ ] Confirm `rag_health` MCP tool shows reranker model name

**Checkpoint:** Two-stage retrieval (hybrid + reranker) is live. ✓

---

## Phase 4 — Evaluation Harness

*Goal: Objective baseline score before any further changes.*
*Spec: `planning/dev-rag-evaluation-strategy.md`*

- [ ] Create `data/evaluation/` directory
- [ ] Implement `eval/loader.py`
- [ ] Implement `eval/runner.py`
- [ ] Implement `eval/scorer.py`
- [ ] Implement `eval/reporter.py`
- [ ] Implement `eval/run_eval.py`
- [ ] Write initial `data/evaluation/devops_questions.yaml`
  (start with the 9 questions from the evaluation strategy doc)
- [ ] Run harness for the first time: `uv run python eval/run_eval.py --domain devops`
- [ ] Save the baseline JSON — note the path printed at the end
- [ ] Record baseline scores in the table below

**Baseline scores (fill in after first run):**

| Metric | Baseline |
|--------|----------|
| Retrieval@1 | |
| Retrieval@3 | |
| MRR | |
| Chunk Match | |
| Negative Precision | |
| Composite Score | |

**Checkpoint:** Eval harness running, baseline established. ✓

---

## Phase 4b — Grow Eval Question Set

*Goal: 25 questions with `expected_source` populated before trusting --compare deltas.*
*Decision: Athens, June 2026 — minimum threshold before gating migrations.*

- [ ] After ingesting Docker Deep Dive, check which source filename appears
  in results: `search_devops("docker secrets")`
- [ ] Update `expected_source` on `devops-001` to match actual filename
- [ ] Write questions 9–25 in `devops_questions.yaml` based on real queries
  you run during Phase 1 usage — questions that arise organically are best
- [ ] Ensure at least 3 questions per category: factual, security, comparison,
  architecture, source_specific, negative, chunk_boundary
- [ ] Run harness: `uv run python eval/run_eval.py --domain devops`
- [ ] Confirm `questions_with_expected_source` ≥ 25 in aggregate output
- [ ] Save this as the **official baseline JSON** for all future `--compare` runs

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

## Phase 6 — Headroom Compression

*Goal: Token reduction on MCP server output.*
*Spec: `planning/headroom-integration-spec.md`*

- [ ] Install Headroom: `uv add headroom`
- [ ] Implement `mcp/compress.py`
- [ ] Run compress tests: `uv run pytest mcp/tests/test_compress.py`
- [ ] Add `from compress import compress_text, compression_stats` to `mcp_server.py`
- [ ] Add `compress_text()` call in `_handle_domain_search()`
- [ ] Add `compress_text()` call in `_handle_search_all()`
- [ ] Add compression stats to `_handle_health()`
- [ ] Run full MCP server tests: `uv run pytest mcp/tests/`
- [ ] Run a query from Claude Code and check `rag_health` for compression stats
- [ ] Confirm answer quality is preserved at default ratio (0.4)

**Checkpoint:** Headroom compression active, stats visible in health output. ✓

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
