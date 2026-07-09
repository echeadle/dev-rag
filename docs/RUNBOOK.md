# dev-rag Runbook — how to run everything

**Last verified:** 2026-07-05 (Phase 2 close). Every command in the "works
today" sections was run and verified on that date. **Update this file whenever
a phase adds or changes a runnable surface** — a runbook that drifts is worse
than none.

---

## 1. One-time setup

```bash
cd ~/Projects/coding_projects/learning/dev-rag
uv sync                    # resolves cleanly; installs CPU torch (pinned index)
```

- Python 3.12, `uv` only — never pip.
- No `.env` needed for ingest (no API keys — everything runs locally).
- First-ever embed run downloads BGE-M3 (~2.3 GB) from HuggingFace into
  `~/.cache/huggingface/` — one time, then cached. It is not a hang.

## 2. Run the tests

```bash
uv run pytest              # expect 106 passed (84 tests/ + 22 mcp/tests/)
```

Fast (~6s): tests never load the real embedding model or touch the real stores.
If only one directory's tests run, `testpaths` in `pyproject.toml` has
regressed — see CLAUDE.md.

## 3. Ingest a book (the main workflow)

Put the PDF in `data/books/`, then:

```bash
uv run python -m dev_rag.ingest.pipeline \
    --source data/books/dockerdeepdive.pdf \
    --domain devops \
    --query "How does Docker isolate containers from each other?"
```

Domains: `devops | travel | python | ai` (see `settings.py`).

`--query` must be a question **this specific book** should answer — stage 8
verifies the new book appears in the top-5 results for it. A question another
book in the domain answers better fails verify even though the data loaded
fine (this bit us on the Compose book, 2026-07-05 — the old shared default
was a Deep Dive question). Required whenever stage 8 runs; `--dry-run` and
`--stop-stage` runs that skip stage 8 don't need it.

### What happens, stage by stage

Spec stage numbers (3 and 5 are deferred LLM stages — not built yet):

| Stage | What | Artifact written | Time (280-page book, CPU) |
|---|---|---|---|
| 1 extract | PDF → markdown per page (pymupdf4llm) | `data/raw/{slug}.json` | ~1 min |
| 2 clean | drop TOC/blank/short pages; strip page numbers | `data/cleaned/{slug}_cleaned.json` | seconds |
| 4 chunk | 1500-char window, 200 overlap, word-snapped | `data/chunks/{slug}_chunks.json` | seconds |
| 6 embed | BGE-M3 dense, dim 1024, normalized | `data/embeddings/{slug}_embeddings.json` | **~14 min** (0.4 chunks/s) |
| 7 load | ChromaDB `{domain}_content` + SQLite + FTS5 | `chroma_db/`, `data/dev_rag.db` | seconds |
| 8 verify | parity check + live dense query | (prints report) | ~15 s (model load) |

`{slug}` = PDF filename, lowercased, spaces → dashes.

### Useful flags

```bash
--stop-stage 2     # stop after clean, inspect data/cleaned/ before continuing
--start-stage 7    # resume from load (reuses existing artifacts; embed not re-run)
--dry-run          # stages 1-6 only; guaranteed no ChromaDB/SQLite writes
--query "..."      # verify-stage query; required when stage 8 runs (see above)
```

The gated workflow used in Phase 1a: run `--stop-stage N`, inspect the artifact,
then `--start-stage N+1` (chunks are only re-embedded if content changed —
re-loading unchanged chunks reports `inserted 0, skipped N`).

### Ingest the same book again (idempotency)

Safe. `content_hash` matching skips unchanged chunks in both stores. A changed
PDF (new edition) re-ingests only what changed — but for books, prefer the
wholesale-replacement strategy in ADR-006 (not yet automated).

## 4. Sanity-check the corpus (store-level)

Quick verify without re-running the pipeline:

```bash
uv run python -m dev_rag.ingest.pipeline \
    --source data/books/dockerdeepdive.pdf --domain devops --start-stage 8 \
    --query "How does Docker isolate containers from each other?"
```

Expected output shape:

```
[8 verify] parity OK (311); top hit dockerdeepdive_0298 p269 dist=0.280
```

SQLite counts by hand:

```bash
sqlite3 data/dev_rag.db \
  "SELECT domain, count(*) FROM chunks WHERE status='active' GROUP BY domain;
   SELECT count(*) FROM chunks_fts;"
```

BM25 sanity query (FTS5 is populated even though hybrid search isn't built yet):

```bash
sqlite3 data/dev_rag.db \
  "SELECT chunk_id, snippet(chunks_fts, 2, '[', ']', '...', 8)
   FROM chunks_fts WHERE chunks_fts MATCH 'restart policies' LIMIT 3;"
```

## 5. Run the search API (Phase 2)

```bash
uv run uvicorn dev_rag.api:app --host 127.0.0.1 --port 8000
```

Boots instantly; BGE-M3 loads lazily on the FIRST search (~10 s), after
which queries take ~105 ms (hybrid/dense) or ~4 ms (sparse).

```bash
# health — real per-domain ChromaDB/SQLite parity (OBS-009)
curl -s http://127.0.0.1:8000/health | python3 -m json.tool

# search — search_mode: hybrid (default) | dense | sparse
curl -s -X POST http://127.0.0.1:8000/search \
  -H 'Content-Type: application/json' \
  -d '{"query": "How do restart policies work?", "domain": "devops", "n_results": 3}' \
  | python3 -m json.tool

# single-channel comparison (ablation-style): add "search_mode"
curl -s -X POST http://127.0.0.1:8000/search \
  -H 'Content-Type: application/json' \
  -d '{"query": "How do restart policies work?", "domain": "devops", "n_results": 3, "search_mode": "sparse"}' \
  | python3 -m json.tool
```

No-curl option: with the server running, open http://127.0.0.1:8000/docs —
FastAPI's auto-generated interactive docs let you fire searches from the
browser (expand POST /search → "Try it out").

`relevance_score` is the canonical ranking field. Its scale is **per-mode**
(hybrid: RRF ~0.01–0.033, or cross-encoder logit when the reranker ran ·
dense: cosine 0–1 · sparse: BM25 unbounded) — never compare scores across
modes. `dense_rank`/`sparse_rank`/`rrf_score`/`reranker_score` in hybrid
responses are debug fields; `reranker_score: null` means the reranker
didn't run for that result.

### 5b. Reranker (Phase 3 — implemented, OFF by default)

Cross-encoder reranking (bge-reranker-v2-m3) is fully wired into hybrid
mode but **disabled by default**: measured 2026-07-06 on CPU it costs
~1.5–2 s per candidate pair — ~15 s/query at 10 candidates, ~112 s at the
spec's 50 — vs ~0.15 s for RRF-only. Enable it per-run for quality A/B
or the Phase 4 eval:

```bash
RERANKER_ENABLED=true RERANKER_CANDIDATES=10 \
    uv run uvicorn dev_rag.api:app --host 127.0.0.1 --port 8000
```

Notes:
- Env names have **no `DEV_RAG_` prefix** (settings.py sets no env_prefix);
  the reranker spec's `DEV_RAG_RERANKER_ENABLED` is wrong — use
  `RERANKER_ENABLED`. (`DEV_RAG_BASE_URL` is different: that's the MCP
  server's own variable, not a pydantic setting.)
- **Phase 5b (2026-07-09): the model loads eagerly at EVERY startup now**,
  regardless of `RERANKER_ENABLED` — the server doesn't answer until
  "Reranker loaded" appears in the log, every time. First-ever startup
  still downloads the model (~2.2 GB, one-time, cached in
  `~/.cache/huggingface/`); it's needed unconditionally so the MCP
  `search_all` tool's `force_rerank` requests can use it even when
  `RERANKER_ENABLED` (the default single-domain-search behavior, ADR-012)
  is off.
- Fallback is graceful (OBS-002): if the model is missing or scoring
  fails, hybrid answers in RRF order with `reranker_score: null`.
- **FBL-006 confidence gate:** the reranker's score is a SIGMOID probability
  in (0,1). A hit below `RERANKER_MIN_SCORE` (default 0.5) is flagged
  `weak_match: true` in the /search response and annotated "⚠️ weak match"
  in the MCP output — a SOFT signal, ranking/R@k unchanged. Tune per-run,
  e.g. `RERANKER_MIN_SCORE=0.6`. `weak_match: null` means the reranker
  didn't run (confidence unknowable). Measured 2026-07-06 (5 negatives): at
  0.5, 4/5 out-of-scope queries flag weak; only devops-027 (GitLab CI) leaks.
- Revisit the ADR-012 single-domain default when Phase 4 eval quantifies
  the accuracy delta.
- **Phase 5b: `force_rerank` (per-request, independent of
  `RERANKER_ENABLED`).** `POST /search` accepts `force_rerank: true` to
  rerank one request regardless of the server-wide default — used by the
  MCP `search_all` tool for genuine cross-domain ranking (RRF scores
  aren't comparable across domains; reranker scores are). Uses a smaller
  pool (`settings.force_rerank_candidates`, default 10) than the
  operator-configured `RERANKER_CANDIDATES`, to stay in the ~20s/query
  range rather than the ~112s/query the default pool of 50 costs.
  **`search_all` costs ~20s × populated domain count** (not a flat ~20s —
  concurrent per-domain reranks were measured to serialize, not overlap,
  on this single-process CPU-bound server); `search_devops`/
  `search_python`/other single-domain tools are completely unaffected,
  still ~0.15s RRF-only by default.

## 5c. Run the evaluation harness (Phase 4)

The server must be running first (§5). Then:

```bash
uv run python eval/run_eval.py --domain devops            # run + save results
uv run python eval/run_eval.py --domain devops \
    --compare eval/baselines/2026-07-06_hybrid_rrf.json   # + delta vs baseline
uv run python eval/run_eval.py --category negative --no-save
```

- Question sets live in `data/evaluation/*_questions.yaml`; every non-null
  `expected_source` is a real ingested filename verified against chunk text
  (OBS-003). When adding questions, verify the book actually contains the
  answer (grep `data/chunks/*.json`) — mislabeled ground truth poisons
  every future comparison.
- Each run saves `eval/results/<timestamp>.json` (gitignored scratch) with
  a self-describing `config` block. Promote a run to an official baseline
  by copying it into `eval/baselines/` (tracked in git).
- The A/B workflow: run against the default server → restart the server
  with different settings (e.g. `RERANKER_ENABLED=true RERANKER_CANDIDATES=10`)
  → run again with `--compare <baseline>`.
- **Negative precision reports n/a on plain hybrid runs BY DESIGN**
  (FBL-005): RRF scores encode rank, not relevance, so "below threshold"
  is meaningless. The metric computes when the reranker is on (logit < 0)
  or in dense mode (cosine < 0.5).
- `--graph` stays gated off until `/search/graph` exists (Phase 8).

## 6. What does NOT run yet (do not trust these surfaces)

| Surface | State |
|---|---|
| `docker compose up` | Compose files predate Phase 1a and are **unverified**; everything runs directly via `uv run`, no containers needed. |
| GraphRAG / agent.py / compression | Stubs, deferred (see docs/TODO.md). |

Architecture doc §8 ("Running the System") still shows the aspirational
Docker-based commands — **this runbook supersedes it** until §8 is
rewritten against reality.

## 7. Where things live

```
data/books/        source PDFs (yours; gitignored)
data/raw|cleaned|chunks|embeddings/   stage artifacts (gitignored, regenerable)
data/dev_rag.db    SQLite: sources, chunks, chunks_fts (gitignored)
chroma_db/         ChromaDB persistence (gitignored)
~/.cache/huggingface/   model cache: BGE-M3 (~2.3 GB) + bge-reranker-v2-m3 (~2.2 GB)
```

Everything outside `data/books/` is regenerable from the PDFs; a full rebuild
of one book costs ~15 minutes (dominated by CPU embedding).
