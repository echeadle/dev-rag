# dev-rag Project Review — Claude Fable 5

**Date:** 2026-07-05
**Scope:** Full read of DEV-RAG-ARCHITECTURE.md, all planning/ specs, migrations,
src/dev_rag/, mcp/, eval/, docs/TODO.md, IMPLEMENTATION-ORDER.md, and the Phase 1a
plan. Reviewed mid-Phase-1a (Stage 1 extract committed on `feat/phase1a-ingest`).
**Requested by:** Ed, before proceeding to Stage 2 (clean).

---

## Overall verdict

An unusually well-run learning project. The decision discipline (ADRs, peer
review, thin-slice scoping) is better than most professional codebases. The main
risk is not quality — it is that **documentation has grown much faster than
code** (~6,000 lines of planning docs over ~200 lines of real implementation),
and that gap is already producing visible drift.

**No changes are needed before continuing Phase 1a.** Everything found below
lives in Phase 2+ territory and is tracked as FBL-001…004 in `docs/TODO.md`.

---

## Strengths

1. **Decision hygiene.** Every non-obvious choice is recorded with alternatives
   and reasoning (ADR-001…013). Six months from now the *why* behind ChromaDB,
   BGE-M3, and dense-only 1a will still be recoverable. This is the single most
   valuable habit in the project — keep it.

2. **Thin-slice scoping.** Deferring LLM structure/enrichment to Phase 1b and
   building extract → clean → chunk → embed → load → verify first is exactly
   right. It produces a queryable corpus fast, and the eval harness can then
   *prove* whether enrichment earns its cost rather than assuming it.

3. **Contract-first with honest labeling.** `relevance_score` canonicalization
   (OBS-001), fallback returning `RankedResult` (OBS-002), and CLAUDE.md openly
   stating that contract guarantees are "correct by construction, not yet
   proven" — that honesty prevents trusting fixture-tested stubs.

4. **Forward-compatible storage.** Migration 002's FTS5 trigger auto-populates
   `chunks_fts` on insert, so Phase 2 hybrid search needs **no re-ingest**.
   Small decision, big payoff.

5. **Personal-scale realism.** CPU-pinned torch, SQLite + in-process Chroma,
   graceful degradation instead of 500s, no enterprise patterns. The
   architecture matches the actual deployment: one user, one laptop.

---

## Weaknesses (ranked by concern)

### 1. FBL-001 — `chunks_fts` goes stale under the project's own update strategy

`migrations/002_add_fts5.sql` defines INSERT and DELETE triggers but **no UPDATE
trigger**. ADR-006 Strategy B (incremental upsert for living sources) does two
things that are both SQL `UPDATE`s:

- rewrites `content` on chunks whose hash changed → FTS keeps the *old* text
- marks vanished chunks `status = 'deleted'` → they stay searchable in BM25 forever

Harmless in Phase 1a (insert-only, one book). Becomes a real bug at Phase 2 +
first URL/living source.

**Fix:** new `003` migration at Phase 2 start with an UPDATE trigger (delete +
re-insert the FTS row; skip or remove rows where `status != 'active'`). The FTS
index is rebuildable without re-embedding, so this is cheap whenever it lands.

### 2. FBL-002 — eval scorer matches `expected_source` inconsistently

In `eval/scorer.py`, Retrieval@k uses **exact list membership**
(`q.expected_source in sources[:3]`) while MRR uses **substring matching**
(`if q.expected_source in source`). If `/search` returns full paths
(`data/books/docker-deep-dive.pdf`) while questions carry bare filenames, MRR
scores hits that Retrieval@k misses — the composite metric quietly disagrees
with itself.

**Fix:** pick one rule (recommend: exact match on the ingested filename) when
populating `expected_source` in Phase 4b — OBS-003 already forces touching every
question then. Decide what `/search` emits as `source` (filename, not path) as
part of the Phase 2 storage-to-API mapping.

### 3. FBL-003 — doc drift is already visible

Concrete instances found:

| Where | Drift |
|---|---|
| `DEV-RAG-ARCHITECTURE.md` | ADR-010's text appears **twice** — an orphaned copy (no header) sits above the real ADR-010 section |
| `CLAUDE.md` | "expect 29 passed" — suite is now 32 (retiring `ingest.py` removed 4 tests, scaffold+extract added 7) |
| `IMPLEMENTATION-ORDER.md` | still describes Phase 1a as "extract, clean, structure, chunk, enrich" — structure+enrich are deferred to 1b |
| `docs/plans/dev-rag-phase1a-plan.md` | lists `source`/`version` as `chunks` columns; migration 001 puts them on `sources` (the kickoff prompt correctly names 001 as authoritative, but the contradiction stands) |

None is dangerous alone; the pattern is the warning. With five overlapping
planning docs, every decision must be updated in several places, and it isn't
happening reliably.

**Fix:** one `docs:` cleanup commit at the end of Phase 1a covering all four.
Longer term, consider a rule: *specs are frozen once their phase ships; only
ADRs and TODO.md stay living.* That caps the number of documents that can drift.

### 4. FBL-004 — Stage 5 enrichment cost is unbudgeted

The ingest spec calls Claude per chunk for summaries, keywords, and 3 synthetic
questions. Docker Deep Dive alone will likely produce 400–700 chunks; the corpus
candidate list is 6+ books. This is the project's first real API spend and it is
currently uncosted — which conflicts with the household cost-watching rule.

**Fix:** after Phase 1a lands, use the *real* chunk count to estimate 1b cost
(chunks × tokens-per-call × price) before green-lighting enrichment. Let the
eval harness confirm enrichment earns its cost (compare 1a baseline vs 1b on the
same questions) — that comparison is exactly what the harness is for.

### 5. `/health` currently lies (known — OBS-009)

Hardcoded zero counts mean `store_parity` always reports `in_sync: true`,
`status: "ok"`. Already tracked; restated here because it is easy to forget that
`/health` is decorative until wired. Guard against the spec's Stage 8 verify
(which trusts `/health` parity) creeping in — the Phase 1a plan's store-level
verify is the correct override.

---

## Recommendations summary

| # | Action | When |
|---|---|---|
| 1 | Proceed with Phase 1a Stages 2–8 as planned — nothing blocks | Now |
| 2 | FBL-001: FTS UPDATE trigger via `003` migration | Phase 2 start |
| 3 | FBL-002: unify scorer source-matching; define `source` field as filename | Phase 4b (decide field at Phase 2) |
| 4 | FBL-003: doc-drift cleanup, one `docs:` commit | End of Phase 1a |
| 5 | FBL-004: enrichment cost estimate from real 1a chunk count | Before Phase 1b |
| 6 | Consider "specs freeze once shipped; only ADRs + TODO stay living" | Whenever convenient |
