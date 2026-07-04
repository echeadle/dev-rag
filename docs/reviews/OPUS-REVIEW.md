# dev-rag Architecture Review
**Reviewed by:** Claude Opus 4.8
**Date:** 2026-06-21
**Scope:** Architecture, planning documents, and scaffold code

---

## Summary

dev-rag is a well-reasoned personal RAG system whose planning is unusually disciplined for its scale — the ADRs record genuine alternatives and rejection reasons, and the whole project is organised around a measure-the-delta philosophy that an eval harness is built to serve. The strongest risks are not in the architecture but in a set of concrete contract mismatches between the `/search` response shape and the code that consumes it, which are currently hidden by mocked tests. None of these require reversing a decision; they are gaps to close before the eval harness is trusted to gate the planned component swaps.

---

## Observations

### OBS-001: `/search` returns `rrf_score`/`reranker_score`, but consumers read `score`
**Severity:** High
**Area:** Retrieval / Eval / MCP
**Observation:** The hybrid and reranker specs define the `/search` response with `rrf_score` and `reranker_score` fields and no generic `score`. Three consumers instead read a `score` key: `mcp_server._format_results()` (`r.get("score") or r.get("distance")`), and the eval scorer's negative-precision check (`result.results[0].get("score", 1.0) < 0.5`). The MCP test fixtures (`FAKE_RESULTS`) supply a `score` key, so the tests pass while masking the mismatch against real output.
**Recommendation:** Pick one canonical relevance field for the `/search` response and update every consumer and test fixture to match it (rather than leaving producer and consumers on different key names).
**Reference:** `reranker-spec.md` §3 route; `mcp/mcp_server.py` `_format_results()`; `dev-rag-evaluation-strategy.md` `scorer.py`; `test_mcp_server.py` `FAKE_RESULTS`

### OBS-002: `rerank_with_fallback` returns a different type than the success path
**Severity:** High
**Area:** Retrieval
**Observation:** `rerank()` returns `RankedResult` objects (which carry `reranker_score`); the fallback paths return `candidates[:top_n]`, which are `HybridResult` objects with no `reranker_score`. The `/search` route then serialises `r.reranker_score` for every result, so an `AttributeError` is raised in exactly the degraded conditions (reranker unloaded or OOM) the fallback was written to survive. The reranker tests only assert `len()` and `chunk_id`, so this never surfaces.
**Recommendation:** Make the fallback map each `HybridResult` to a `RankedResult` with `reranker_score=None` so the response shape is uniform whether or not the reranker ran.
**Reference:** `reranker-spec.md` §1 `rerank_with_fallback`, §3 route serialisation; `test_reranker.py` fallback tests

### OBS-003: With `expected_source: null` on every shipped question, the headline metrics never populate
**Severity:** Medium
**Area:** Eval
**Observation:** `scorer.py` only computes Retrieval@1/@3/@5, MRR, and source precision when `expected_source` is set. All eight questions in the committed `devops_questions.yaml` — including the `source_specific` one (devops-006) — have `expected_source: null`. Because `compute_aggregate_metrics` only emits a composite when *all* component metrics are non-None, the first real run produces a `None` composite and empty retrieval numbers, undermining the `--compare` delta workflow that is the harness's entire purpose.
**Recommendation:** Populate concrete `expected_source` filenames on the source-specific question and a handful of factual questions before the first baseline run, so Retrieval@k, MRR, and the composite actually compute.
**Reference:** `data/evaluation/devops_questions.yaml`; `dev-rag-evaluation-strategy.md` `scorer.py` `compute_aggregate_metrics`

### OBS-004: Eval runner targets a `/search/graph` route and a null domain that the API does not support
**Severity:** Medium
**Area:** Eval
**Observation:** `runner.py` posts `domain: None` for `cross_domain` questions, but `SearchRequest.domain` has no default and the route immediately calls `get_collection(request.domain)` — so cross-domain questions will error. It also posts to `/search/graph` to compute graph lift, but no graph endpoint is defined in `api.py` or any planning spec, so `graph_lift` can never be produced.
**Recommendation:** Decide explicitly whether cross-domain and graph scoring are in scope for the first harness; if not, gate those code paths off rather than leaving runner calls that target unimplemented routes.
**Reference:** `dev-rag-evaluation-strategy.md` `runner.py`; `api.py` `/search`

### OBS-005: A test lost its `def` header and two scenarios are now fused into one
**Severity:** Low
**Area:** Testing
**Observation:** `test_search_all_fanout_three_domains` ends with its assertions, then contains a second docstring (`"""Unified /search 500 → fan-out…"""`) followed by a complete second test body — new `call_count`, `side_effect`, mock, call, and assertion — with no `def` line. The 500-fallback scenario therefore runs as trailing code of the three-domain test and is never reported as its own pass/fail.
**Recommendation:** Restore the missing `def test_search_all_fanout_on_500(...)` header so the 500-fallback case is an independent test again.
**Reference:** `mcp/tests/test_mcp_server.py`, `test_search_all_fanout_three_domains`

### OBS-006: FTS5 `porter ascii` tokenizer undercuts the exact-token premise of hybrid search
**Severity:** Medium
**Area:** Retrieval
**Observation:** The hybrid-search rationale rests on BM25 catching exact tokens like `--network=host`, `COPY --chown`, and `containerd` "with perfect precision." But `tokenize='porter ascii'` applies Porter stemming and the default punctuation split, so `--network=host` is indexed as `network`/`host` (flag syntax dropped) and identifiers get stemmed. The promised flag-level precision is weaker than stated.
**Recommendation:** Run the planned ablation queries and confirm flag-level matches actually surface; if they don't, evaluate a `unicode61` tokenizer with custom `tokenchars` (or an unstemmed identifier column) before relying on BM25 for exact-syntax recall.
**Reference:** `hybrid-search-spec.md` "Why Hybrid Search" + §1 schema; `migrations/002_add_fts5.sql`

### OBS-007: The sliding-window chunker is the exact weakness the chunk_boundary eval is built to expose, with no structure-aware plan
**Severity:** Medium
**Area:** Ingest
**Observation:** `ingest.py chunk_text()` is a fixed 1000-char / 100-overlap window with no awareness of code fences or procedure steps. Eval question devops-008 (`chunk_boundary`, expecting `docker network create` steps intact) is designed to fail precisely when a procedure is split mid-sequence, and the Headroom spec even refers to "the sliding-window chunker." Yet no roadmap phase introduces structure-aware chunking.
**Recommendation:** Decide now whether structure-aware chunking is in scope or an explicit non-goal, so the predictable chunk_boundary failures around the 25-question mark are an expected result rather than a surprise.
**Reference:** `src/dev_rag/ingest.py` `chunk_text`; `devops_questions.yaml` devops-008; `headroom-integration-spec.md`

### OBS-008: Headroom integration is fully mocked, so the assumed API surface is unverified
**Severity:** Medium
**Area:** Integration
**Observation:** `compress.py` assumes a specific Headroom API (`CompressionConfig(target_ratio=, use_ccr=, preserve_code_blocks=, preserve_cli_flags=)`, `compressor.compress().original_tokens/.text`, `compressor.session_stats()`). All ten tests mock this surface, so they would pass even if the real library's API differs entirely — there is zero signal that the integration matches reality, and the headline 60–95% / 95%-accuracy figures and attribution are stated without a source.
**Recommendation:** Before Phase 6, add a single un-mocked smoke test against the actually-installed Headroom to confirm the assumed constructor and result attributes exist.
**Reference:** `headroom-integration-spec.md` `compress.py` and `test_compress.py`; ADR-009

### OBS-009: ChromaDB + SQLite can drift out of sync, with no detector until pgvector lands
**Severity:** Medium
**Area:** Ingest / Reliability
**Observation:** The pgvector spec correctly notes that the two-store design "can drift out of sync if a write fails mid-ingest." That risk is real for the entire ChromaDB era (Phases 1–6): if the Chroma write succeeds and the SQLite/FTS5 insert fails (or vice versa), dense and sparse indexes silently disagree and RRF results degrade with no signal. ACID only arrives at Phase 7.
**Recommendation:** Add a cheap per-domain parity check (chunk count in the `chunks` table vs the Chroma collection) to `rag_health` or `list_collections` so drift is at least visible before the pgvector migration.
**Reference:** `pgvector-migration-spec.md` "Why Migrate" §3; `ingest.py`; `mcp_server.py` `_handle_health`

### OBS-010: FastAPI `@app.on_event("startup")` is a deprecated pattern for the reranker load
**Severity:** Low
**Area:** Documentation / API
**Observation:** The reranker is correctly loaded once at startup, but via `@app.on_event("startup")`, which current FastAPI deprecates in favour of a `lifespan` context manager. Because the model load is mandatory and slow, building it on the deprecated hook is worth correcting before more startup logic accretes there.
**Recommendation:** Specify the startup model load via a `lifespan=` handler on the `FastAPI(...)` constructor instead of the `on_event` decorator.
**Reference:** `reranker-spec.md` §3 startup; ADR-012

### OBS-011: pgvector CVE reference and "fixed" image tag are asserted but not pinned
**Severity:** Low
**Area:** Security
**Observation:** The spec cites CVE-2026-3172 affecting pgvector 0.6.0–0.8.1 and says "the Docker image in this spec pins to a version that includes the fix," but no concrete image tag appears anywhere in the spec. Pinning ≥0.8.2 is the right instinct; the evidence for it is incomplete.
**Recommendation:** Put the exact pinned Postgres/pgvector image tag in the spec and verify the CVE identifier resolves before treating the note as authoritative.
**Reference:** `pgvector-migration-spec.md` "Security Note"; ADR-003 pgvector security note

### OBS-012: settings.py uses the Pydantic v1 `class Config` style under a Pydantic v2 stack
**Severity:** Low
**Area:** Documentation
**Observation:** The stack is Pydantic / pydantic-settings v2, but `Settings` configures env loading via the v1-era `class Config:` inner class. It works today through a compatibility shim but is the deprecated form and will emit warnings.
**Recommendation:** Move env-file configuration to `model_config = SettingsConfigDict(...)` to match the v2 stack the project has standardised on.
**Reference:** `src/dev_rag/settings.py`

---

## What Is Well-Designed

- **RRF fusion is implemented correctly on the property that matters:** it fuses on rank only (not raw score), keeps documents that appear in just one list, and has unit tests for both the both-empty and single-source-empty cases. The "ranks are comparable, scores are not" reasoning is stated and then actually honoured in code.
- **Graceful degradation is a consistent, deliberate theme** — reranker → RRF order, Headroom → original text, MCP unified endpoint → per-domain fan-out, FTS5 syntax error → sanitised query. For a single-user local tool, "degraded but answering" over "crashed" is the right default and it's applied everywhere (the type bug in OBS-002 is an implementation slip, not a philosophy problem).
- **The reranker-loaded-once-at-startup decision is explicitly called out** as the key performance choice, with a realistic latency table that drives the `reranker_candidates` setting rather than leaving it arbitrary.
- **The ADRs record real alternatives and rejection reasons** (BGE-M3 vs voyage-code-2/Qwen3-8B; NetworkX vs Neo4j; ChromaDB-first-then-pgvector), and the build-and-swap-then-measure-the-delta discipline — with an eval harness existing specifically to make those swaps evidence-based — is rare and valuable at this scale.
- **`HybridResult` field-name parity between the ChromaDB and pgvector implementations** is a thoughtful seam: it lets the reranker and API layer stay untouched across the Phase 7 backend swap, which is the whole point of the build-and-swap approach.
- **Eval questions are designed around "what failure mode does this expose,"** not just collected as Q&A. The negative/no-answer, adversarial-paraphrase, and chunk-boundary categories show a real grasp of where RAG actually breaks.
- **Test ergonomics are good:** respx mocks the HTTP layer so MCP tests need no live server, and reranker/compress tests are fully mocked so they run without multi-hundred-MB model downloads. (The flip side is OBS-008's blind spot, but the ergonomic intent is sound.)

---

## Open Questions

- **Cross-domain `search_all` ranking.** The unified `/search` path and the per-domain fan-out path produce different orderings, and true reranked cross-domain ranking is marked "future." Which is the intended default once the reranker is live, and does the `n // 3` fan-out under-fetch when one domain is much larger than the others?
- **Harness timing vs. the swaps it is meant to gate.** The evaluation strategy says not to write questions until the system works and that the set becomes "genuinely valuable around 50 questions," yet IMPLEMENTATION-ORDER places the harness at Phase 4 with ~9 seed questions, before the Python domain, Headroom, and pgvector — each validated by `--compare` deltas. With fewer than ten questions (and currently null `expected_source`), those deltas won't be meaningful. When does the set actually reach 50, relative to the migrations it is supposed to gate?
- **`requires_multi_source` and `requires_graph` are recorded but not scored.** The scorer doesn't appear to consume either flag (no multi-source coverage metric). Are they aspirational metadata, or intended to drive metrics that aren't built yet?
- **Is GraphRAG actually on the build path?** ADR-005, the file structure (`graph.py`, `agent.py`), the `requires_graph` questions, and the graph-lift metric all assume it — but unlike every other component, there is no planning spec for graph build/query, and `/search/graph` is undefined. Is the graph in scope for the current implementation pass, or deferred?
