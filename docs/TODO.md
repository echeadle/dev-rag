# dev-rag & Related Projects — To-Do List

**Last updated:** June 2026 (Athens)  

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
- [ ] **Phase 6** — Headroom compression
- [ ] **Phase 7** — pgvector migration, benchmark delta vs ChromaDB
- [ ] **Phase 8** — GraphRAG (after baseline established)

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

## Backlog — dev-rag Future Phases

- [ ] GraphRAG spec — write when Phase 4 baseline is established
- [ ] Multi-source coverage metric in eval harness
- [ ] Graph-lift metric (after GraphRAG is implemented)
- [ ] Cross-domain `search_all` ranking improvements beyond Phase 5b
- [ ] Headroom API verification smoke test before Phase 6

---

## Open Questions to Revisit

- [ ] **Eval harness threshold** — is 25 questions enough or do deltas
  need more? Revisit after first `--compare` run.
- [ ] **Structure-aware chunking** — needed or not? Determined by whether
  chunk_boundary eval questions (008, 020) pass or fail.
- [ ] **porter ascii tokenizer** — does flag-level BM25 matching actually
  work? Determined by ablation queries after hybrid search is live.
- [ ] **Python book titles** — confirm from shelf before ingesting Python domain.
- [ ] **Ansible book titles** — confirm from shelf before ingesting DevOps corpus.

---

*Created Athens, June 2026. Update as items are completed.*
