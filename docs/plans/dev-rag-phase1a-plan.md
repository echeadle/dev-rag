# dev-rag Phase 1a — Thin-Slice Ingest (plan + Claude Code kickoff) — v3 (CPU torch pinned)

## Decision recap
- **OBS-007:** spec wins. `ingest.py` sliding-window stub retired.
- **Scope:** THIN VERTICAL SLICE — local PDF -> retrievable dense chunks.
  Build Extract -> Clean(basic) -> Chunk(simple) -> Embed -> Load -> Verify.
  **Defer to 1b:** Stage 3 (LLM structure), Stage 5 (LLM enrich), URL/html2text, /search & /health.
- **First ingest:** Docker Deep Dive, local PDF in `data/books/`.
- **Machine:** System76 Darter Pro — **CPU only, no GPU.**

## Embedding — SETTLED
- Library: **sentence-transformers** (`SentenceTransformer("BAAI/bge-m3")`), **dense only**
  (sparse channel is FTS5/BM25 per hybrid-search-spec.md — no FlagEmbedding). dim **1024**.
- Device: **auto-detect** (`"cuda" if torch.cuda.is_available() else "cpu"`) — resolves to CPU
  here, but keeps the code portable.

## torch — CPU build (no GPU on this machine)
Pin CPU torch project-wide (the Phase-3 reranker uses torch too). Requires uv >= 0.5.3.
Add to `pyproject.toml` BEFORE any `uv add` (else uv pulls the ~2GB CUDA wheel, then discards it):

```toml
[[tool.uv.index]]
name = "pytorch-cpu"
url = "https://download.pytorch.org/whl/cpu"
explicit = true

[tool.uv.sources]
torch = [{ index = "pytorch-cpu" }]
```

Then `uv add torch sentence-transformers pymupdf`. Verify:
`uv run python -c "import torch; print(torch.__version__, torch.cuda.is_available())"`
-> expect a `+cpu` version and `False`.

## CPU consequences (design-relevant)
- Bulk ingest embedding is slow-but-fine (occasional, offline). Batch sensibly.
- First real embed downloads BGE-M3 (~2GB) from HuggingFace and caches it — one-time; not a hang.
- **The embed TEST must MOCK the model** — never load real BGE-M3 in `uv run pytest`.

## Storage contract — Load DEFINES it (retrieve.py is an empty stub; nothing to match)
- Chroma `./chroma_db`; collection **`{domain}_content`** (e.g. `devops_content`).
- SQLite **`data/dev_rag.db`**; `chunks` columns (per specs):
  `chunk_id, source_id, domain, source, page_number, content, content_hash, version, status, ingest_timestamp`.
- Chroma per-chunk metadata >= `source, domain, page_number, chunk_id`.
- **Apply migrations 001 + 002** at Load; 002's trigger auto-populates `chunks_fts` on insert ->
  hybrid-ready, NO re-ingest in Phase 2. (Requires `chunks.content` — verify in 001; the FTS
  trigger references `new.content`.) Idempotency via `content_hash`.

## Key design calls
1. **Verify is STORE-LEVEL, not API-level** (/search stub, /health parity = OBS-009 deferred):
   count parity + a direct ChromaDB query returning Docker Deep Dive chunks.
2. **Chunk consumes CLEANED text, not sections** (Stage 3 deferred). devops-008 may FAIL — that's
   the OBS-007 signal, not a bug.
3. **Load defines the storage contract** from the specs.

## Parked for Phase 2 (don't touch in 1a)
- Naming: spec's `rrf_score`/`score` vs code's canonical `relevance_score` (OBS-001).
- OBS-006 `porter ascii` tokenizer flag caveat (FTS index rebuildable later WITHOUT re-embedding).

## Phase-boundary note (optional, non-blocking)
This vertical slice defers structure+enrich; IMPLEMENTATION-ORDER's "1a = all prep stages" should
be relabeled 1a/1b when convenient.

## .gitignore preflight
Ignore before running: `data/raw/`, `data/cleaned/`, `data/chunks/`. Keep `data/evaluation/*.yaml`
TRACKED. (`data/dev_rag.db` covered by `*.db`.)

## Build order (each stage: implement -> test -> inspect -> commit -> STOP)
0 scaffold+deps · 1 extract(PDF) · 2 clean(basic) · 3 chunk(simple) · 4 embed(BGE-M3 dense) ·
5 load(Chroma+SQLite+migrations) · 6 verify(store-level) · 7 pipeline orchestrator.

---

## Kickoff prompt (paste into Claude Code, from repo root)

```
You are in the dev-rag repo. Create and work on a NEW branch: feat/phase1a-ingest.
Conventions: uv ONLY (never pip), Python 3.12. See CLAUDE.md; ADRs in DEV-RAG-ARCHITECTURE.md
are FINAL. Personal-scale tool — simplest thing that works, no enterprise patterns. This machine
is CPU-ONLY (no GPU).

GOAL: a THIN VERTICAL SLICE of planning/ingest-pipeline-spec.md taking a local PDF (Docker Deep
Dive, in data/books/) to retrievable DENSE chunks in ChromaDB + SQLite. Stages: Extract ->
Clean(basic) -> Chunk(simple) -> Embed -> Load -> Verify. DEFER (do NOT build): Stage 3 structure
(LLM), Stage 5 enrich (LLM), URL extraction/html2text, and any /search or /health API changes.

EMBEDDING (settled): sentence-transformers, SentenceTransformer("BAAI/bge-m3"), DENSE ONLY (sparse
is FTS5/BM25 per hybrid-search-spec.md — do NOT use FlagEmbedding). Assert dim 1024. Device
auto-detect (will be cpu here).

STORAGE CONTRACT — Load DEFINES it (retrieve.py is empty; nothing to match):
- Chroma path settings.chroma_db_path ("./chroma_db"); collection "{domain}_content".
- SQLite settings.sqlite_db_path ("data/dev_rag.db"); write chunks per migrations/001; apply BOTH
  001 and 002; 002's trigger auto-populates chunks_fts. If chunks lacks the `content` column the
  002 trigger references, STOP and report (schema bug).
- Chroma per-chunk metadata >= source, domain, page_number, chunk_id. Idempotency via content_hash.

HOW TO WORK: one stage at a time. For each: write its test, run `uv run pytest`, and if the stage
writes a data/ artifact print a short inspection summary. Then STOP and show me before the next
stage — do NOT run the full pipeline end-to-end unprompted. One commit per stage. Do NOT push.
If a stage is ambiguous or a needed convention/column is missing, STOP and ask.

DISCOVER FIRST: settings.py (paths, collection convention, embedding_model), migrations/001+002
(chunks columns + FTS5 table/triggers), ingest-pipeline-spec.md (stage details).

SETUP: `git status` clean (else stop). Create branch feat/phase1a-ingest.

TASK 0 — record OBS-007 decision:
- Replace src/dev_rag/ingest.py's MODULE docstring with the "SUPERSEDED STUB" note I provide.
- Add a one-line OBS-007 adoption note atop planning/ingest-pipeline-spec.md.
- Commit: `docs: record OBS-007 decision (spec supersedes ingest.py; thin slice)`.

TASK 1 — scaffold + CPU-pinned deps:
- Create src/dev_rag/ingest/__init__.py + tests/test_ingest/__init__.py.
- FIRST add this to pyproject.toml (so torch resolves to the CPU wheel, not the ~2GB CUDA build):
      [[tool.uv.index]]
      name = "pytorch-cpu"
      url = "https://download.pytorch.org/whl/cpu"
      explicit = true
      [tool.uv.sources]
      torch = [{ index = "pytorch-cpu" }]
  (needs uv >= 0.5.3; `uv self update` if the index config isn't recognized.)
- THEN `uv add torch sentence-transformers pymupdf`. Commit the regenerated uv.lock.
- Verify: `uv run python -c "import torch; print(torch.__version__, torch.cuda.is_available())"`
  prints a `+cpu` version and `False`. If it prints a CUDA build, STOP and fix the source pin.
- Ensure .gitignore ignores data/raw/, data/cleaned/, data/chunks/.
- Commit: `build: scaffold ingest package + CPU torch + deps`.

TASK 2 — Stage 1 Extract (ingest/extract.py): extract_pdf via PyMuPDF preserving page boundaries
(ExtractedPage/ExtractedDocument per spec); save_extracted -> data/raw/{slug}.json. extract_url =
NotImplementedError stub. test_extract.py with a TINY fixture PDF (not the full book). Run on the
Docker Deep Dive PDF, print page count + first-page snippet, STOP.
Commit: `feat(ingest): stage 1 extract (PDF via PyMuPDF)`.

TASK 3 — Stage 2 Clean (ingest/clean.py): basic non-LLM noise removal only (page numbers, recurring
headers/footers, blank pages). save -> data/cleaned/. test_clean.py with synthetic noisy pages.
Run, print pages kept/removed, STOP. Commit: `feat(ingest): stage 2 basic clean`.

TASK 4 — Stage 4 Chunk (ingest/chunk.py): simple fixed-size window (size/overlap) over CLEANED text
(no section structure yet). Carry metadata (source, source_id, domain, title, page_number) +
content_hash. save -> data/chunks/. Comment: fixed-size intentional (OBS-007); devops-008 is the
trigger to go structure-aware. test_chunk.py. Run, print chunk count + a sample, STOP.
Commit: `feat(ingest): stage 4 simple chunk`.

TASK 5 — Stage 6 Embed (ingest/embed.py): dense BGE-M3 via sentence-transformers, batched; assert
dim 1024 + no NaNs; device auto-detect. test_embed.py MUST MOCK the model (never load real BGE-M3
in tests — CPU + ~2GB download makes the suite unusable). Run on a few chunks, print dim, STOP.
Commit: `feat(ingest): stage 6 embed (BGE-M3 dense)`.

TASK 6 — Stage 7 Load (ingest/load.py): apply migrations 001+002; write chunks (full schema incl
content) + Chroma "{domain}_content" (ids/embeddings/documents/metadatas); content_hash idempotency;
assert chroma_count == sqlite_count == n_chunks and chunks_fts populated. test_load.py against temp
Chroma dir + temp SQLite. Run, print counts, STOP.
Commit: `feat(ingest): stage 7 load (ChromaDB + SQLite + migrations)`.

TASK 7 — Stage 8 Verify (ingest/verify.py) — STORE-LEVEL, do NOT call /search or /health:
(a) assert store count parity; (b) embed a sample devops query, query ChromaDB directly, assert
>=1 result whose source is Docker Deep Dive. test_verify.py. Run, print top result, STOP.
Commit: `feat(ingest): stage 8 store-level verify`.

TASK 8 — pipeline.py orchestrator: wire 1->2->4->6->7->8 (skip 3,5), each reading the prior data/
artifact, with --start-stage/--stop-stage/--dry-run. Run END-TO-END only after I approve stages.
Commit: `feat(ingest): thin-slice pipeline orchestrator`.

DO NOT: build Stage 3 or 5; implement URL extraction or add httpx/html2text; touch retrieval /
reranker / api.py /search / /health; revert relevance_score; push. Review + push are mine.
```
