# dev-rag Phase 2 — Hybrid Search (plan + Claude Code kickoff) — v1

**Date:** 2026-07-05 · **Spec:** `planning/hybrid-search-spec.md` · **Branch:** `feat/phase2-hybrid-search`

## What Phase 2 delivers
A working `/search` endpoint: dense (BGE-M3 + ChromaDB) and sparse (FTS5 BM25)
retrieval fused with RRF, behind `search_mode = dense | sparse | hybrid`.
After this phase the MCP server becomes genuinely usable from Claude Code.

## Spec vs. reality — reconciliations (the spec predates Phase 1a)

Already DONE by Phase 1a (skip spec Implementation Order steps 1–2, §4):
- Migration 002 applied; `chunks_fts` populated (311 rows, parity verified).
- Ingest writes chunks via explicit DELETE+INSERT (fires both FTS triggers).

Spec details that MUST be adapted:
1. **`rrf_score` in the response (spec §5) violates OBS-001.** `/search` emits
   canonical `relevance_score` (hard rule in CLAUDE.md). Mapping:
   hybrid → `rrf_score`; dense → cosine similarity; sparse → negated BM25.
   `rrf_score`/`dense_rank`/`sparse_rank` stay as optional debug fields
   (already in api.py's `SearchResult` model).
2. **Spec's `chroma_collection.query(query_texts=...)` won't work.** Our
   collections have no bound embedding function (Phase 1a passes embeddings
   explicitly). Dense retrieval must embed the query with BGE-M3 itself and
   call `query_embeddings=`. Model: lazy singleton, monkeypatchable in tests
   (same never-load-real-model-in-tests rule as ingest).
3. **Spec's chunks columns `source`/`version` don't exist** (they live on
   `sources` per migrations/001 — see FBL-003 correction in the 1a plan).
   `bm25_search` JOINs `chunks` → `sources` to return `source` = filename,
   and filters `chunks.status = 'active'`.
4. **Spec test fixture hand-builds its own schema** — build fixtures via
   `apply_migrations()` (real 001/002/003) instead, so tests can't drift
   from the actual schema.
5. **Spec steps 7–8 (eval baseline + --compare) are Phase 4**, not Phase 2
   (per docs/TODO.md phase list). Parked.

## Folded-in tracked items
- **FBL-001** — migration `003_fts_update_trigger.sql`: UPDATE trigger so
  content edits and `status` flips keep `chunks_fts` correct (delete + re-insert
  row; remove from FTS when `status != 'active'`). Remember: implicit deletes
  (REPLACE) don't fire triggers — test with real UPDATE statements.
- **OBS-006** — after implementation, run the spec's six ablation queries
  (`--network=host`, `COPY --chown`, BuildKit, …) in sparse vs dense vs hybrid
  on the real corpus; record results + tokenizer decision in the spec doc.
- **OBS-009** — `/health` gets real per-domain ChromaDB/SQLite counts while
  api.py is open (cheap now, was "before Phase 7").
- **CLAUDE.md rule** — end-to-end test hitting the REAL `/search` endpoint
  (TestClient + temp stores built by real migrations + injected fake embedder),
  finally proving the OBS-001/002 contract against a live producer.

## NEW FINDING to park (add to TODO as FBL-005)
The eval scorer's negative-precision check treats `relevance_score < 0.5` as
"correctly refused". RRF scores max out near `2/(60+1) ≈ 0.033`, so under
hybrid mode EVERY query scores "< 0.5" and the metric becomes meaningless.
Fix belongs in Phase 4 (per-mode thresholds or normalized scores) — do NOT
silently tune it here.

## Key design calls (decided; revisit only with a reason)
- `relevance_score` semantics are **per-mode and not comparable across modes**
  — documented in the response (`search_mode` field already present).
- Query embedder: lazy module-level singleton in `retrieve.py`, shared with
  api.py; loads once (~10 s CPU) on first search, not at startup — keeps
  tests and `uvicorn` boot fast.
- Dense/sparse candidate counts and `rrf_k` come from settings (already
  present: 20/20/60).
- `reranker_enabled` stays untouched; `/search` response's `reranker` field
  reflects settings but NO reranking happens (Phase 3). relevance_score =
  rrf_score is the documented OBS-001 fallback semantics until then.

## Build order (each stage: implement → test → inspect → commit → STOP)
0. branch + migration 003 (FBL-001) — test UPDATE/status sync; apply to real
   `data/dev_rag.db` via `apply_migrations()`; verify 311 parity intact.
1. `retrieve.py` — dense: embed query, ChromaDB query, `DenseResult` with
   `source` from Chroma metadata. Tests: temp stores + fake embedder.
2. `retrieve_sparse.py` — `bm25_search` + `_sanitise_fts_query` per spec,
   adapted: JOIN sources for filename, filter active. Tests per spec's 6
   BM25 cases (fixtures via real migrations).
3. `retrieve_hybrid.py` — `reciprocal_rank_fusion` + `hybrid_search` per
   spec §3. Spec's 6 RRF unit tests.
4. `api.py` — wire all three modes into `/search` (OBS-001 mapping above),
   real `/health` counts (OBS-009). E2E TestClient test through the real
   endpoint; all 22 mcp fixture tests must stay green untouched.
5. Manual verify on the real corpus: runbook smoke (`uvicorn` + curl for all
   three modes) + OBS-006 ablation queries; record findings.
6. Docs: RUNBOOK.md gains "start the API / query it" section; TODO.md checkboxes
   (FBL-001, OBS-006, OBS-009 → done; add FBL-005); current_context.md close.

## Done when
- [ ] `POST /search` returns real ranked results in all three modes with
      canonical `relevance_score`
- [ ] E2E test hits the real endpoint against real-migration temp stores
- [ ] migration 003 closes FBL-001 (UPDATE/status sync proven by tests)
- [ ] `/health` reports real counts (OBS-009 closed)
- [ ] ablation queries run and recorded; OBS-006 decision made
- [ ] suite green (70 existing + new); runbook updated; not pushed — review+merge is Ed's

---

## Kickoff prompt (paste into Claude Code, from repo root)

```
You are in the dev-rag repo. Create and work on a NEW branch: feat/phase2-hybrid-search.
Conventions: uv ONLY, Python 3.12. CLAUDE.md rules apply; ADRs are FINAL; canonical
relevance_score is a HARD RULE (never emit rrf_score as the primary field). Personal-scale
tool — simplest thing that works. CPU-only machine; NEVER load real BGE-M3 in tests.

GOAL: implement hybrid search per planning/hybrid-search-spec.md AS RECONCILED by
docs/plans/dev-rag-phase2-plan.md (the plan's "Spec vs. reality" section OVERRIDES the
spec where they disagree — the spec predates Phase 1a). Read both before coding.

DISCOVER FIRST: docs/plans/dev-rag-phase2-plan.md (this plan), planning/hybrid-search-spec.md,
src/dev_rag/api.py (SearchResult model), migrations/001+002, src/dev_rag/ingest/load.py
(how stores are written), docs/RUNBOOK.md (how to run things).

Work stage-by-stage per the plan's Build order: one stage at a time, write tests first,
run `uv run pytest`, print a short inspection summary, STOP and show me before the next
stage. One commit per stage. Do NOT push. Do NOT touch reranker/graph/agent/compression.
Do NOT re-ingest or re-embed the corpus. If a needed convention is missing, STOP and ask.
```
