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
- [x] **Phase 5** — ✅ 2026-07-08. Ingested Five Lines of Code (Clausen)
  under `domain=python` (532 chunks, 338 pages) — no pipeline code changes
  needed, domain routing was already fully generic. Verified end-to-end:
  `/health` shows `python: 532/532 in_sync`; live `search_python` MCP
  query confirmed real content; `expected_source` populated for
  python-004/005/006 (verified against real chunk text, not guessed).
  First python baseline: `eval/baselines/2026-07-08_python_6q.json`
  (R@1/R@3/R@5/MRR/chunk_match/composite all **100%**). python-003 (GIL
  question) reclassified `no_answer: true` — grep-verified the book
  (refactoring/optimization-focused, TypeScript examples) never mentions
  the GIL, matching the devops-007 (Podman) negative-test convention.
  python-001/002 stay `expected_source: null` — never gated on this book.
- [x] **Phase 5b** — ✅ 2026-07-09. Unified `search_all` ranking, scoped to
  `search_all` only (Ed's call) — not a global ADR-012 reversal.
  `SearchRequest` gains `force_rerank: bool` (independent of
  `settings.reranker_enabled`); `lifespan()` now always loads the reranker
  model at startup (cheap, cached weights) so it's ready regardless of the
  default. `_handle_search_all` (`mcp/mcp_server.py`) was rewritten: drops
  the dead "try unified endpoint" call (POST /search always 422s without a
  domain), discovers POPULATED domains via `/health` instead of a
  hardcoded 4-way split, fans out with `force_rerank: true`, and — the
  actual fix — **sorts the combined results by `relevance_score`**, valid
  because the reranker's cross-encoder score is domain-agnostic (RRF is
  not, per the `weak_match` docstring: "encodes rank, not relevance").
  New `settings.force_rerank_candidates` (10, not the default
  `reranker_candidates` 50) keeps force_rerank calls from taking the
  measured ~112s/query-at-50 path.
  **Latency finding (corrects the original plan):** tried
  `asyncio.to_thread` to let concurrent per-domain reranks overlap —
  measured WORSE (50s vs 40s for 2 domains), not better. This is
  CPU-bound, not GIL-bound (the CrossEncoder likely already runs its own
  internal thread pool), so reverted. **Real cost is ~20s × populated
  domain count**, not a flat ~20s — `SEARCH_ALL_TIMEOUT` raised to 150s
  and the tool description states the honest per-domain cost.
  4 new tests, 3 existing ones updated for `/health`-driven discovery;
  147 total (was 143).
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
- [x] **FBL-004** — ✅ 2026-07-08. Estimated Stage 5 enrichment API cost against
  the real corpus (1495 chunks, 4 books — not the 311/book placeholder in the
  spec's original comment). Per call: ~800 input tokens (1491-char avg content
  + fixed prompt/schema template) and ~400 output tokens average (1000 cap
  worst case). At Sonnet-tier pricing: **~$12.56 sync / ~$6.28 via Batch API**
  for average output, **~$26/~$13 worst case** if every call hit the
  `max_tokens` cap. **Conclusion: cost is a non-issue at this corpus scale** —
  the gate that blocked Phase 1b is cleared. (Back-of-envelope, no live
  `count_tokens` call — no API credentials configured in this environment —
  but the "cheap" conclusion holds even at 2x the estimate.) Note: the spec's
  `model="claude-sonnet-4-6"` should be revisited against the then-current
  recommended model whenever Phase 1b is actually implemented. Whether to
  actually greenlight Phase 1b is a separate scope decision, still Ed's.

**Phase 1b (structure+enrich) — Ed's call, 2026-07-08: DEFER.** With the
cost gate cleared, we scoped a narrower first slice (structure-aware
chunking only, no LLM enrichment) and investigated before writing an
implementation plan. Two things killed the concrete justification:
1. The eval failure this was meant to fix (`devops-020`,
   `chunker_splits_procedure`) no longer fails because of chunk splitting —
   it fails because a newer Ansible book now outranks Docker Deep Dive for
   that query (source competition). The gated reranker (Slice A / FBL-006)
   already fixes it — it was absent from the reranker-run failure list
   reproduced live this session.
2. `planning/ingest-pipeline-spec.md` Stage 3 (`structure.py`) is
   LLM-based, not regex-based, and its boundary-detection logic is an
   unfinished TODO stub in the spec itself — not ready-to-wire, needs real
   design. A faithful implementation also changes the `Chunk` dataclass
   shape, rippling through `load.py`, `retrieve*.py`, `embed.py`,
   `api.py`, `mcp_server.py`, and eval fixtures.

**Decision: hold structure+enrich entirely** (including a metadata-only
version) until a real, currently-unfixed eval failure actually points at a
chunk-boundary defect — not source competition, not something the
reranker already handles.

- [x] **FBL-005** — ✅ 2026-07-06 (Phase 4): negative precision is mode-aware —
  reranker logit < 0, dense cosine < 0.5, and **None (n/a) under plain RRF**
  since RRF encodes rank, not relevance. Reporter says so explicitly.
- [x] **FBL-006** — ✅ 2026-07-06 (Slice A, `feat/fbl006-negative-gating`).
  **Root cause was a units bug, not a blind reranker.** `CrossEncoder.predict()`
  returns a SIGMOID probability in (0,1); the scorer gated negatives with
  `reranker_score < 0.0` (a raw-logit cutoff), which a probability can never
  satisfy → 0% was mechanically forced, not measured. (The dense branch already
  used the correct `< 0.5`.) **Fix:** a settings-driven `weak_match` flag —
  when the reranker ran, a hit below `settings.reranker_min_score` (default 0.5
  = sigmoid midpoint = logit 0) is flagged low-confidence. It is a SOFT signal,
  not a drop: ranking/R@k unchanged by construction; the API + MCP surface the
  flag and eval/scorer.py reads it (measures the gate that ships, not a scorer
  knob). Grew the negative set 3→5 (added devops-035 Istio orthogonal control,
  devops-036 Pulumi near-domain, both grep-verified absent). **Result (39q,
  gated, `_reranker_c10_4books_39q.json`):** negative precision 0→80% (4/5),
  R@1 96.2 / R@3 100 held. **Residual:** devops-027 (GitLab CI, 0.655) still
  leaks — the corpus's whole Jenkins chapter makes it a genuine near-domain
  hit that outscores 3 real positives; 0.5 is held on principle rather than
  tuned past it. This residual + ~100× latency feed the still-open ADR-012
  default decision.

### Reranker default (ADR-012) — DECIDED 2026-07-08: stays OFF
- The 4th book pushed RRF R@3 off the ceiling (100→92), creating the first
  real reranker headroom. **Matched 39q A/B (candidates=10, gated,
  `_reranker_c10_4books_39q.json` vs `_hybrid_rrf_4books_39q.json`):**
  **R@1 84.6→96.2 (+11.5), R@3 92.3→100 (+7.7), MRR 89.4→98.1 (+8.7)**,
  chunk_match 81.5→92.6, composite 88.3→94.7. The reranker recovers exactly
  the cross-book erosion.
- ADR-012's own reopen criterion (flip when R@3 delta ≥ +3) is met (+7.7),
  where the earlier same-candidates A/B saw R@3 delta 0. **Insight: reranker
  value is corpus-dependent** — headroom appeared only once cross-book
  competition did, not from any config change.
- **FBL-006 is now RESOLVED as a metric bug** (see above): with the sigmoid
  gate, negative precision is 0→80% (4/5). Read the per-metric deltas as the
  rigorous comparison (all clean, all up). Composite (88.3→94.7) is only
  DIRECTIONAL — the runs weight the negative term differently (RRF excludes it,
  the reranker includes neg=0.80), so it's not the same construct; it does
  dispel the earlier "82.6" scare (purely the 0% artifact) but isn't a precise
  gain.
- What still weighs against default-ON: ~100× latency (~15–20 s/query @10 on
  CPU) and the ONE residual leak (devops-027 GitLab CI, a confident
  near-domain hallucination the Jenkins chapter feeds). So the *tradeoff*
  genuinely reopened; it was NOT automatically "turn it ON."
- **Decision (Ed, 2026-07-08): stays OFF.** For a single-user tool used
  interactively via MCP (search may be called many times per session), the
  ~100× latency outweighs the quality gain as a default. `RERANKER_ENABLED=true`
  stays available per-run. Not a standing open item anymore — reopen only on a
  material change (GPU inference, caching, further corpus growth).
- **TODO (nice-to-have, not urgent):** log the active reranker candidate
  count and its rough per-query latency at server startup (e.g. "reranker
  enabled: candidates=50 (~112s/query) — set RERANKER_CANDIDATES=10 for
  ~15s/query interactive use") whenever `RERANKER_ENABLED=true`. Right now
  the split between `reranker_candidates` (default 50, meant for deliberate
  quality A/B work) and `force_rerank_candidates` (10, `search_all`'s fixed
  fast path) is documented only in code comments — someone bare-enabling
  the flag has no visible warning before hitting the slow path. Reason:
  2026-07-10, Ed turned the reranker on for interactive use and got the
  ~112s/query default silently, which queued several searches serially and
  took minutes to trace back to `reranker_candidates` vs
  `force_rerank_candidates`. Not a design bug (the two-tier split is
  deliberate — see above) — just missing at-runtime visibility.

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
- [x] Mastering Ansible, 4th Edition (Freeman, Packt 2021) — ✅ 2026-07-09
  (`feat/ingest-mastering-ansible`): 577 chunks, 540 pages (525 kept),
  corpus parity 2072/2072/2072. Completes the Ansible trilogy — learn
  (for DevOps) → apply (Real-Life Automation) → master. Stage-8 verify
  needed a re-run with a more distinctive query ("Vault IDs", 44
  mentions vs. RLA's 1 passing mention) after the first attempt's query
  scored entirely from RLA's competing content — data was fine, only the
  smoke-test query was too generic. Re-verified existing negatives live
  (not assumed): this book's substantial ansible-bender/Podman container
  section (18 mentions) does not crack the top-10 for the `devops-007`
  Podman negative question. New baseline
  `eval/baselines/2026-07-09_hybrid_rrf_5books_39q.json`: R@1 84.6%
  (flat), R@3 92.3→96.2% (+3.8), MRR +0.3, composite +1.7 — pure gain,
  no erosion. `devops-020`'s one failure is the pre-existing documented
  source-competition issue, unrelated to this ingest.
- [ ] Additional Ansible book(s) — confirm titles from shelf
- [x] Mastering Ubuntu Server, 4th Edition (LaCroix, Packt 2024) — ✅
  2026-07-09 (`feat/ingest-mastering-ubuntu-server`): 1017 chunks, 583
  pages (567 kept), `devops` domain now 3089/3089 in_sync (6th book).
  Background ingest was killed by the environment ~33 min into embedding
  (no crash — recovered via `--start-stage 7`, no re-embed needed; see
  CLAUDE.md Lessons). Existing negatives (Podman/GitLab/Istio/Pulumi)
  clean. New 39q baseline
  `eval/baselines/2026-07-09_hybrid_rrf_6books_39q.json`: R@3 dropped
  96.2→92.3% (-3.8) — `devops-para-001b` flipped to failing, a
  recurrence of the same Ansible-vs-Docker erosion pattern already
  recorded at the RLA ingest (not a new bug — recorded, not fixed).
- [x] Securing DevOps (Vehent, Manning 2018) — ✅ 2026-07-09
  (`feat/ingest-securing-devops`): 708 chunks, 401 pages (390 kept),
  `devops` domain now 3797/3797 in_sync (7th book). Ran cleanly, no
  environment interruption. Existing negatives re-checked (GitLab's 4
  mentions all incidental, `devops-027` holds). **New erosion pattern —
  genuine topical competition**, not corpus-shift noise: this is the
  first security-*specific* book in the corpus, so it now legitimately
  edges out Docker Deep Dive's security chapter on security-themed
  questions (checked live: `devops-006` loses by 0.031 vs 0.0303).
  New baseline `eval/baselines/2026-07-09_hybrid_rrf_7books_39q.json`:
  R@1 84.6→80.8% (-3.8), source_precision 100→83.3% (-16.7, first time
  this category has been contested), composite -0.8.

### AI Domain
- [x] Unlocking Data with Generative AI and RAG (Bourne, Packt 2024) — ✅
  2026-07-09 (`feat/ingest-bourne-rag-ai-domain`): **opens the AI domain**
  — first book, 608 chunks, 346 pages (334 kept). `ai` domain now
  608/608 in_sync. Stage-8 verify passed first try. The 7-question
  `ai_questions.yaml` eval set was pre-written before any AI content
  existed (gated on nothing, `expected_source: null` throughout) — ran
  unmodified against the new corpus, all 7 questions retrieve top-1 from
  this book. retrieval_at_k/MRR/composite read n/a by design (no
  expected_source to score against); chunk_match 80% (4/5 applicable),
  with the one miss (ai-005) verified as a chunk-boundary keyword
  co-occurrence artifact, not a coverage gap (376 "retrieval" mentions
  in the book overall). First AI baseline:
  `eval/baselines/2026-07-09_ai_1book_7q.json`.
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
- [x] Five Lines of Code (Clausen) — ✅ ingested 2026-07-08 (Phase 5, 532
  chunks). Correction: code examples are **TypeScript, not Python**
  (this entry previously said "with Python examples" — verified wrong
  against real ingested content); the refactoring rules/principles apply
  language-agnostically, same as Art of Unit Testing's JS examples below.
- [ ] Confirm remaining Python book titles from shelf (Art of Unit Testing,
  already owned — see below)
- [x] Practices of the Python Pro (Hillard, Manning) — ✅ 2026-07-09
  (`feat/ingest-practices-python-pro`): 397 chunks, 250 pages (237
  kept), `python` domain now 929/929 in_sync (2nd book, alongside Five
  Lines of Code). Stage-8 verify passed first try. `python-003`'s GIL
  negative re-checked, still holds. **Tried and parked an added-value
  eval question** (matching the devops-034 precedent — no positive
  question pointed at this book's unique content): coupling, type
  hints, and cProfile/pytest-specific queries all still retrieved Five
  Lines of Code's content first on dense search despite this book being
  the literal/BM25 match — genuine semantic overlap between the two
  python books, not a bug. Declined to force a fragile question by
  cherry-picking a winning phrasing (same principle as OBS-003: never
  guess/force ground truth). Existing 6-question baseline reproduces
  clean, 100% unchanged. New baseline
  `eval/baselines/2026-07-09_python_2books_6q.json`.
  cryptography, TLS, authentication, OAuth 2.0, attack resistance;
  directly relevant to securing FastAPI backends and the Ansible security project
- [x] The Art of Unit Testing, 2nd Edition (Osherove, Manning) — ✅ 2026-07-10
  (`feat/ingest-art-of-unit-testing`): 481 chunks, 294 pages (281 kept),
  `python` domain now 1410/1410 in_sync (3rd book, alongside Five Lines of
  Code and Practices of the Python Pro). Stage-8 verify passed first try
  (dist=0.450). **Two stale TODO facts corrected against real content,
  not guessed:** (1) previous entries said "3rd Edition" — wrong, the file
  actually present is the 2nd Edition (Osherove solo, no Khorikov); (2)
  previous entries said "examples in JavaScript" — wrong, grep-verified
  the book is C#/.NET-based (200+ NUnit, 161 .NET, 74 Typemock, 28 C#, 19
  Rhino Mocks mentions vs. 12 incidental JavaScript ones). Principles
  (fakes/stubs/mocks, isolation frameworks, Humble Object pattern, legacy
  code, org-wide test strategy) are still language-agnostic and directly
  applicable to Python pytest work. `python-003`'s GIL negative re-checked,
  still holds (0 mentions, grep-verified). Existing 6-question baseline
  reproduces clean, 100% unchanged. New baseline
  `eval/baselines/2026-07-10_python_3books_6q.json`.
- [x] Writing Great Specifications (Nicieja, Manning) — ✅ 2026-07-10
  (`feat/ingest-writing-great-specifications`): 539 chunks, 308 pages
  (299 kept), `python` domain now 1949/1949 in_sync (4th book —
  specification-by-example, BDD/Gherkin, acceptance testing; general
  software-craft, same bucket as Five Lines of Code / Practices of the
  Python Pro / Art of Unit Testing, per Ed's call 2026-07-10). Stage-8
  verify passed first try (dist=0.376). `python-003`'s GIL negative
  re-checked, still holds (0 mentions, grep-verified). Existing
  6-question baseline reproduces clean, 100% unchanged. New baseline
  `eval/baselines/2026-07-10_python_4books_6q.json`. Ingested as a
  reference for improving dev-rag itself (alongside the RAG book and Art
  of Unit Testing), not purely as corpus growth — Ed's next step is a
  pause on ingesting to discuss RAG-system usage readiness.
- [ ] Prioritise books that cover: internals, async, production patterns,
  packaging, refactoring, security, testing

**Travel domain removed 2026-07-09 (Ed's call).** dev-rag never had any
travel books to ingest — travel research is a web-search task, not a
personal-library RAG task. Removed as a valid domain everywhere:
`settings.valid_domains`, the `search_travel` MCP tool, the empty
`travel_questions.yaml` stub, and travel references across
DEV-RAG-ARCHITECTURE.md/RUNBOOK.md/README.md. See
`feat/remove-travel-domain`.

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

- [x] **Eval "added value" blind spot** — ✅ 2026-07-06
  (`feat/eval-rla-positive`): added devops-034, the first eval positive
  targeting the RLA book's unique content ("multibranch pipeline in Jenkins
  to run Ansible", exclusive to RLA). Before this, no question pointed at an
  Ansible book, so a new book's ingest could only be measured as *erosion*.
  New 37q RRF baseline `2026-07-06_hybrid_rrf_4books_37q.json` (R@1 84.6 / R@3
  92.3 / MRR 89.4). Still open: Geerling (ansible-for-devops.pdf) has no
  positive either — add one when convenient. Shared-topic candidate parked:
  "manage Docker containers using Ansible" (RLA top-1/2 but Geerling competes).
- [ ] GraphRAG spec — write when Phase 4 baseline is established
- [ ] Multi-source coverage metric in eval harness
- [ ] Graph-lift metric (after GraphRAG is implemented)
- [ ] Cross-domain `search_all` ranking improvements beyond Phase 5b
- [ ] **Ingest pipeline: checkpoint the embed stage.** Found 2026-07-09
  (Mastering Ubuntu Server ingest, killed by the environment ~33 min into
  embedding): stage 6 buffers all vectors in memory and writes
  `data/embeddings/{slug}_embeddings.json` once at the very end — no
  per-batch checkpoint. That specific kill happened to land right after
  the last batch finished, so `--start-stage 7` recovered cheaply, but a
  kill mid-batch would have lost the entire ~30+ min embed run with
  nothing to resume from. Worth adding incremental batch-level
  checkpointing if books keep growing past ~500 pages (embed time scales
  with page/chunk count — this was the 3rd-largest book so far).

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
- [x] **Python book titles** — Five Lines of Code confirmed and ingested
  2026-07-08 (Phase 5); Practices of the Python Pro confirmed and ingested
  2026-07-09. Art of Unit Testing confirmed 2026-07-10 as the **2nd
  Edition** (file present in `data/books/` — earlier entries wrongly said
  3rd Edition).
- [ ] **Ansible book titles** — confirm from shelf before ingesting DevOps corpus.

---

*Created Athens, June 2026. Update as items are completed.*
