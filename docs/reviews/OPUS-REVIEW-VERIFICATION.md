# OPUS-REVIEW re-verification against current code

**Verified by:** Claude Opus 4.8
**Date:** 2026-07-04
**Branch:** `review/opus-fixes`
**Method:** Read every file the review cites in the CURRENT tree; ran the test
suite; grepped for the exact key names / patterns each finding names. Where the
review's line references were stale, the on-disk file is treated as source of truth.

---

## TL;DR (read this before Step 2)

The codebase was **already reworked against this exact review** since 2026-06-21.
Almost every source and spec file now carries explicit `OBS-XXX` fix annotations,
and the consumers were migrated to a single canonical relevance field. Concretely:

- **11 of 12 findings are resolved or no longer apply** at the contract/consumer/
  test level. Only **OBS-006** (FTS5 tokenizer) remains open — and it is a
  *measurement/decision*, not a mechanical code edit.
- The two **High** findings (OBS-001, OBS-002) **no longer reproduce**: every
  consumer reads `relevance_score`, and the response model exposes no
  `reranker_score` field at all, so the crash vector is structurally gone.
- **All 29 tests pass** (7 in `tests/` + 22 in `mcp/tests/`).

### ⚠️ The Step 2 plan as written is based on a stale premise — do not run it verbatim

The Step 2 instruction is to revert `FAKE_RESULTS` to `rrf_score/reranker_score`
(no `score`) to force red tests, then fix consumers. **That would REGRESS working
code.** OBS-001 was already fixed the way the review itself recommended: pick one
canonical field (`relevance_score`) and update *every* producer, consumer, and
fixture to it. Reverting the fixtures would re-introduce exactly the mismatch
OBS-001 warned about.

**Recommendation:** accept the existing `relevance_score` fix. Whether you'd
prefer a different wire field name is a decision for you, not something to flip
silently. **After this pass there are essentially no clean mechanical fixes left
for Step 2** — the remaining items are documented decisions, data-dependent (need
ingestion to observe), or an investigation. That reshapes what Step 2 even is,
which is the most useful thing to hand back.

### Important caveat: "fixed at contract level" ≠ "verified working end-to-end"

`api.py`'s `/search` returns `{"results": []}` — it is a stub (line 120‑126).
`retrieve_hybrid.py`, `reranker.py`, `compress.py`, `agent.py`, `graph.py` are all
stubs. So OBS-001/002 are resolved in the **contract, consumers, fixtures, and
tests**, but the producer (retrieval → rerank → serialise) path is never exercised
at runtime yet. The fixes are correct *by construction of the contract*; they have
not been proven against a live retrieval pipeline because none exists.

### Environment note (relevant to OBS-008)

Setting up the venv with `uv` surfaced that the `compress` extra is unsatisfiable:
`pyproject.toml` pins `headroom>=0.3.0`, but only `headroom<=0.2.7` exists on the
index. `uv sync` fails to resolve. Tests were run via `uv pip install '.[dev]'`
(the `dev` extra only), which sidesteps the broken `compress` extra.

---

# PART A — FIX LIST

Severity is the review's original rating. "Reproduces now?" is the key column.

### OBS-001 — `/search` `score` vs `rrf_score`/`reranker_score` mismatch  · **High**
**Classification: ALREADY FIXED.** Reproduces now? **No.**

The fix chosen was to introduce one canonical field, `relevance_score`, and route
every consumer and fixture through it — precisely the review's own recommendation.

Evidence (current tree):
- Producer contract: `src/dev_rag/api.py:59` — `relevance_score: float  # single
  canonical field for all callers`; `rrf_score` kept only as optional debug field
  (`api.py:60`). Docstring `api.py:104‑107` states the semantics per search mode.
- MCP consumer: `mcp/mcp_server.py:90` — `score = r.get("relevance_score")`. No
  `score`/`distance` fallback remains.
- Eval consumer: `eval/scorer.py:64` — negative precision reads
  `result.results[0].get("relevance_score", 1.0)`.
- Fixtures: `mcp/tests/test_mcp_server.py:29,35,44,53` all use `relevance_score`;
  `test_format_results_relevance_score_field` (line 82) asserts `score`/`distance`
  are *not* read.
- Grep for any remaining `.get("score")` / `["score"]` / bare `rrf_score` /
  `reranker_score` **read** by a consumer: **none** (only the debug-only optional
  field and doc comments).

Minimal fix if still valid: N/A. **Do not revert fixtures per Step 2** — that
reintroduces the bug.

---

### OBS-002 — reranker fallback returns wrong type, crashes degraded path  · **High**
**Classification: ALREADY FIXED (contract) / NO LONGER APPLIES (runtime).**
Reproduces now? **No.**

Two independent reasons it cannot crash as described:
1. **Structural:** the response model `SearchResult` (`api.py:54‑63`) exposes only
   `relevance_score` (+ optional `rrf_score`) and has **no `reranker_score` field
   at all**. The original crash vector was serialising `r.reranker_score` on a
   `HybridResult`; that field is gone from the contract, so it cannot be accessed.
2. **Spec:** `planning/reranker-spec.md` now defines `rerank_with_fallback` to map
   `HybridResult → RankedResult` with `reranker_score=None` via `_wrap_as_ranked`
   (spec lines ~204‑242), and its fallback tests assert
   `isinstance(results[0], RankedResult)` (spec lines ~490‑504).

Runtime note: `src/dev_rag/reranker.py` is a 6-line stub (no `rerank_with_fallback`
implemented), and there is no `test_reranker.py` in the tree — so the buggy runtime
code the review saw no longer exists. `api.py:109‑117` documents the correct
contract for whoever implements Stage 2.

Minimal fix if still valid: N/A. Ensure the eventual implementation follows the
spec's `_wrap_as_ranked` pattern.

---

### OBS-003 — every shipped question has `expected_source: null`  · **Medium**
**Classification: PARTIALLY VALID (largely addressed).** Reproduces now? **Partially.**

Two mitigations were added:
- `eval/scorer.py:97‑103` — the composite is no longer all-or-nothing; it now
  computes when **≥2** of `{r3, mrr, cm, neg}` are present (`if len(non_none) >= 2`)
  and reweights. `scorer.py:118‑122` also surfaces
  `questions_with_expected_source`.
- `data/evaluation/devops_questions.yaml` now sets `expected_source` on the two
  source-specific questions: devops-006 (`:74`) and devops-021 (`:389`), both
  `"docker-deep-dive.pdf"`.

Remaining gap: the value `"docker-deep-dive.pdf"` is a **placeholder** — it must
match the actual ingested filename, and it can only be validated *after ingestion*.
Every other (factual/comparison/etc.) question is still `expected_source: null`, so
Retrieval@k/MRR will still be sparse on the first run. This is data-dependent, not a
code edit.

Minimal fix if still valid: after ingestion, populate real `expected_source`
filenames on the source-specific + a handful of factual questions. Not actionable
now (no corpus ingested).

---

### OBS-004 — eval runner hits `/search/graph` and posts `domain: None`  · **Medium**
**Classification: ALREADY FIXED.** Reproduces now? **No.**

- `eval/runner.py:14‑17` defines `GRAPH_ENDPOINT_AVAILABLE = False` and
  `CROSS_DOMAIN_ENDPOINT_AVAILABLE = False`.
- Graph lift is gated: `runner.py:56` only calls `/search/graph` when
  `... and GRAPH_ENDPOINT_AVAILABLE`.
- Cross-domain no longer posts `domain=None`; `runner.py:37‑43` routes
  `cross_domain` questions through `_run_cross_domain` fan-out (`runner.py:69‑96`),
  which posts a valid `domain` per request.

Minor observations (not blocking, optional cleanup):
- `CROSS_DOMAIN_ENDPOINT_AVAILABLE` is defined but never read — the fan-out always
  runs for `cross_domain`. Dead flag.
- `_run_cross_domain` fans out to `["devops","travel","python"]` (`runner.py:76`),
  omitting `"ai"`, which *is* in `settings.valid_domains`. Same omission exists in
  `data/evaluation` domain coverage. Cosmetic mismatch, not a crash.

---

### OBS-005 — a test lost its `def` header; two scenarios fused  · **Low**
**Classification: ALREADY FIXED.** Reproduces now? **No.**

`mcp/tests/test_mcp_server.py:243` — `test_search_all_fanout_on_500` now has its own
`def` header and runs as an independent test. Both it and
`test_search_all_fanout_three_domains` (line 215) are collected and pass (part of
the 22 MCP tests).

---

### OBS-006 — FTS5 `porter ascii` tokenizer undercuts exact-token premise  · **Medium**
**Classification: STILL VALID (open).** Reproduces now? **Cannot yet observe (no data).**

`migrations/002_add_fts5.sql:8` is unchanged: `tokenize = 'porter ascii'`. Porter
stemming + default punctuation split still means `--network=host` indexes as
`network`/`host`, and identifiers get stemmed — so the "perfect flag-level
precision" claim in `hybrid-search-spec.md` is still overstated.

**This is not a mechanical Step 2 fix.** The review's own recommendation is to run
the planned ablation queries against ingested data and *then* decide whether to move
to `unicode61` with custom `tokenchars` (or an unstemmed identifier column). With no
corpus ingested, there is nothing to measure yet. Treat as a measurement/decision
item, not a code edit — do not invent a tokenizer change blind.

---

### OBS-007 — sliding-window chunker vs the chunk_boundary eval  · **Medium**
**Classification: ADDRESSED (decision documented).** Reproduces now? **N/A (by design).**

The review's actual ask was "decide now whether structure-aware chunking is in
scope." That decision now exists in two places:
- `src/dev_rag/ingest.py:20‑31` — explicit docstring: structure-aware chunking is
  "OUT OF SCOPE for the initial implementation," with a documented fallback plan
  (increase chunk_size/overlap first).
- `planning/ingest-pipeline-spec.md` (header) — a full structure-aware ingest spec
  marked "Ready to implement — replaces ingest.py stub / Supersedes the basic
  sliding-window chunker."

Note a mild tension: `ingest.py`'s docstring says structure-aware is out of scope,
while the spec presents semantic chunking as the ready replacement. Both point the
same direction; just be aware which one is authoritative when Phase 1 is built.
See PART B for the "is this the real first-build spec?" question.

---

### OBS-008 — Headroom integration fully mocked, API surface unverified  · **Medium**
**Classification: NO LONGER APPLIES to current code / spec risk remains.**
Reproduces now? **No (the mocked tests are gone).**

- `mcp/compress.py` is now a trivial stub (`compress_text` returns text unchanged;
  `compression_stats` returns `{"enabled": False, ...}`). There is **no
  `test_compress.py`** in the tree — so "all ten tests mock the surface" no longer
  describes current code.
- The assumed API still lives only in `planning/headroom-integration-spec.md`, and
  **the assumed version is provably not installable**: `pyproject.toml` pins
  `headroom>=0.3.0`, but only `headroom<=0.2.7` exists (uv resolution fails). This
  is concrete new evidence reinforcing the review's core worry — the integration is
  written against an API/version that does not currently exist.

Minimal fix if still valid: the review's recommendation (un-mocked smoke test before
Phase 6) stands for the future; additionally reconcile the `headroom>=0.3.0` pin
with reality (0.2.7) before Phase 6. Not actionable now (library unavailable).

---

### OBS-009 — ChromaDB/SQLite drift with no detector before pgvector  · **Medium**
**Classification: ALREADY FIXED (structure); counts stubbed.** Reproduces now? **No.**

- `src/dev_rag/api.py:69‑96` — `/health` now returns a `store_parity` block per
  domain (`chroma_chunks` vs `sqlite_chunks`, `in_sync`) plus a top-level
  `stores_in_sync`, and reports `status: degraded` when they disagree.
- `mcp/mcp_server.py:448‑459` — `rag_health` surfaces `/health` output to the user.

Caveat: the parity counts are TODO stubs (`api.py:78‑79` both hardcoded `0`), so it
always reports in-sync until real collection/`chunks`-table queries are wired in.
The drift-detection *seam* the review asked for exists; it needs real counts.

---

### OBS-010 — deprecated `@app.on_event("startup")` for reranker load  · **Low**
**Classification: ALREADY FIXED.** Reproduces now? **No.**

`src/dev_rag/api.py:23‑33` — startup now uses an `@asynccontextmanager` `lifespan`
handler passed to `FastAPI(..., lifespan=lifespan)`. No `on_event` anywhere (grep
confirms only doc comments reference the old name). The model load is still a TODO
inside the lifespan (`api.py:26‑27`), but the pattern is correct.

---

### OBS-011 — pgvector CVE / image tag asserted but not pinned  · **Low**
**Classification: ALREADY FIXED.** Reproduces now? **No.**

`planning/pgvector-migration-spec.md` now pins a concrete tag:
`pgvector/pgvector:pg16-0.8.2` (security note ~line 65 and compose block line 452,
annotated `OBS-011: pinned — never use floating :pg16 tag`), cites the CVE affecting
0.6.0–0.8.1, and instructs "0.8.2 or later." The exact image tag now appears in the
spec.

Not independently verified here: whether CVE-2026-3172 resolves to this exact
description (would require an external CVE lookup; out of scope for a code re-verify).

---

### OBS-012 — `settings.py` uses Pydantic v1 `class Config` under v2  · **Low**
**Classification: ALREADY FIXED.** Reproduces now? **No.**

`src/dev_rag/settings.py:14‑18` — uses
`model_config = SettingsConfigDict(env_file=".env", ...)`. No inner `class Config`
remains (grep confirms only doc comments mention the old form).

---

## PART A — process gap worth flagging

`pyproject.toml:36` sets `testpaths = ["tests"]`, so a bare `pytest` collects only
the **7** tests in `tests/`. The **22** MCP tests in `mcp/tests/` — including every
`relevance_score` fixture/consumer alignment test that guards OBS-001 — are **not
run by default**; you must invoke `pytest mcp/tests` explicitly. That means the
tests protecting the two High findings are outside the default gate. Consider adding
`mcp/tests` to `testpaths` (a one-line change — noted, not done, since Step 1 is
report-only).

---

# PART B — PLANNING-GAP STATUS (informational only; NOT a Step 2 queue)

### B1 — Is `planning/ingest-pipeline-spec.md` the real first-build ingestion spec?
**Status: Yes, it presents itself as authoritative.** Its header declares
`Status: Ready to implement — replaces ingest.py stub` and
`Supersedes: The basic sliding-window chunker in src/dev_rag/ingest.py`
(`planning/ingest-pipeline-spec.md:1‑6`). It is a 36 KB structure-aware pipeline
(noise removal, semantic chunking, metadata enrichment). Tension to resolve later:
`src/dev_rag/ingest.py:20‑31` documents structure-aware chunking as *out of scope*
for the initial build, while this spec is the ready replacement — the two disagree
on sequencing. (Handle in a later session.)

### B2 — Is there a GraphRAG spec for `src/dev_rag/graph.py` + `graph_db/`?
**Status: No.** `planning/` contains specs for evaluation, headroom, hybrid-search,
ingest-pipeline, pgvector, and reranker — but **no graph/GraphRAG spec**.
`src/dev_rag/graph.py:1‑6` is a stub (`TODO: implement GraphRAG using NetworkX`).
`graph_db/` contains only `.gitkeep` (empty). `/search/graph` is undefined in
`api.py` and explicitly gated off in `eval/runner.py:15`. This matches the review's
Open Question "Is GraphRAG actually on the build path?" — every artifact assumes it
(ADR-005, `graph.py`, `requires_graph` questions, graph-lift metric) but no spec
exists. (Handle in a later session.)

### B3 — Is `src/dev_rag/agent.py` wired into the request path, or a placeholder?
**Status: Placeholder.** `src/dev_rag/agent.py:1‑5` is a 5-line stub
(`TODO: implement Pydantic AI agent with search_corpus and search_graph tools`).
It is imported nowhere: the request path is `mcp/mcp_server.py` → HTTP → `api.py`
routes; nothing references `agent.py`. It is not on the live path. (Handle in a
later session.)

---

## Test evidence

```
$ python -m pytest -q                # testpaths = ["tests"]
7 passed

$ python -m pytest mcp/tests -q      # not collected by default
22 passed
```
Environment: `uv venv --python 3.12` + `uv pip install '.[dev]'` (the `compress`
extra is unsatisfiable — see the environment note above).
