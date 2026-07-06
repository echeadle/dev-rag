# dev-rag: Architecture & Decision Record

**Version:** 5.0  
**Date:** June 2026  
**Status:** Active development — resuming after Athens trip

---

## 1. What dev-rag Is

dev-rag is a personal expert collaboration system. The core idea is to index books you own and curated websites so you can have expert-level conversations about production software practices — not the tutorial-quality, insecure-by-default answers you find on Stack Overflow, but synthesised advice from high-quality sources you have personally vetted.

The motivating example was Docker secrets: virtually every tutorial shows passwords hardcoded in a Dockerfile or Compose file with a note saying "don't do this in production," but never shows the production alternative. dev-rag is designed to close that gap by making your curated library searchable and conversational.

It is not a general-purpose search engine. It is a personal knowledge base built from sources you trust, tuned for production-grade DevOps and travel questions.

---

## 2. System Overview

```
Sources (PDFs, URLs)
        │
        ▼
   Ingest Pipeline
   (PyMuPDF / httpx → chunker → BGE-M3 → ChromaDB + SQLite)
        │
        ▼
   FastAPI (dev-rag API)
        │
        ▼
   MCP Server (mcp_server.py)
        │
        ▼
   Claude Code (terminal sessions)
```

At query time the path reverses: Claude Code sends a tool call to the MCP server, which POSTs to the FastAPI layer, which embeds the query with BGE-M3, runs ANN search in ChromaDB, joins metadata from SQLite, optionally compresses results through Headroom, and returns ranked passages as MCP `TextContent`.

---

## 3. Technology Stack

| Component | Technology | Version |
|-----------|-----------|---------|
| Language | Python | 3.12 |
| Package manager | uv | (never pip) |
| API framework | FastAPI | latest |
| Data validation | Pydantic / Pydantic AI | v2 |
| Vector store | ChromaDB | latest |
| Metadata store | SQLite | built-in |
| Graph store | NetworkX | latest |
| Document loader | PyMuPDF | latest |
| Web loader | httpx | latest |
| Embedding model | BGE-M3 | (BAAI/bge-m3) |
| MCP server | mcp Python SDK | >=1.0.0 |
| Containerisation | Docker Compose | latest |
| Secret management | python-dotenv | latest |
| Context compression | Headroom (optional) | latest |
| Reranker | bge-reranker-v2-m3 | (BAAI/bge-reranker-v2-m3) |
| BM25 / sparse search | SQLite FTS5 | built-in |
| Rank fusion | RRF (custom Python) | n/a |

---

## 4. Architectural Decisions

Each decision below records what was chosen, what was considered, and why the choice was made. These are the decisions that are easy to second-guess six months later.

---

### ADR-001: Python over Go for the retrieval layer

**Decision:** Python is the sole language for all retrieval, orchestration, and API logic.

**Context:** A Go RAG server was explored early in the project. Go is a strong serving language — fast, low memory overhead, clean concurrency model.

**Why Python won:**  
The entire cutting-edge RAG ecosystem lands in Python first: PyTorch, HuggingFace `sentence-transformers`, reranker libraries, evaluation frameworks (RAGAS, DeepEval), and contextual retrieval research. In Go you would be perpetually reimplementing things or shelling out to Python processes anyway. The retrieval quality ceiling in Go is meaningfully lower, not because of the language but because of ecosystem access.

The one scenario where Go would still make sense is as a thin API gateway in front of the Python retrieval service — handling routing, auth, and connection pooling — while Python does all the actual RAG work. That pattern was kept open but not implemented, because there was no specific latency or deployment requirement that justified the split codebase.

**Rejected alternative:** Go for serving + Python sidecar for ML. Adds operational complexity (two processes, two languages, cross-process serialisation) for no retrieval quality gain.

---

### ADR-002: BGE-M3 as the embedding model

**Decision:** BAAI/bge-m3 for all domains (DevOps and Travel).

**Context:** Several embedding models were evaluated including `voyage-code-2` (Voyage AI, code-specific), `Qwen3-Embedding-8B` (highest MTEB accuracy among open models at time of decision), and `nomic-embed-text-v2` (good general-purpose baseline). The question was whether to use a code-specific model for the DevOps corpus and a general model for Travel, or a single model across both.

**Why BGE-M3:**

1. **Hybrid-native.** BGE-M3 is a single model that produces dense vectors, sparse vectors (like BM25 weights), and ColBERT-style multi-vector representations simultaneously. Most models force you to run separate dense and sparse models and fuse the results. BGE-M3 gives you all three from one inference call, which matters for hybrid search on technical documentation.

2. **Code + prose balance.** The DevOps corpus is a mix of prose explanation, YAML configuration, shell commands, and Python code. A pure code embedding model like `voyage-code-2` is optimised for code-to-code retrieval; it underperforms on natural language questions about code. BGE-M3's training covers both, which matches the actual query pattern ("how do I configure Docker bridge networks" is prose, not code).

3. **Local inference, no API dependency.** Voyage AI is a hosted API. BGE-M3 runs locally via HuggingFace, which is consistent with the project's strong preference for open ecosystems and avoiding vendor lock-in. No API key, no per-token cost, no outbound dependency at query time.

4. **Operational simplicity.** Using one model for both domains means one model loaded in memory, one embedding function wired to all collections, and no per-domain routing logic in the embedding layer. The routing registry (domain → collection) stays simple.

**Why not Qwen3-Embedding-8B:** Higher MTEB accuracy, but 8B parameters requires meaningful GPU VRAM. BGE-M3 at ~570M parameters is comfortable on available hardware without competing with other local inference workloads. Qwen3-Embedding-8B is the natural upgrade path if retrieval quality becomes the bottleneck.

**Why not voyage-code-2:** Hosted API (vendor dependency), optimised for code-to-code rather than prose-about-code, and no sparse vector output for hybrid search.

---

### ADR-003: ChromaDB as the vector store

**Decision:** ChromaDB for vector storage, with pgvector noted as the migration path.

**Context:** pgvector (Postgres extension) and ChromaDB were the primary candidates. Qdrant was also considered.

**Why ChromaDB first:**  
ChromaDB has a batteries-included Python API that binds the embedding function directly to the collection, making collection-per-domain isolation the default behavior rather than something you engineer. For a project that was incomplete at vacation time, reaching a working baseline quickly was the priority. ChromaDB runs in-process with no separate service, which keeps Docker Compose simple (one container, not two).

**Why pgvector is the likely future:**  
pgvector keeps everything in Postgres, which means hybrid dense + full-text search in a single query using native `tsvector` and RRF fusion — no need for a separate sparse store. It also means SQL for all metadata filtering and joins, which is more powerful than ChromaDB's metadata filter syntax. The multi-domain, multi-model pattern maps cleanly to table-per-domain in pgvector (separate `vector(N)` column per table, matching the dimensionality of the model used for that domain).

**pgvector security note:** Always use version 0.8.2 or later — a buffer
overflow in parallel HNSW index builds in versions 0.6.0–0.8.1 can leak
data from other relations. Use the pinned Docker image
`pgvector/pgvector:pg16-0.8.2` (OBS-011 fix — never use the floating
`:pg16` tag). Verify the installed version with:
```sql
SELECT extversion FROM pg_extension WHERE extname = 'vector';
```

**The planned swap-and-compare approach:** The project philosophy is to build with ChromaDB first, get it fully working, then swap to pgvector and benchmark the difference. This produces genuine understanding of both tools rather than a blind framework choice.

---

### ADR-004: SQLite for document metadata

**Decision:** SQLite for storing document-level metadata (source, domain, page number, chunk ID, content hash, version, ingest timestamp).

**Why:** Chunk metadata doesn't belong in the vector store. ChromaDB's metadata filter is useful for simple equality filters but is not a relational database — you can't efficiently join, aggregate, or run complex queries against it. SQLite is zero-infrastructure (file on disk), has full SQL, and integrates trivially with Python. At personal-scale (thousands of documents, not millions) it is more than sufficient.

**Chunk metadata schema** (from the document update strategy planning document):

| Field | Type | Purpose |
|-------|------|---------|
| `source_id` | TEXT | Stable identifier for the source document |
| `chunk_id` | TEXT | Unique identifier for this chunk |
| `content_hash` | TEXT | SHA-256 of chunk text for change detection |
| `version` | TEXT | Edition or version of the source |
| `domain` | TEXT | `devops` or `travel` |
| `source_path` | TEXT | Original file path or URL |
| `page_number` | INT | Page in the source PDF (if applicable) |
| `ingest_timestamp` | TEXT | ISO 8601 timestamp of last ingest |
| `status` | TEXT | `active`, `superseded`, `deleted` |

---

### ADR-005: NetworkX for GraphRAG

**Decision:** NetworkX for a knowledge graph stored as JSON on disk, used alongside (not instead of) vector search.

**Context:** Pure vector search handles "find passages similar to this query" well, but struggles with multi-hop questions ("what is the relationship between decorators and closures?"), prerequisite chains ("what do I need to understand before learning metaclasses?"), and cross-document connections ("how do Python scripts interact with Docker?"). A knowledge graph makes relationships between concepts explicit and queryable.

**Why NetworkX over Neo4j:**  
Neo4j requires a separate running service. NetworkX is pure Python, runs in-process, and persists as a JSON file alongside `chroma_db/`. At personal scale (tens of thousands of nodes at most from a book collection) it is more than fast enough. No extra Docker service, no extra configuration.

**Hybrid GraphRAG pattern:** Vector search and graph traversal run in parallel at query time. Results are merged and deduplicated before being passed to the LLM. This is additive — the graph enhances retrieval without replacing it.

```
User question
      │
      ├──► Vector search (ChromaDB)   ──► top-k similar chunks
      │
      └──► Graph traversal (NetworkX) ──► related concept chunks
                │
                ▼
         Merge + deduplicate
                │
                ▼
         FastAPI returns ranked results
```

The graph is built once at ingest time using Claude to extract entities and relationships (one-time cost), then queried cheaply at runtime.

---

### ADR-006: Document update strategy — wholesale replacement vs. incremental upsert

**Decision:** Two strategies depending on source type, not a single universal approach.

**Context:** When a new edition of a book is released, or a documentation site is updated, how should dev-rag handle the existing chunks? Chunk-level diffing was considered and rejected.

**Why chunk diffing fails:** Chunks don't have stable identities. When a document is edited, chunk boundaries shift. A chapter that was previously chunks 10–18 might become chunks 11–20. There is no reliable way to match old chunks to new chunks without comparing every possible pair, which is O(n²) and fragile in practice.

**Strategy A — Wholesale replacement** (for static artifacts: books, versioned docs):
1. Delete all chunks with `source_id = <this document>`
2. Re-ingest the entire document from scratch
3. Update version field in SQLite metadata

Use when: a new edition of a book is released, a PDF is corrected, any source where the entire document changes at once.

**Strategy B — Incremental upsert** (for living sources: documentation sites, runbooks):
1. Fetch current content
2. Hash each new chunk
3. Compare against stored `content_hash` values
4. Upsert chunks whose hash has changed; leave unchanged chunks alone
5. Mark chunks that no longer exist as `status = 'deleted'`

Use when: a documentation site is crawled on a schedule, a runbook is updated frequently, any source where only parts change between updates.

**Source-type decision matrix:**

| Source type | Strategy | Rationale |
|-------------|----------|-----------|
| Technical book (PDF) | Wholesale | Entire document replaced per edition |
| Official docs site | Incremental upsert | Pages update independently |
| Blog post / article | Wholesale | Treat as immutable per URL |
| Internal runbook | Incremental upsert | Frequent partial edits |
| GitHub README | Incremental upsert | Commit-level changes |

---

### ADR-007: Multi-domain architecture — one server, isolated collections

**Decision:** Single dev-rag server instance with separate ChromaDB collections per domain (`devops`, `travel`).

**Context:** The project has two corpora with different subject matter. The question was whether to run separate server instances or share one.

**The hard constraint:** Vectors from different embedding models cannot share a collection. Different models have different dimensionality and incompatible vector spaces — cosine similarity between a BGE vector and a Nomic vector is noise. Even if two models share dimensionality, their spaces are unrelated.

**The corollary:** Queries must be embedded with the same model used to index the collection. The routing registry (domain → embedding model → collection name) is the critical piece of glue.

**Why one server:** With BGE-M3 chosen for both domains (ADR-002), both collections use the same model. There is no technical reason for separate instances, and one server is simpler to operate, deploy, and monitor. If domains ever needed different models, the right shape would be separate collections on the same server (not separate servers), with a routing registry directing queries to the right collection and embedding function.

**Cross-domain search:** When `search_all` is called from the MCP server, results are retrieved separately per collection and merged. If a reranker is added (the planned next step), it runs over the merged result set to produce a single ranked list regardless of source domain.

---

### ADR-008: MCP server transport — stdio default, HTTP/SSE optional

**Decision:** stdio as the default transport for Claude Code integration, HTTP/SSE available via `--http` flag.

**Why stdio for local dev:** Claude Code spawns the MCP server as a subprocess over stdin/stdout. Zero ports, zero networking configuration, works immediately with `claude mcp add --transport stdio`. The process lifecycle is managed by Claude Code — it starts and stops with the session.

**Why HTTP/SSE for multi-session or remote access:** When multiple Claude Code sessions need to share one MCP server, or when Argos (the personal AI orchestration framework) needs to call the RAG corpus, HTTP/SSE allows multiple clients to connect to a single running instance. Registered with `claude mcp add --transport sse`.

**Configuration storage:** `~/.claude.json` for user scope (available in all projects) or `.mcp.json` in the project root for project scope (committed to git). User scope is the right choice for dev-rag since the corpus is not project-specific.

---

### ADR-009: Headroom for context compression (optional layer)

**Decision:** Headroom integrated as an optional compression layer on MCP server output, not a hard dependency.

**Context:** Headroom is an open-source context compression library (Apache 2.0, by Tejas Chopra, Netflix) that sits between the RAG retrieval output and the LLM, compressing tool outputs before they consume context window tokens. Benchmarks show 60–95% token reduction on RAG workloads specifically, with 95%+ accuracy preservation.

**Why it fits dev-rag:** RAG output is exactly the dynamic, high-noise content Headroom is designed for — chunked passages with metadata that the LLM often doesn't need verbatim. The MCP server's `_format_results()` function is the natural integration point: compress the formatted result string before wrapping it in `TextContent`. This is additive and reversible — Headroom's CCR (Content-Compressed Retrieval) saves compressed data locally so the LLM can request the original if needed.

**Why optional:** Headroom adds a dependency and a latency step. For short result sets (5 chunks) it may not be worth it. For larger cross-domain queries (20–30 chunks) the token savings become significant. The architecture keeps it optional so it can be toggled per-query or per-domain without changing the retrieval pipeline.

**Distinction from prompt caching:** Anthropic's prompt caching is better for fixed prefixes (same 50K-token system prompt, varying short user messages). Headroom is better when context is dynamic — which dev-rag output is. The two are complementary, not competing.

---

### ADR-013: Staged ingest pipeline with LLM enrichment

**Decision:** Replace the basic sliding-window chunker with an 8-stage
ingest pipeline: extract → clean → structure → chunk → enrich → embed
→ load → verify.

**Context:** The original `ingest.py` stub used a fixed 1000-character
sliding window with no noise removal, no structure awareness, and no
metadata enrichment. A staged approach document was reviewed in Athens
(June 2026) that demonstrated a significantly more sophisticated pipeline.

**Why the staged approach:**

Retrieval quality is determined more by document preparation than by the
vector database or embedding model. The basic chunker sends noisy,
unstructured text to the embedder — including table of contents entries,
page numbers, headers, footers, and mid-sentence splits across chunks.

The staged pipeline fixes this:

1. **Cleaning** removes TOC, index, copyright, headers, and footers before
   anything is chunked or embedded
2. **Structure detection** uses Claude to identify chapter and section
   boundaries so chunks follow the book's logical structure
3. **Semantic chunking** keeps sections intact as single chunks and only
   splits when a section exceeds ~1500 tokens — at paragraph boundaries,
   never mid-sentence
4. **Enrichment** adds summaries, keywords, synthetic questions, and
   extracted code blocks to each chunk

**The enrichment stage is particularly high-value for dev-rag:**

- **Summaries** give BGE-M3 a cleaner embedding signal — distilled meaning
  rather than raw technical prose
- **Keywords** improve BM25 sparse matching in hybrid search — exact flag
  names, command names, and tool names are explicitly indexed
- **Synthetic questions** match real user queries better than source text —
  "What is the production-safe way to store secrets?" matches our eval
  questions directly
- **Code extraction** stores code blocks separately so they can be
  retrieved as exact examples rather than embedded as prose

**Inspect at every stage:**
The pipeline includes `--stop-stage` and `--start-stage` flags so each
output can be inspected before the next stage runs. This is the correct
approach for building a high-quality corpus — automate only after
each stage is verified to produce good output.

**Synthetic questions as eval seeds:**
The synthetic questions generated at Stage 5 (3 per chunk) can feed
directly into the eval harness as additional question candidates — the
pipeline effectively generates eval questions as a by-product of ingest.

**Implementation:** Spec in `planning/ingest-pipeline-spec.md`.
Replaces the `chunk_text()` stub in `src/dev_rag/ingest.py` with a
proper `src/dev_rag/ingest/` package.

---

### ADR-010: uv for all package management

**Decision:** uv exclusively. Never pip.

**Why:** uv is 10–100x faster than pip for dependency resolution and installation, has a compatible `pyproject.toml` interface, and produces reproducible lockfiles. This is a project-wide convention applied to all Python projects, not a dev-rag-specific decision.

---

### ADR-011: Python domain added to the corpus

**Decision:** Add `python` as a third domain alongside `devops` and `travel`,
ingesting personally owned Python books and curated Python reference sites.

**Context:** The project is already writing a Python AI agent programming book,
and Edward's primary language across all projects (Utah Watchdog, Argos, dev-rag
itself) is Python. The same gap that motivated dev-rag for DevOps exists for
Python: tutorial answers to Python questions are shallow, and production-grade
guidance — on metaclasses, descriptors, async patterns, memory management,
packaging — lives in books, not Stack Overflow.

**Why a separate domain rather than merging into devops:**
Python content and DevOps content have different vocabularies and different
query patterns. A question about Python decorators should not surface Docker
chunks, and vice versa. Domain isolation keeps retrieval precise and gives
Claude Code a `search_python` tool that is unambiguous in scope. A
`search_all` call can still fan out to all three domains when needed.

**No architectural changes required:**
The existing domain routing registry pattern (ADR-007) handles additional
domains cleanly. Adding `python` requires:

1. Add `python` as a valid domain value in settings and validation
2. Create a `python` ChromaDB collection at first ingest
3. Add `search_python` tool to the MCP server alongside `search_devops` and `search_travel`
4. Add `data/evaluation/python_questions.yaml` to the eval harness

No changes to the embedding model (BGE-M3 handles Python prose and code
equally well — see ADR-002), no changes to the chunking pipeline, no changes
to the hybrid search or reranker layers. All existing infrastructure applies
unchanged to the new domain.

**AI domain added (June 2026):**
A fourth domain `ai` was added to the corpus to house RAG and AI engineering
references — specifically "RAG-Driven Generative AI" (Rothman, Packt 2024)
and "A Simple Guide to RAG" (Kimothi, Manning). This domain is meta — it
contains books about building the system you are using to query them.
The `search_ai` MCP tool and `data/evaluation/ai_questions.yaml` seed
7 initial evaluation questions covering RAG taxonomy, chunking strategies,
reranker tradeoffs, evaluation metrics, and hallucination reduction.

**Initial Python corpus candidates** (books owned, to be ingested in priority order):

| Source | Type | Priority |
|--------|------|----------|
| Fluent Python (Ramalho) | PDF | High — production-grade idioms |
| Python Cookbook (Beazley & Jones) | PDF | High — practical recipes |
| Architecture Patterns with Python (Percival & Gregory) | PDF | High — DDD, ports & adapters |
| CPython Internals (Shaw) | PDF | Medium — deep internals |
| Python docs (docs.python.org) | URL | High — authoritative reference |
| Real Python articles (curated) | URL | Medium — selected production topics |

**Evaluation questions this domain enables:**

- "What is the difference between `__new__` and `__init__` and when would you use `__new__`?"
- "When should you use a generator instead of building a list?"
- "How do Python descriptors work and what are they used for in production code?"
- "What does `__slots__` do and when is it worth the tradeoff?"
- "How does the GIL affect CPU-bound vs I/O-bound concurrency?"
- "What is the difference between `asyncio.gather` and `asyncio.TaskGroup`?"

These are exactly the questions where tutorial answers are wrong or incomplete
and a good book gives the real production answer — the same motivation as the
original DevOps corpus.

**Connection to the Python AI agent book:**
The Python corpus will serve double duty — as a retrieval source for dev-rag
queries during development, and as a living reference for the book itself.
Chapters covering advanced Python patterns can be validated against the corpus
the same way DevOps chapters are validated against Docker documentation.

---

### ADR-012: Cross-encoder reranker — bge-reranker-v2-m3

**Decision:** Add `bge-reranker-v2-m3` as a second-pass reranking stage over
the top-50 candidates from hybrid search.

**Context:** Hybrid search (ADR hybrid spec) produces a good ranked list of
candidates via RRF fusion of dense vectors and BM25. A cross-encoder reranker
produces a better ranked list by reading the query and each candidate chunk
*together* as a pair and scoring their relevance directly — something the
first-pass retrieval cannot do, since bi-encoders encode query and document
independently.

**The two-stage pattern:**

```
Stage 1 (fast, approximate): Hybrid search → top-50 candidates
Stage 2 (slow, precise):     Cross-encoder → re-scored top-10
```

**Why bge-reranker-v2-m3:**

1. **Companion to BGE-M3.** Both are from BAAI, trained to work together.
   The reranker understands the same vocabulary and concept space as the
   embedding model already in use.

2. **Local inference, no API dependency.** Runs via HuggingFace
   `sentence-transformers`. No outbound call, no per-query cost. Consistent
   with the open-ecosystem principle throughout this project.

3. **Reasonable size.** ~568M parameters — similar to BGE-M3 itself.
   Runs on CPU for personal-scale query volumes; significantly faster on GPU.

4. **Multilingual.** Handles the Travel corpus (English prose, some French
   and Greek place names) as well as DevOps and Python corpora without
   domain-specific configuration.

**Why not alternatives:**

| Alternative | Reason rejected |
|-------------|----------------|
| `bge-reranker-v2-gemma` | 2B parameters — too heavy for local inference |
| `cross-encoder/ms-marco-MiniLM-L-6-v2` | English-only, weaker on technical content |
| Cohere Rerank API | Hosted, per-call cost, vendor dependency |
| Voyage AI Rerank | Same objection as Cohere |

**Graceful fallback:** If the reranker fails (OOM, model not loaded, unexpected
input), the route returns hybrid search results in RRF order rather than a 500
error. For a local dev tool this is the right behaviour — degraded quality is
better than a crashed tool. The fallback wraps `HybridResult` objects in
`RankedResult(reranker_score=None)` so the `/search` serialisation never hits
an `AttributeError` when reading `.reranker_score` (OBS-002 fix).

**Implementation:** Spec in `planning/reranker-spec.md`. One new file
(`reranker.py`), one modified (`api.py` — startup model load and two-stage
search route).

**Measured delta (2026-07-06, Phase 4 baseline — 36 devops questions, 25 with
verified expected_source; corpus = 2 books / 583 chunks; reranker
bge-reranker-v2-m3 @ 10 candidates on CPU):**

| Metric | hybrid RRF | + reranker | delta |
|---|---|---|---|
| Retrieval@1 | 92.0% | 96.0% | **+4.0** |
| Retrieval@3 | 100% | 100% | **0.0** |
| MRR | 95.3% | 98.0% | +2.7 |
| Chunk match | 84.6% | 88.5% | +3.9 |
| Negative precision | n/a (FBL-005: RRF has no relevance scale) | **0.0%** | — |
| Latency/query (warm) | ~0.15 s | ~15 s | ~100× |

Baselines: `eval/baselines/2026-07-06_hybrid_rrf.json` / `_reranker_c10.json`.

**Decision:** the ADR's own criterion triggered — R@3 delta is below +3 points
(hybrid RRF is already at the R@3 ceiling on this two-book corpus), so
`reranker_enabled` stays **False** by default. The reranker remains fully
implemented for per-run use (`RERANKER_ENABLED=true`) and the question
re-opens when the corpus grows enough for R@3 headroom to exist.

**New finding (FBL-006):** the hoped-for negative gating (logit < 0 rejects
out-of-corpus queries) does NOT hold — all 3 negatives (Podman/Nomad/GitLab)
got confidently positive logits on near-miss content; negative precision 0%.
Composite scores are NOT comparable across the two runs (negatives only
computable in the reranker run). Tracked in docs/TODO.md.

---

These are the planned next steps in priority order, based on where retrieval
quality improvements are highest-leverage. Items marked ✓ have a complete
spec in `planning/` and are ready to implement.

1. **Staged ingest pipeline** ✓ — 8-stage pipeline replacing the basic
   sliding-window chunker. Stages: extract → clean → structure → chunk
   → enrich (summaries, keywords, synthetic questions, code) → embed
   → load → verify. Spec: `planning/ingest-pipeline-spec.md`.
   This is now the highest-priority item — it affects retrieval quality
   for every subsequent phase.

2. **Hybrid search** ✓ — BM25 (SQLite FTS5) + dense vectors (BGE-M3) fused
   with Reciprocal Rank Fusion. Spec: `planning/hybrid-search-spec.md`.
   Pure dense vector search is no longer the professional baseline in 2026.
   The DevOps and Python corpora especially benefit from exact-token matching
   (flag names, error strings, API method names).

2. **Cross-encoder reranker** ✓ — `bge-reranker-v2-m3` runs a second pass
   over the top 50 candidates from hybrid search, scoring (query, document)
   pairs directly. Spec: `planning/reranker-spec.md`. Often the single
   highest-impact retrieval improvement. Also enables true cross-domain
   unified ranking for `search_all`.

3. **Evaluation harness** ✓ — Question-driven benchmark with seven scoring
   metrics (Retrieval@k, MRR, chunk match, negative precision, paraphrase
   consistency, source precision, graph lift) and a `--compare` flag for
   delta reporting between pipeline changes.
   Spec: `planning/dev-rag-evaluation-strategy.md`.

4. **Python domain** ✓ — Third corpus alongside DevOps and Travel.
   Decision recorded in ADR-011. No architectural changes required —
   add domain to settings, create ChromaDB collection, add `search_python`
   MCP tool, add `python_questions.yaml` to eval harness.

5. **Headroom integration** ✓ — Wire `_format_results()` in `mcp_server.py`
   through Headroom CCR compression before returning `TextContent`.
   Most valuable for large cross-domain queries (20–30 chunks).
   Spec: `planning/headroom-integration-spec.md`.

6. **pgvector migration** ✓ — Swap ChromaDB for pgvector, benchmark retrieval
   quality and latency, and compare. Hybrid search SQL for pgvector is already
   documented in `planning/hybrid-search-spec.md` (migration note section).
   Full migration spec: `planning/pgvector-migration-spec.md`.
   This is part of the explicit build-and-swap learning approach.

---

## 5. Peer Review Findings — Opus 4.8 (June 2026)

A peer review was conducted using Claude Opus 4.8 across all planning
documents and scaffold code before implementation began. The reviewer
produced 12 observations. All were addressed. The findings and resolutions
are recorded here for traceability.

### Resolved — High Severity

**OBS-001: `/search` response field name contract mismatch**  
The hybrid search and reranker specs defined `rrf_score` and `reranker_score`
as separate fields, but the MCP server's `_format_results()` read a `score`
field, and the eval scorer's negative-precision check also read `score`. Test
fixtures used `score`, masking the mismatch.

*Resolution:* Established `relevance_score` as the single canonical field
emitted by `/search` regardless of search mode. Set from `reranker_score`
when the reranker runs, from `rrf_score` on fallback. All consumers,
test fixtures, and specs updated to match.

**OBS-002: `rerank_with_fallback()` returned wrong type on fallback**  
The fallback paths returned raw `HybridResult` objects, but the `/search`
serialisation read `.reranker_score` — an attribute that only exists on
`RankedResult`. This caused an `AttributeError` in exactly the degraded
conditions the fallback was written to survive.

*Resolution:* `rerank_with_fallback()` now wraps all fallback results in
`RankedResult(reranker_score=None, ...)`. The response shape is uniform
whether or not the reranker ran. Fallback tests updated to assert
`isinstance(result, RankedResult)` and `result.reranker_score is None`.

---

### Resolved — Medium Severity

**OBS-003: `expected_source: null` on all eval questions prevented metrics from computing**  
With `expected_source: null` on every question, Retrieval@k, MRR, and the
composite score never computed — making the `--compare` delta workflow
useless for the planned component swaps.

*Resolution:* `devops-006` (source_specific question) now has
`expected_source: "docker-deep-dive.pdf"`. `devops-001` has a note
explaining when to populate it after ingestion. The scorer now computes
a partial weighted composite from whichever metrics are available rather
than returning `None` when all components are not present.

**OBS-004: `runner.py` called non-existent endpoints**  
The eval runner posted `domain=None` for cross-domain questions (which
fails `SearchRequest` validation) and called `/search/graph` (which has
no implementation or spec).

*Resolution:* Cross-domain questions now fan out to per-domain endpoints.
Graph scoring is gated behind `GRAPH_ENDPOINT_AVAILABLE = False` and will
remain off until `/search/graph` is specced and implemented.

**OBS-006: Porter stemming undercuts exact flag-token matching**  
The hybrid search rationale claimed BM25 would match CLI flags like
`--network=host` "with perfect precision," but the `porter ascii` tokenizer
strips punctuation and stems tokens — `--network=host` indexes as `network`
and `host`, not the full flag syntax.

*Resolution:* An honest caveat added to the porter ascii tokenizer
explanation in `planning/hybrid-search-spec.md`. The ablation queries
are still required to verify actual flag-level recall before relying on
BM25 for exact-syntax matching. If flag-syntax precision is required,
`unicode61` with custom `tokenchars` is the documented alternative.

**OBS-007: Sliding-window chunker weakness not explicitly scoped**  
The chunk_boundary eval category (devops-008) is specifically designed
to catch when multi-step procedures get split mid-sequence. No roadmap
phase addressed structure-aware chunking, creating an ambiguity about
whether failures were expected or a bug.

*Resolution:* Explicitly documented in `ingest.py` as out of scope for
the initial implementation. chunk_boundary failures are expected and
useful signals. The remediation path is: tune `chunk_size`/`overlap`
first, then consider structure-aware chunking if failures persist.

**OBS-008: Headroom integration tested only against a mocked API surface**  
All ten Headroom tests mock the assumed constructor and result attributes.
If the real library's API differs, the tests pass while the integration
silently fails.

*Resolution:* A live smoke test step added as Step 2 of the Headroom
implementation order in `planning/headroom-integration-spec.md`. The
smoke test must confirm real constructor arguments, result attributes,
and `session_stats()` before `compress.py` is written.

**OBS-009: ChromaDB + SQLite drift has no detector until pgvector**  
A write failure mid-ingest can leave ChromaDB and SQLite out of sync,
degrading RRF results with no signal until the pgvector migration resolves
it with ACID transactions.

*Resolution:* `/health` now returns `store_parity` — ChromaDB vs SQLite
chunk counts per domain — and a `stores_in_sync` flag. Status is `degraded`
rather than `ok` if any domain is out of sync.

---

### Resolved — Low Severity

**OBS-005: Missing `def` header in test file fused two tests into one**  
`test_search_all_fanout_on_500` had no `def` line — its body ran as
trailing code of `test_search_all_fanout_three_domains` and was never
reported as an independent test result.

*Resolution:* `def test_search_all_fanout_on_500()` header restored.
Now 18 independent MCP server tests.

**OBS-010: Deprecated `@app.on_event("startup")` used for reranker load**  
FastAPI deprecates `on_event` in favour of a `lifespan` context manager.

*Resolution:* `api.py` now uses `@asynccontextmanager async def lifespan(app)`
passed to `FastAPI(lifespan=lifespan)`. The deprecated decorator is removed.

**OBS-011: pgvector image tag not pinned despite CVE note**  
The migration spec cited a CVE fixed in 0.8.2 but used the floating
`:pg16` image tag, which doesn't guarantee that version.

*Resolution:* Image pinned to `pgvector/pgvector:pg16-0.8.2`. Added note
not to use the floating `:pg16` tag.

**OBS-012: Pydantic v1 inner `class Config` style used under a v2 stack**  
`settings.py` used the deprecated v1-era `class Config:` inner class
which emits warnings under pydantic-settings v2.

*Resolution:* Replaced with `model_config = SettingsConfigDict(...)` throughout.

---

### Open Questions (from Opus review — not yet resolved)

These are genuine ambiguities to decide before the relevant implementation
phases begin. They do not require code changes now.

**GraphRAG scope:** ✅ **DECIDED — DEFERRED**  
GraphRAG (ADR-005, `graph.py`, `agent.py`, `/search/graph`) is explicitly
out of scope for the current implementation pass (Phases 1–7). The core
value of dev-rag comes from hybrid search + reranker. GraphRAG cannot be
meaningfully measured without a working eval harness baseline first.
Implement as **Phase 8** after the baseline is established.
- `graph.py` and `agent.py` remain as stubs
- `requires_graph` eval questions remain as placeholders but are not scored
- `GRAPH_ENDPOINT_AVAILABLE = False` stays in `eval/runner.py`
- GraphRAG spec to be written when Phase 4 baseline is established
- *Decision made: Athens, June 2026*

**Eval harness timing vs. component swaps:** ✅ **DECIDED**  
Minimum threshold of **25 questions with `expected_source` populated**
before trusting any `--compare` delta to gate a migration or component
swap. This is a starting point to experiment with — not a hard rule.
The implementation order gains a checkpoint between Phase 4 and Phase 5:

- **Phase 4** — Eval harness running, ~9 seed questions, first baseline established
- **Phase 4b** — Grow question set to 25 with `expected_source` populated on each
- **Phase 5 onwards** — `--compare` deltas are meaningful and can gate decisions

If 25 questions produces stable, consistent deltas, the threshold stays.
If deltas are still noisy, increase toward 50. The eval strategy document
notes that "the first 40 questions expose ranking problems" — 25 is the
right first checkpoint on that journey.
- *Decision made: Athens, June 2026*

**`requires_multi_source` and `requires_graph` flags unscored:** ✅ **DECIDED — KEEP AS ASPIRATIONAL METADATA**  
Both flags are retained in the eval question YAML schema as statements of
intent. They cost nothing to carry and ensure goals are not lost as the
project grows. Neither drives a metric today but both will when the
corresponding capabilities are built:

- `requires_graph` — will drive the graph-lift metric when GraphRAG
  is implemented in Phase 8
- `requires_multi_source` — will drive a future multi-source coverage
  metric ("did results come from at least two different sources?") once
  the corpus is large enough to make it meaningful

The scorer ignores both flags for now. No questions need retagging later.
This is a deliberate choice to build a professional, complete system
rather than trimming scope to what is immediately measurable.
- *Decision made: Athens, June 2026*

**Cross-domain `search_all` ranking post-reranker:** ✅ **DECIDED — PHASE 5b**  
`search_all` will be upgraded to true unified reranked ranking as Phase 5b,
immediately after the reranker is working (Phase 3) and before the Python
domain is added (Phase 5). The implementation is small — pass the
concatenated per-domain fan-out candidates through the reranker already
loaded in memory. The reranker scores (query, document) pairs without
caring which domain the document came from, so no new model or
infrastructure is needed.

Rationale for timing: adding the Python domain without unified ranking
produces confusing `search_all` results (three independently ordered lists
concatenated). Fixing it first means the Python domain lands into a
properly working cross-domain tool.

The current per-domain fan-out concatenation is explicitly a temporary
design. Phase 5b is when it becomes permanent unified ranking.
- *Decision made: Athens, June 2026*

---

**Build first, swap and compare second.** The project approach is to build with proven, capable tools (ChromaDB, FastAPI, BGE-M3), get the system fully working, then systematically swap components (ChromaDB → pgvector, etc.) and benchmark the difference. This produces genuine understanding rather than framework shopping.

**Curated sources over volume.** dev-rag is deliberately a personal expert system built from sources you have vetted. It is not a crawler of the open web. The signal-to-noise ratio of the corpus is more important than its size.

**Local inference, open ecosystem.** No API-dependent embedding models, no proprietary vector stores, no vendor lock-in. Everything runs on your hardware with open-source components.

**Provenance matters.** Every retrieved chunk carries its source, page number, and domain. Answers are traceable back to the specific book or page that informed them.

---

## 7. File Structure

```
dev-rag/
├── src/dev_rag/
│   ├── ingest.py             # Document loading, chunking, embedding, ChromaDB write
│   ├── retrieve.py           # Query embedding, ANN search, metadata join
│   ├── retrieve_sparse.py    # BM25 via SQLite FTS5
│   ├── retrieve_hybrid.py    # RRF fusion of dense + sparse results
│   ├── reranker.py           # Cross-encoder reranking + graceful fallback
│   ├── graph.py              # NetworkX knowledge graph build, persist, query
│   ├── agent.py              # Pydantic AI agent with search_corpus + search_graph tools
│   └── api.py                # FastAPI routes (/search, /documents, /collections, /health)
├── mcp/
│   ├── mcp_server.py         # MCP server (stdio + HTTP/SSE)
│   ├── pyproject.toml
│   └── Dockerfile
├── tests/
│   ├── test_ingest.py
│   ├── test_retrieve.py
│   ├── test_hybrid_search.py
│   ├── test_reranker.py
│   ├── test_graph.py
│   ├── test_agent.py
│   └── test_mcp_server.py
├── data/
│   └── evaluation/
│       ├── devops_questions.yaml
│       ├── travel_questions.yaml
│       ├── python_questions.yaml
│       └── cross_domain_questions.yaml
├── eval/
│   ├── run_eval.py
│   ├── loader.py
│   ├── runner.py
│   ├── scorer.py
│   ├── reporter.py
│   └── results/              # gitignored
├── migrations/
│   ├── 001_initial_schema.sql
│   └── 002_add_fts5.sql
├── planning/
│   ├── rag-document-update-strategy.md
│   ├── hybrid-search-spec.md
│   ├── reranker-spec.md
│   └── PRD-docker.md
├── chroma_db/                # ChromaDB persistence (volume-mounted)
├── graph_db/
│   └── knowledge_graph.json
├── docker-compose.yml
├── docker-compose.mcp.yml
├── Dockerfile
├── pyproject.toml
├── .env                      # Never committed
└── DEV-RAG-ARCHITECTURE.md   # This document
```

---

## 8. Running the System

> **⚠ Superseded for now — see `docs/RUNBOOK.md`.** The commands below are the
> aspirational Docker-based workflow; as of Phase 1a the system runs directly
> via `uv run` (see the runbook, verified 2026-07-05). Rewrite this section
> against reality when the API phase lands.

```bash
# Start dev-rag API
docker compose up -d

# Ingest a PDF
docker compose exec dev-rag uv run python -m dev_rag.ingest \
  --source /data/docker-deep-dive.pdf \
  --domain devops

# Ingest a URL
docker compose exec dev-rag uv run python -m dev_rag.ingest \
  --source https://docs.docker.com/engine/security/secrets/ \
  --domain devops

# Register MCP server with Claude Code (stdio, user scope)
claude mcp add --transport stdio dev-rag \
  --env DEV_RAG_BASE_URL=http://localhost:8000 \
  -- python /path/to/mcp/mcp_server.py

# Verify
claude mcp list

# Run tests
docker compose exec dev-rag uv run pytest
```

---

*v1 written in June 2026. v2 adds ADR-011 (Python domain). v3 adds ADR-012 (reranker). v4 adds Section 5 (Opus peer review, all 12 observations resolved, 4 open questions). v5 adds ADR-013 (staged ingest pipeline with LLM enrichment). Update this document whenever a significant decision is made or reversed.*
