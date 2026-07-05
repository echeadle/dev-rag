# dev-rag & Related Projects — To-Do List

**Last updated:** July 2026 (home)

> **Status note:** The OPUS architecture review is re-verified and essentially
> absorbed (see `docs/reviews/OPUS-REVIEW-VERIFICATION.md`) — 11/12 findings
> resolved at contract level. A small hardening pass (`review/opus-fixes`:
> test-gate fix + `runner.py` cleanup + headroom removal) is the only review
> work left. Real next work is implementing the stubbed pipeline.

---

## Active — dev-rag Implementation

Work through `IMPLEMENTATION-ORDER.md` in sequence:

- [ ] **Phase 1a** — Staged ingest pipeline (extract, clean, structure, chunk, enrich)
- [ ] **Phase 1b** — Wire up MCP server, ingest Docker Deep Dive, first query
- [ ] **Phase 2** — Hybrid search (BM25 + dense + RRF)
- [ ] **Phase 3** — Cross-encoder reranker (bge-reranker-v2-m3)
- [ ] **Phase 4** — Evaluation harness running, first baseline established
- [ ] **Phase 4b** — Grow eval question set to 25 with expected_source populated
- [ ] **Phase 5** — Python domain
- [ ] **Phase 5b** — Unified search_all ranking via reranker
- [ ] ~~**Phase 6** — Headroom compression~~ **REMOVED from the build path**
  (2026-07-04) — deferred to nice-to-have; see **Deferred** below.
  *(Phase numbers 7/8 left unchanged to stay aligned with
  `IMPLEMENTATION-ORDER.md` — apply the same "Phase 6 removed" edit there.)*
- [ ] **Phase 7** — pgvector migration, benchmark delta vs ChromaDB
- [ ] **Phase 8** — GraphRAG (after baseline established)

### Review follow-ups (from OPUS-REVIEW-VERIFICATION, do at the mapped phase)
- [ ] **OBS-009** — wire real Chroma/SQLite counts into `/health` `store_parity`
  (currently hardcoded `0`, so it always reports in-sync). Do before Phase 7.
- [ ] **OBS-003** — replace placeholder `expected_source` (`docker-deep-dive.pdf`)
  with real ingested filenames (folds into Phase 4b).

### Review follow-ups (from Fable review 2026-07-05, `docs/reviews/FABLE-REVIEW-2026-07-05.md`)
- [ ] **FBL-001** — `chunks_fts` has no UPDATE trigger: ADR-006 Strategy B upserts
  chunk content and marks removals `status='deleted'` via UPDATE, so BM25 would serve
  stale/deleted content. Add UPDATE trigger (new `003` migration) at Phase 2 start.
- [ ] **FBL-002** — `eval/scorer.py` matches `expected_source` inconsistently:
  Retrieval@k uses exact list membership, MRR uses substring. Pick one (exact match
  on ingested filename) when populating `expected_source` in Phase 4b.
- [ ] **FBL-003** — doc drift cleanup (one `docs:` commit at end of Phase 1a):
  duplicated ADR-010 text block in DEV-RAG-ARCHITECTURE.md; stale "expect 29" test
  count in CLAUDE.md; IMPLEMENTATION-ORDER.md Phase 1a/1b relabel (structure+enrich
  deferred to 1b).
- [ ] **FBL-004** — estimate Stage 5 enrichment API cost from Phase 1a's real chunk
  count before green-lighting Phase 1b (per-chunk Claude calls × corpus size).

---

## Active — dev-rag Corpus Building

Books and sources to ingest as the system comes online:

### DevOps Domain
- [ ] Docker Deep Dive (Poulton) — ingest first, drives 15 of 26 eval questions
- [ ] A Developer's Essential Guide to Docker Compose (Gkatziouras, Packt 2023) —
  dedicated Compose coverage; complements Docker Deep Dive for multi-service
  application patterns, secrets, health checks, and scaling
- [ ] Ansible for DevOps (Geerling) — **already owned**;
  the standard Ansible reference; ingest after Docker books are working
- [ ] Ansible for Real-Life Automation (Madapparambath, Packt 2022) — **already owned**;
  practical production use cases, Ansible Vault for secrets, container
  management, CI/CD integration; complements Geerling — Geerling teaches
  Ansible thoroughly, Madapparambath shows real production application
- [ ] Mastering Ansible, 4th Edition (Freeman, Packt 2021) — **already owned**;
  advanced internals, Python extensions, collections, Vault secrets,
  debugging and error recovery; completes the Ansible trilogy —
  learn → apply → master
- [ ] Additional Ansible book(s) — confirm titles from shelf
- [ ] Mastering Ubuntu Server, 4th Edition (LaCroix, Packt 2024) — **already owned**;
  covers Ubuntu 22.04 LTS, server administration, Ansible automation, container
  orchestration, and security; fills the Linux security reference gap;
  ingest after Docker and Ansible books are working
- [ ] Securing DevOps (Vehent, Manning 2018) — **already owned**;
  test-driven security, continuous security monitoring, risk assessment,
  securing cloud services and web applications; written by Mozilla Firefox
  Operations Security lead; core principles age well despite 2018 publication

### AI Domain (new)
- [ ] Unlocking Data with Generative AI and RAG (Bourne, Packt 2024) — **already owned**;
  covers naïve RAG, hybrid RAG, reranking, query expansion, and RAGAS evaluation;
  check Packt account at home for Second Edition (adds GraphRAG, agentic memory)
  — ingest whichever edition is available
- [ ] RAG-Driven Generative AI (Rothman, Packt 2024) — **recommended purchase**;
  advanced RAG patterns, adaptive RAG with human feedback, knowledge graphs;
  directly applicable to dev-rag architecture decisions
- [ ] A Simple Guide to Retrieval Augmented Generation (Kimothi, Manning) —
  **recommended purchase**; foundational RAG reference, clean structure,
  good companion for the Python AI agent book
- [ ] Using Stable Diffusion with Python (Zhu, Packt) — **already owned**;
  covers diffusers, LoRAs, ControlNet, VRAM management, prompt engineering;
  relevant once Oryx Pro is set up for local image generation;
  **low priority** — ingest after RAG books are working
- [ ] Ingest order: Bourne first (already owned), then Rothman, then Kimothi,
  then Stable Diffusion when Oryx Pro is set up
- [ ] Confirm Python book titles from shelf
- [ ] Five Lines of Code (Clausen) — refactoring with Python examples;
  enables code review queries during Claude Code sessions
- [ ] Practices of the Python Pro (Hillard, Manning) — **already owned**;
  professional software design, modularisation, reducing complexity,
  coding style and application design at scale; complements Five Lines
  of Code well — Clausen gives concrete rules, Hillard gives broader
  design principles
  cryptography, TLS, authentication, OAuth 2.0, attack resistance;
  directly relevant to securing FastAPI backends and the Ansible security project
- [ ] The Art of Unit Testing, 3rd Edition (Osherove & Khorikov, Manning) — **already owned**;
  readable and maintainable tests, fakes/stubs/mocks, isolation frameworks,
  legacy code, organisation-wide test strategies; examples in JavaScript but
  principles are language-agnostic and directly applicable to Python pytest work
- [ ] Prioritise books that cover: internals, async, production patterns,
  packaging, refactoring, security, testing

### Travel Domain
- [ ] Add Crete research documents
- [ ] Add Athens research documents
- [ ] Add any future trip research

---

## Planned — Ansible Security Hardening Project

Full brief: `docs/ansible-security-project.md`

Extend existing `ansible-personal` project with a new
`laptop-security.yml` playbook covering:

- [ ] UFW firewall rules (reuse existing Docker/UFW conflict fix)
- [ ] SSH hardening
- [ ] Automatic security updates
- [ ] Docker daemon hardening
- [ ] Docker socket permissions
- [ ] Development environment security (npm audit, uv, .env files)
- [ ] API key hygiene and rotation reminders
- [ ] Network security (open ports audit)
- [ ] Lynis security audit integration (optional)
- [ ] Trivy Docker image scanning (optional)

**Timing:** Start after dev-rag Phase 1 is running.
**Book connection:** Real-world Ansible chapter for the Python AI agent book.
**Corpus connection:** Ansible books go into the DevOps corpus in dev-rag.

---

## Planned — Python AI Agent Book

- [ ] Finalise chapter outline using Argos as the real-world project arc
- [ ] dev-rag as a featured real-world project (Chapters TBD)
- [ ] Ansible security project as a real-world Ansible chapter
- [ ] Document each implementation decision as it's made — feeds book content

---

## Planned — Argos (Personal AI Orchestration)

- [ ] Resume Argos development after dev-rag Phase 1 is running
- [ ] Connect Argos to dev-rag MCP server (HTTP/SSE mode)
- [ ] Google Calendar, Gmail, Google Drive MCP integrations already connected
- [ ] Add dev-rag as a knowledge source for Argos agents

---

## Deferred / Nice-to-have (revisit only after a working, evaluated RAG baseline)

### Multiple PDF extractors / LLM extractor selection — DECIDED AGAINST 2026-07-05
`pymupdf4llm` is the sole extraction engine (switched from plain PyMuPDF
mid-Phase-1a: markdown output, real tables, headings for free). Do NOT build
multiple extractor tools with LLM per-PDF selection — the corpus is ~6-10
curated books ingested once each, and the pipeline's stage-1 inspection gate
already judges real output quality better than any up-front prediction.
Escape hatch if a future book extracts badly (scanned/OCR, two-column):
add a second extraction function behind `extract_pdf()` and select it with a
per-source config field in the ingest manifest — deterministic, not LLM-chosen.

### Context compression (Headroom) — REMOVED from active build 2026-07-04
RAG works fine without compression; this is a token/cost optimisation, not a
requirement. Revisit only after the core retrieve → rerank → serialise pipeline
is working and evaluated.

- `mcp/compress.py` stays a no-op stub for now; the `headroom` dependency and the
  `compress` extra were removed from `pyproject.toml` so `uv sync` resolves cleanly.
- **GOTCHA when picking this up:** the compression library is **`headroom-ai`** on
  PyPI (you *import* it as `headroom`; currently ~0.28.0) — **NOT** the bare
  **`headroom`**, which is an unrelated command-line agent stuck at 0.2.7. The old
  unsatisfiable `headroom>=0.3.0` pin was exactly that mix-up. Add `headroom-ai` as
  an **optional** extra, never a core dep.
- Then verify `headroom-ai`'s real `compress()` API against
  `planning/headroom-integration-spec.md`, and add an un-mocked smoke test (OBS-008)
  before relying on it.

---

## Backlog — dev-rag Future Phases

- [ ] GraphRAG spec — write when Phase 4 baseline is established
- [ ] Multi-source coverage metric in eval harness
- [ ] Graph-lift metric (after GraphRAG is implemented)
- [ ] Cross-domain `search_all` ranking improvements beyond Phase 5b

---

## Open Questions to Revisit

- [ ] **Eval harness threshold** — is 25 questions enough or do deltas
  need more? Revisit after first `--compare` run.
- [ ] **Structure-aware chunking** — needed or not? Determined by whether
  chunk_boundary eval questions (008, 020) pass or fail. *(Review OBS-007: a
  structure-aware `ingest-pipeline-spec.md` exists; `ingest.py` docstring says
  out-of-scope for first build — reconcile which is authoritative.)*
- [ ] **porter ascii tokenizer** — does flag-level BM25 matching actually
  work? Determined by ablation queries after hybrid search is live.
  *(Review OBS-006: still open; may move to `unicode61` + custom `tokenchars`.)*
- [ ] **Python book titles** — confirm from shelf before ingesting Python domain.
- [ ] **Ansible book titles** — confirm from shelf before ingesting DevOps corpus.

---

*Created Athens, June 2026. Update as items are completed.*
