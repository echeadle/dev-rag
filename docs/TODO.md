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

- [x] **Phase 1a** — Thin-slice ingest pipeline ✅ 2026-07-05 (extract via
  pymupdf4llm, clean, chunk 1500/200, embed BGE-M3, load, verify; Docker Deep
  Dive live at parity 311/311/311). Structure+enrich (spec stages 3+5) were
  deferred OUT of 1a — tracked in IMPLEMENTATION-ORDER.md under "Ingest
  Structure + Enrich (DEFERRED)", gated on FBL-004; NOT the same as Phase 1b below
- [x] **Phase 1b** — Wire up MCP server, ingest Docker Deep Dive, first query
  ✅ 2026-07-05 (feat/mcp-smoke merged: e2e stdio smoke tests, /collections,
  .mcp.json; live MCP query from a real Claude Code session)
- [x] **Phase 2** — Hybrid search (BM25 + dense + RRF) ✅ 2026-07-05 (pending
  merge). /search live in 3 modes w/ canonical relevance_score; OBS-006 ablation:
  hybrid ≥ dense everywhere, porter ascii kept; e2e tests on the real endpoint.
- [x] **Phase 3** — Cross-encoder reranker (bge-reranker-v2-m3) ✅ 2026-07-06:
  implemented + wired into hybrid (50-candidate pool → top-N), OBS-002
  fallback proven, 14 new tests (12 unit + 2 real-endpoint e2e), verified
  live against the 583-chunk corpus. **Shipped default OFF** (Ed's call):
  measured ~1.5-2 s/pair on CPU → ~15 s/query @10 candidates, ~112 s @50,
  vs ~0.15 s RRF-only, while the informal 2-query quality delta was modest
  (second book already fixed the gap query at RRF level). Enable per-run:
  `RERANKER_ENABLED=true RERANKER_CANDIDATES=10` (no DEV_RAG_ prefix — the
  spec's env name is wrong). **Phase 4 eval decided (2026-07-06): default
  stays OFF** — R@3 delta 0 (already at ceiling), R@1 +4 at ~100× latency;
  see ADR-012's measured table. Re-open when the corpus has R@3 headroom;
  smaller-model option (bge-reranker-base) parked with it.
- [x] **Phase 4** — Evaluation harness running, first baseline established
  ✅ 2026-07-06: loader/reporter/run_eval implemented (scorer/runner already
  real), FBL-002 + FBL-005 fixed, 12 new tests incl. full-harness e2e.
  OFFICIAL BASELINE `eval/baselines/2026-07-06_hybrid_rrf.json`: R@1 92%,
  R@3 100%, MRR 95.3%, composite 94.1% (25 ground-truthed questions).
  Reranker A/B (`_reranker_c10.json`): R@1 +4, R@3 +0, MRR +2.7 at ~100×
  latency → **default stays OFF** per ADR-012's own <+3 R@3 criterion
  (measured table now filled in ADR-012). New finding FBL-006 below.
- [x] **Phase 4b** — Grow eval question set to 25 with expected_source populated
  ✅ 2026-07-06: 36 devops questions (7 new), 25 with expected_source verified
  against chunk artifacts — never guessed from titles. Notables: devops-019
  converted negative→positive (Compose book ch12 covers Terraform+ECS, so the
  old negative broke); devops-027 (GitLab CI) is the replacement negative;
  nulls are deliberate + documented per-question (multi-source or corpus gap).
- [ ] **Phase 5** — Python domain
- [ ] **Phase 5b** — Unified search_all ranking via reranker
  - [ ] Review `search_all` result budget (found in MCP smoke test 2026-07-05):
    the MCP fan-out fallback splits `n_results // 4` across domains
    (`mcp/mcp_server.py`), so a request for 8 returns only 2 while devops is
    the sole populated domain. Left as-is deliberately — the real fix is the
    unified cross-domain endpoint (OBS-004 gate), not patching the fallback.
- [ ] ~~**Phase 6** — Headroom compression~~ **REMOVED from the build path**
  (2026-07-04) — deferred to nice-to-have; see **Deferred** below.
  *(Phase numbers 7/8 left unchanged to stay aligned with
  `IMPLEMENTATION-ORDER.md` — apply the same "Phase 6 removed" edit there.)*
- [ ] **Phase 7** — pgvector migration, benchmark delta vs ChromaDB
- [ ] **Phase 8** — GraphRAG (after baseline established)

### Review follow-ups (from OPUS-REVIEW-VERIFICATION, do at the mapped phase)
- [x] **OBS-009** — ✅ 2026-07-05 (Phase 2): `/health` reports real per-domain
  counts; drift flips status to `degraded` (proven by e2e test).
- [x] **OBS-003** — ✅ 2026-07-06 (Phase 4b): all placeholders replaced with
  real ingested filenames, verified against chunk text; python-004's
  not-ingested placeholder nulled with a note.

### Review follow-ups (from Fable review 2026-07-05, `docs/reviews/FABLE-REVIEW-2026-07-05.md`)
- [x] **FBL-001** — ✅ 2026-07-05 (Phase 2 stage 0): migration
  `003_fts_update_trigger.sql` keeps chunks_fts correct on UPDATE (content
  rewrite + status flips), tests in tests/test_migrations.py.
- [x] **FBL-002** — ✅ 2026-07-06 (Phase 4): exact match everywhere (MRR was
  substring); regression-tested in tests/test_eval.py.
- [x] **FBL-003** — doc drift cleanup ✅ 2026-07-05: removed duplicated ADR-010
  block; CLAUDE.md test count updated (70) + ingest marked implemented;
  IMPLEMENTATION-ORDER.md Phase 1a marked complete with deferred structure+enrich
  split into its own unambiguous section; phase1a plan's chunks-column list
  corrected to match migrations/001.
- [ ] **FBL-004** — estimate Stage 5 enrichment API cost from Phase 1a's real chunk
  count before green-lighting Phase 1b (per-chunk Claude calls × corpus size).
- [x] **FBL-005** — ✅ 2026-07-06 (Phase 4): negative precision is mode-aware —
  reranker logit < 0, dense cosine < 0.5, and **None (n/a) under plain RRF**
  since RRF encodes rank, not relevance. Reporter says so explicitly.
- [ ] **FBL-006** — reranker logits do NOT reject near-domain negatives: all 3
  no_answer questions (Podman/Nomad/GitLab CI) drew confidently positive logits
  on near-miss content → negative precision 0% in the reranker A/B
  (2026-07-06). The corpus answers out-of-scope questions with lookalike
  content and no layer currently gates it. Ideas when picked up: calibrate a
  higher logit threshold on a labelled negative set; or surface "weak match"
  warnings in the MCP layer. Note: composite scores are not comparable between
  runs whose negative metric differs in computability.
  **New data 2026-07-06 (4-book reranker A/B):** still negative precision 0% /
  hallucination 100% — but now with a concrete mechanism. devops-007's
  reranker top-1 is the RLA book's Podman-*aside* chunk ("if you use Podman,
  see containers.podman"): the 4th book handed the reranker a fresh
  near-miss to confidently mis-rank. Ingesting more books makes this worse,
  not better, until a gating layer exists.

### Reranker default (ADR-012) — REOPENED 2026-07-06 by measured headroom
- The 4th book pushed RRF R@3 off the ceiling (100→92), creating the first
  real reranker headroom. Reranker A/B on the identical 4-book corpus
  (candidates=10, `2026-07-06_reranker_c10_4books.json` vs
  `2026-07-06_hybrid_rrf_4books.json`): **R@1 84→96 (+12), R@3 92→100 (+8),
  MRR 89→98 (+9)**, chunk_match 80.8→92.3, paraphrase 0→100. The reranker
  recovers exactly the cross-book erosion.
- ADR-012's own reopen criterion (flip when R@3 delta ≥ +3) is now met (+8),
  where the earlier same-candidates A/B saw R@3 delta 0. **Insight: reranker
  value is corpus-dependent** — headroom appeared only once cross-book
  competition did, not from any config change.
- BUT latency is unchanged (~100×, ~21 s/query @10 on CPU), and FBL-006
  (negatives) is now the visible failure mode. So the *tradeoff* genuinely
  reopens; it is NOT automatically "turn it ON." **Decision is Ed's** (ADRs
  are final) — recorded here, ADR-012 decision line left OFF pending review.
  Composite (87.8→82.6) is NOT the metric to read here: it fell only because
  neg-precision/hallucination went n/a→computable (see FBL-006 note); every
  comparable retrieval metric improved.

---

## Active — dev-rag Corpus Building

Books and sources to ingest as the system comes online:

### DevOps Domain
- [x] Docker Deep Dive (Poulton) — ✅ 2026-07-05 (Phase 1a): 311 chunks
- [x] A Developer's Essential Guide to Docker Compose (Gkatziouras, Packt 2023) —
  ✅ 2026-07-05: 272 chunks, corpus parity 583/583/583. Lesson: the pipeline's
  DEFAULT_QUERY verify smoke test is written for Deep Dive, so stage 8 failed
  until re-run with a Compose-specific `--query` (data was fine; verify-only).
  For future ingests always pass a book-specific `--query`, or make it required.
- [x] Ansible for DevOps (Geerling) — ✅ 2026-07-06: 499 chunks, corpus
  parity 1082/1082/1082; stage-8 verify passed first try with the
  book-specific --query (inventory question). Post-ingest eval re-baseline
  `eval/baselines/2026-07-06_hybrid_rrf_3books.json`: R@1 88 (-4: devops-025's
  Compose chunk slipped to #2), R@3 100 (held), MRR 93.3, composite 93.5.
  devops-027 GitLab negative re-verified (mentions incidental; Jenkins
  chapter + GH Actions now strong near-miss bait — the test got harder).
- [x] Ansible for Real-Life Automation (Madapparambath, Packt 2022) —
  ✅ 2026-07-06 (`feat/ingest-ansible-real-life`): 413 chunks, corpus parity
  1495/1495/1495. Screenshot-heavy Packt book (480 pages → 413 chunks;
  literal commands live in figures, so text chunks are thinner). Stage-8
  verify passed first try with a Jenkins-CI/CD `--query`. Negatives
  re-verified by reading hits: all 3 hold (Nomad 0, Podman 4 "use
  containers.podman instead" asides, GitLab 9 incidental — its CI/CD chapter
  is Jenkins-based); 007 + 027 notes updated. RRF re-baseline
  `2026-07-06_hybrid_rrf_4books.json`: R@1 84 (-4), **R@3 92 (-8, off the
  ceiling for the first time)**, MRR 89, paraphrase 0 (-100), composite 87.8
  — all erosion from the RLA book competing with the Docker books
  (devops-020 image-push, devops-para-001b secrets paraphrase), recorded not
  fixed. **This R@3 drop reopened the reranker question** — see FBL-006 and
  ADR-012 below.
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
