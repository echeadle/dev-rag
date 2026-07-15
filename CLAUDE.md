# CLAUDE.md — dev-rag

Project conventions for any Claude (Code or chat) session working in this repo.
Read this before running commands or editing files.

> Reflects the `review/opus-fixes` cleanup: headroom removed (so `uv sync`
> resolves) and `mcp/tests` in the default test path (so a bare `pytest` runs
> all 29). If those aren't merged yet, see "If the branch isn't applied yet" below.

## What this is
A **personal, single-user, local** RAG system — not a production SaaS. Scale is
personal (thousands of docs, one user, local inference). Optimize for clarity and
correctness at that scale; **do not introduce enterprise patterns.**

Stack: Python 3.12, FastAPI, Pydantic AI, ChromaDB (→ pgvector planned), SQLite
FTS5, BGE-M3 embeddings, bge-reranker-v2-m3, NetworkX, Docker Compose, MCP server.

## Self-learning
When I correct you, or you catch yourself making a mistake: before continuing add the lesson as a 
one-line rule under ## Lessons, so it never happens again.

## Lessons

- (Claude adds rules here)
- Check in on context usage at natural checkpoints (end of a merged
  branch, before starting a new plan/phase) — don't let a long,
  tool-heavy session (many subagent spawns, file reads, background tasks)
  run past ~50-60% without proactively suggesting `/compact` or `/clear`.
  Reason: 2026-07-09 session hit 68% usage / 81% of work done above 150k
  context before Ed had to flag it via `/usage` himself — cost and quality
  both degrade in that territory, and I have no way to measure it
  precisely mid-session, so the fix is proactively asking, not waiting to
  notice.
- When killing a background dev server started earlier in a session, kill
  it by the PID captured at launch (`ps aux | grep ...` if the PID was
  lost), never by `kill %1` — each Bash tool call is its own shell, so
  job-table numbers don't reliably survive across calls. Reason:
  2026-07-09, a `uvicorn` server started for the Phase 5b live review sat
  running for over an hour after a later `kill %1` silently killed
  nothing (wrong/empty job table in that call's fresh shell), only caught
  during an unrelated cleanup sweep.
- A background ingest can be killed by the environment (not a crash — no
  traceback, no OOM in `journalctl`) on large books; ~33 min of embedding
  seems to be near a ceiling. If it happens: check whether
  `data/embeddings/{slug}_embeddings.json` was written before assuming
  progress is lost, then resume cheaply with `--start-stage 7` (it reuses
  the file) rather than re-running the whole ~30+ min embed stage. Reason:
  2026-07-09, Mastering Ubuntu Server's ingest (1017 chunks, ~33 min
  embed) was killed right at the stage 6→7 boundary; the embeddings file
  had already been written (the embed stage buffers all vectors in memory
  and writes the JSON once at the very end — no per-batch checkpoint), so
  this specific kill was recoverable, but a kill mid-batch would not have
  been. Worth a pipeline checkpoint improvement if books keep growing
  (tracked in docs/TODO.md backlog).
- `RERANKER_ENABLED=true` on its own applies `settings.reranker_candidates`
  (default 50, ~112s/query on CPU) to EVERY single-domain search — not the
  fast `force_rerank_candidates=10` (~15-20s) path that `search_all` uses.
  Don't tell Ed "single-domain searches will take ~15s" when he turns the
  global flag on — that number is `search_all`'s scoped pool size, not the
  default one. Also: uvicorn runs single-process/single-threaded for this
  CPU-bound work, so firing several searches close together queues them
  serially — a client can hit its own timeout and report an error while
  the request is still running server-side (it'll show up as a delayed
  200 OK in the server log). Reason: 2026-07-10, gave Ed the wrong latency
  estimate when walking him through `RERANKER_ENABLED=true`, then watched
  a `search_ai` call queue behind an earlier `search_all` call and a curl
  test needed a 90s+ timeout before I traced it to `reranker_candidates`
  vs `force_rerank_candidates`.
- When building a Pydantic AI agent, a test suite that mocks the model
  (`FunctionModel`/`TestModel`) and mocks the wrapped tool logic cannot,
  by construction, catch bugs that only manifest at real model
  construction (e.g. a provider-prefixed model name silently surviving
  into `AnthropicModel`, which — unlike `Agent(model=str)` — doesn't
  strip it) or from actually-untrusted LLM-chosen tool arguments (e.g. an
  invalid `domain` string). Before declaring an agent branch done, run a
  cheap no-key/no-network check that exercises exactly the real-model
  construction path (`AnthropicModel(name, provider=...)`, inspect
  `.model_name`) and directly call any tool function with adversarial
  args, not just through the mocked agent loop. Reason: 2026-07-15,
  `feat/agent-search-corpus` — an advisor pass caught both a wrong
  `"anthropic:"` prefix on `settings.agent_model` (would have failed on
  the very first real API call) and a missing domain-validation boundary
  in `search_corpus` (LLM could pass any string, got a silent empty
  result instead of a signal to retry) — the full 149-test mocked suite
  was green through both bugs.

## Toolchain — uv only
- **Use `uv` exclusively. Never call `pip` directly.** Use `uv run …`, `uv add …`,
  `uv sync`.
- **Python 3.12** (pinned). If setting up fresh: `uv python pin 3.12`.
- **Setup:**
  ```
  uv sync                  # resolves cleanly
  ```

## Tests — the full suite is 153 (as of the /ask route, 2026-07-15)
```
uv run pytest              # expect 153 passed (125 in tests/ + 28 in mcp/tests/)
```
The `mcp/tests/` include the fixtures/consumer-alignment tests guarding the two
High review findings (OBS-001/002). **If a bare run reports only the `tests/`
count**, `testpaths` in `pyproject.toml` has regressed to `["tests"]` and is
skipping `mcp/tests` — restore `mcp/tests` to `testpaths` (or run
`uv run pytest tests mcp/tests`). The `tests/` count grows as pipeline stages
are implemented; the invariant to watch is that BOTH directories are collected.
Ingest tests never load real BGE-M3 — the model is always mocked.

## Hard rules
- **Do not revert the canonical `relevance_score` field.** OBS-001 was fixed the
  review's recommended way: one canonical relevance field across producer, all
  consumers, and fixtures. Reverting fixtures to `rrf_score`/`reranker_score`
  reintroduces the exact bug. `rrf_score` may remain only as an optional debug field.
- **ADRs are final.** Architectural decisions live in `DEV-RAG-ARCHITECTURE.md`
  (ADR-001…012). Don't reverse them without flagging a genuine, un-considered risk.
- **Session close:** update `current_context.md` before ending a session (a Stop
  hook checks this).
- **Branch close:** before the final commit on any feature branch, append that
  branch's review section (context paragraphs + numbered steps with expected
  outputs) to `docs/BRANCH-REVIEW-CHECKLIST.md` and add its index bullet at the
  top of that file. A branch without its review section is not ready for Ed's
  review or merge. This is how Ed learns what was done and verifies it himself
  — never skip it because a change "seems small."
- **Code straight to main:** a small isolated code fix committed directly to
  main still gets a short entry (2–3 verify steps with expected output) in
  `docs/BRANCH-REVIEW-CHECKLIST.md` under "Small Fixes Log", in the same
  commit. Docs-only changes are exempt.

## Current state — ingest + hybrid search real (important context)
**Implemented and proven:**
- **Phase 1a (2026-07-05):** `src/dev_rag/ingest/` — thin-slice pipeline
  (extract via pymupdf4llm → clean → chunk 1500/200 → embed BGE-M3 dense →
  load → verify), run as `python -m dev_rag.ingest.pipeline`. Docker Deep Dive
  ingested: 311 chunks, ChromaDB + SQLite + FTS5 at parity. LLM structure/
  enrich deferred (see IMPLEMENTATION-ORDER.md "Ingest Structure + Enrich").
- **Phase 2 (2026-07-05):** `retrieve.py` (dense), `retrieve_sparse.py` (BM25,
  OR-joined terms), `retrieve_hybrid.py` (RRF), `/search` live in all three
  modes with canonical `relevance_score` (per-mode scales — see api.py
  docstring), `/health` real parity counts. E2E tests hit the real endpoint.
  OBS-006 resolved: porter ascii kept (ablation in hybrid-search-spec.md).
- **MCP smoke (2026-07-05):** MCP server smoke-tested e2e over real stdio;
  `.mcp.json` registers it for Claude Code sessions; `/collections` real counts.
  Corpus: 4 DevOps books, 1495 chunks (Deep Dive 311 + Compose guide 272 +
  Ansible for DevOps 499 + Ansible for Real-Life Automation 413, last ingested
  2026-07-06 on `feat/ingest-ansible-real-life`). Current official RRF baseline
  is `eval/baselines/2026-07-06_hybrid_rrf_4books_39q.json` (39 questions, 5
  negatives; R@1 84.6 / R@3 92.3 / MRR 89.4) — supersedes the 37q file (Slice A
  added devops-035/036). The 4th book pushed R@3 off the ceiling and reopened
  the reranker default; the matched gated reranker baseline is
  `_reranker_c10_4books_39q.json` — see ADR-012 and the FBL-006 Slice A note below.
- **Phase 3 (2026-07-06):** `reranker.py` real — bge-reranker-v2-m3 wired into
  hybrid mode with OBS-002 fallback, proven live. **Disabled by default**: on
  CPU it costs ~15 s/query @10 candidates (~112 s @50) vs ~0.15 s RRF-only.
  `RERANKER_ENABLED=true` (no `DEV_RAG_` prefix) enables it per-run. See
  runbook §5b.
- **Phase 4 + 4b (2026-07-06):** eval harness real end-to-end (loader/
  reporter/run_eval implemented; FBL-002/FBL-005 scorer fixes; OBS-003
  resolved — 36 devops questions, 25 with expected_source VERIFIED against
  chunk text). Official baseline `eval/baselines/2026-07-06_hybrid_rrf.json`:
  R@1 92 / R@3 100 / MRR 95.3 / composite 94.1. Reranker A/B: R@3 delta 0 →
  default stays OFF (ADR-012 measured table). **When adding eval questions,
  verify expected_source against data/chunks/*.json — never guess from
  titles.** Runbook §5c.
- **Slice A / FBL-006 (2026-07-06):** the reranker's "0% negative precision"
  was a **units bug** — `CrossEncoder.predict()` returns a sigmoid probability
  in (0,1) but the scorer gated with `reranker_score < 0.0` (logit space), so
  it could never fire. Fixed with a settings-driven `weak_match` flag
  (`settings.reranker_min_score`, default 0.5; API + MCP surface it, scorer
  reads it — a SOFT flag, ranking/R@k unchanged). Eval grew to **39q / 5
  negatives** (added devops-035 Istio, devops-036 Pulumi, grep-verified
  absent). Matched 39q baselines `_hybrid_rrf_4books_39q.json` /
  `_reranker_c10_4books_39q.json`: gated reranker gives neg precision 0→80%
  (4/5) with R@1 96.2 / R@3 100. Residual leak devops-027 (GitLab CI). The
  ADR-012 reranker-default decision is still Ed's (reopen data + latency).
- **Phase 5 (2026-07-08):** second domain populated for the first time —
  `python` domain
  ingested (Five Lines of Code, Clausen: 532 chunks, 338 pages). No pipeline
  code changes needed — domain routing (ChromaDB per-domain collections,
  SQLite `domain` column filtering, `/search`, `/health`, MCP
  `search_python`) was already fully generic; this proved it end-to-end
  with real data. `/health` confirms `python: 532/532 in_sync`, `devops`
  unaffected at 1495. First python-domain eval baseline:
  `eval/baselines/2026-07-08_python_6q.json` (6 questions: R@1/R@3/R@5/MRR/
  chunk_match/composite all **100%**). python-003 (GIL question) was
  reclassified `no_answer: true` — the book (refactoring/optimization,
  TypeScript examples) genuinely never mentions the GIL (grep-verified: 0
  matches), a corpus-coverage gap not a retrieval bug, matching the
  devops-007 (Podman) negative-test convention rather than left as a
  silently-always-failing factual question.
- **Phase 5b (2026-07-09):** `search_all` is now genuinely unified
  cross-domain search, not four domain-blocks concatenated. New
  `SearchRequest.force_rerank` (independent of `settings.reranker_enabled`
  — ADR-012's default stays OFF) lets `search_all` specifically request
  reranking; `mcp_server.py`'s `_handle_search_all` discovers POPULATED
  domains via `/health` (not a hardcoded 4-way split), fans out with
  `force_rerank: true`, and sorts the combined results by
  `relevance_score` — valid because the reranker's cross-encoder score is
  domain-agnostic (RRF is not: "encodes rank, not relevance").
  **Latency correction:** tried offloading rerank to a thread so
  concurrent per-domain calls would overlap — measured WORSE (this is
  CPU-bound, not GIL-bound; reverted). Real cost is **~20s × populated
  domain count** (~40-50s today at 2 domains), not a flat ~20s;
  `SEARCH_ALL_TIMEOUT` raised to 150s. `search_devops`/`search_python`/
  single-domain search are completely unaffected — still ~0.15s, RRF-only,
  by default. 147 tests (was 143).
- **Mastering Ansible ingest (2026-07-09, `feat/ingest-mastering-ansible`):**
  5th DevOps book, no pipeline code changes. 577 chunks (540 pages, 525
  kept post-clean); `devops` domain now 2072/2072 in_sync, `python`
  unaffected at 532. Stage-8 verify needed a second, more distinctive
  query on the first attempt — the initial query scored top-5 entirely
  from `ansible-for-real-life-automation.pdf` (data loaded fine; only the
  smoke-test query was too generic for a domain with 5 competing Ansible
  books). Re-verified with a "Vault IDs" query (44 mentions in this book
  vs. 1 passing mention in RLA) — passed, dist=0.235. **Existing negative
  tests re-checked empirically, not assumed:** this book adds real,
  multi-chunk Podman content (ansible-bender container builds, 18
  mentions) that could plausibly have broken `devops-007`'s Podman
  negative test — verified live via `/search` that it does not crack the
  top 10 for that query; the incidental RLA asides still rank higher.
  GitLab CI / Istio / Pulumi negatives unaffected (0 mentions,
  grep-verified). New official baseline
  `eval/baselines/2026-07-09_hybrid_rrf_5books_39q.json`: R@1 84.6%
  (unchanged), **R@3 92.3→96.2% (+3.8)**, MRR 89.4→89.7 (+0.3), composite
  88.3→90.0 (+1.7) — the 5th book added coverage without eroding anything.
  The one failure (`devops-020`) is the pre-existing, already-documented
  Ansible-source-competition issue, not a new regression.
- **Practices of the Python Pro ingest (2026-07-09,
  `feat/ingest-practices-python-pro`):** 2nd python-domain book, no
  pipeline code changes. 397 chunks (250 pages, 237 kept post-clean);
  `python` domain now 929/929 in_sync, `devops` unaffected at 2072.
  Stage-8 verify passed first try (dist=0.354). `python-003`'s GIL
  negative test re-checked and still holds (0 mentions, grep-verified —
  this is a software-practices book, not internals). **Tried and parked
  a new added-value positive question** (matching the devops-034
  precedent): the two python books turn out to have real semantic
  overlap — coupling, type hints, and even cProfile/pytest-specific
  queries all still retrieved Five Lines of Code's broader
  performance/testing content ahead of this book's more literal coverage
  on dense search, despite sparse/BM25 correctly favoring the right book.
  Rather than force a fragile question by cherry-picking a winning
  phrasing (the exact mistake OBS-003 already warns against), left this
  parked — same call as the devops corpus's own shared-topic questions.
  Existing 6-question baseline reproduces clean: **100% across the board,
  unchanged**, confirming the new book adds coverage without regressing
  anything measured. New baseline
  `eval/baselines/2026-07-09_python_2books_6q.json`.
- **Bourne RAG book ingest — AI domain opened (2026-07-09,
  `feat/ingest-bourne-rag-ai-domain`):** first book in the `ai` domain
  (Unlocking Data with Generative AI and RAG, Bourne). 608 chunks (346
  pages, 334 kept post-clean); `ai` domain now 608/608 in_sync, other
  domains unaffected. Stage-8 verify passed first try (dist=0.270). The
  `ai_questions.yaml` eval set (7 questions) already existed, pre-written
  before any AI content was ingested and gated on nothing
  (`expected_source: null` throughout, meant to be answerable by
  whichever AI-domain book landed first) — ran unmodified against the
  new corpus. All 7 questions retrieve top-1 from Bourne's book;
  retrieval_at_k/MRR/composite read n/a by design (no expected_source to
  score against); chunk_match 80% (4/5 applicable, 2 N/A by design).
  The one chunk_match miss (`ai-005`) is a chunk-boundary keyword
  co-occurrence artifact, not a coverage gap — verified the book has 376
  "retrieval" mentions overall, just not in the specific top-ranked
  chunk (a RAGAS-metrics passage leaning generation-side); left as-is
  rather than loosening the check. First official AI baseline:
  `eval/baselines/2026-07-09_ai_1book_7q.json`.
- **Mastering Ubuntu Server ingest (2026-07-09,
  `feat/ingest-mastering-ubuntu-server`):** 6th DevOps book, no pipeline
  code changes. 1017 chunks (583 pages, 567 kept post-clean); `devops`
  domain now 3089/3089 in_sync. **Background ingest was killed by the
  environment right at the stage 6→7 boundary** (~33 min into embedding,
  no crash/traceback, no OOM in journalctl) — recovered cheaply via
  `--start-stage 7` since the embeddings JSON had already been written;
  see the new Lessons entry above. Stage-8 verify passed on that resumed
  run (dist=0.306). All existing negatives clean (Podman/GitLab/Istio/
  Pulumi: 0 mentions, grep-verified). **Genuine R@3 erosion, not a false
  alarm:** `devops-para-001b` (a paraphrase question expecting Docker
  Deep Dive) flipped from passing to failing — checked live: the correct
  chunk is now ranked #5, crowded out by Ansible content (RLA rank 1,
  Mastering Ansible rank 2) as the larger corpus shifts RRF/BM25
  statistics. This is a recurrence of the exact erosion pattern already
  documented when RLA was first ingested ("recorded not fixed"), not a
  new failure mode. New baseline
  `eval/baselines/2026-07-09_hybrid_rrf_6books_39q.json`: R@1 84.6% (flat),
  R@3 96.2→92.3% (-3.8, back off the ceiling), MRR 89.7→89.2 (-0.5),
  composite 90.0→88.2 (-1.7). Two failures: `devops-020` (pre-existing)
  and `devops-para-001b` (this erosion).
- **Travel domain removed (2026-07-09, `feat/remove-travel-domain`,
  Ed's call):** dev-rag never had travel books to ingest — travel
  research is a web-search task, not a personal-library RAG task.
  Removed as a valid domain everywhere: `settings.valid_domains` (now
  `["devops", "python", "ai"]`), the `search_travel` MCP tool and its
  dispatch/label/description code, the empty `travel_questions.yaml`
  stub, and the domain lists/enums/examples across
  DEV-RAG-ARCHITECTURE.md (premise statement + ADR-002/007/011),
  RUNBOOK.md, README.md, pyproject.toml, and all `planning/*.md` specs.
  Live-verified: `/health`'s `valid_domains` and `store_parity` no
  longer list travel, `POST /search` with `domain: "travel"` is
  correctly rejected, and the MCP `list_tools()` no longer offers
  `search_travel`. Test suite dropped 147→146 (one test removed, several
  others repointed from `travel` to `python`/`ai` fixtures to keep
  multi-domain coverage meaningful). Historical records — past
  `docs/BRANCH-REVIEW-CHECKLIST.md` sections, `docs/reviews/
  OPUS-REVIEW-VERIFICATION.md`, `docs/plans/dev-rag-phase1a-plan.md` —
  were deliberately left untouched; they're accurate records of what was
  true when written, not living specs.
- **Securing DevOps ingest (2026-07-09, `feat/ingest-securing-devops`):**
  7th DevOps book, no pipeline code changes. 708 chunks (401 pages, 390
  kept post-clean); `devops` domain now 3797/3797 in_sync. Ran to
  completion cleanly this time (no environment kill, unlike Mastering
  Ubuntu Server). Stage-8 verify passed first try (dist=0.375). Existing
  negatives re-checked: Podman/Istio/Pulumi still 0 mentions; GitLab (4
  mentions) inspected directly — all incidental (source-hosting option
  lists, a one-line "substitute GitLab for GitHub" aside), no actual
  GitLab CI content, `devops-027` still holds. **A new, different kind
  of erosion — genuine topical competition, not corpus-shift noise:**
  this book is specifically about DevOps security, so for the first time
  a competitor to Docker Deep Dive's security chapter exists on actual
  merit. `devops-006` (source-specific, expected Docker Deep Dive) now
  loses by a hair (0.031 vs 0.0303 — checked live) to Securing DevOps on
  a "container security recommendations" query; `devops-para-001b`'s
  secrets-paraphrase question also now tops with Securing DevOps instead
  of the Ansible books. New baseline
  `eval/baselines/2026-07-09_hybrid_rrf_7books_39q.json`: R@1 84.6→80.8%
  (-3.8), R@3 92.3% (flat), MRR 89.2→86.5 (-2.7), source_precision
  100→83.3% (-16.7, new — the `source_specific` category questions had
  never been contested before), composite 88.2→87.4 (-0.8). Two
  failures: `devops-020` (pre-existing) and `devops-para-001b` (this
  erosion, new top-1 source).
- **agent.py — search_corpus capability (2026-07-15,
  `feat/agent-search-corpus`):** `agent.py` is no longer a stub. Built with
  Pydantic AI's `capabilities` API (`pydantic-ai==2.5.0`, confirmed
  installed): one `Capability(id="search_corpus", defer_loading=False)`
  wrapping the existing hybrid search. `defer_loading=False` was a
  deliberate call, not an oversight — it's the agent's only tool today, used
  on essentially every turn, so deferring would add a `load_capability`
  round trip for zero context savings; revisit once `search_graph` exists
  as a genuine second bundle. Default model is Haiku 4.5
  (`settings.agent_model`, cost-optimized); `search_corpus` defaults to
  RRF-only (`force_rerank=False`, matches ADR-012 and the single-domain MCP
  tools) so the agent can check multiple domains in one turn without
  compounding rerank latency. **One real refactor, disclosed and
  behavior-preserving:** extracted `perform_search()` out of the `/search`
  route in `api.py` so the OBS-001/OBS-002 canonical-`relevance_score`
  logic has exactly one implementation shared by the HTTP route and the
  agent tool, instead of risking a third divergent copy of a bug this
  project has already been bitten by twice. The `/search` HTTP contract is
  unchanged — all 146 pre-existing tests pass unmodified. **Real
  provider construction is lazy by design:** `build_agent()` only
  constructs `AnthropicProvider` when no `model=` override is passed;
  empirically confirmed this session that constructing it with an empty
  `anthropic_api_key` raises `UserError` immediately (not at `.run()`
  time), and this repo has no `.env` / no `load_dotenv()` call anywhere —
  so `dev_rag.agent` must stay importable with zero key configured, which
  the lazy factory guarantees. Tests use `FunctionModel`/`TestModel`
  overrides exclusively — never touches the real Anthropic API, matching
  this project's "never load real models in tests" convention. New
  `tests/test_agent.py` (4 tests): direct `search_corpus` unit test,
  invalid-domain rejection, `build_agent()` raising cleanly without a key,
  and a full `FunctionModel` agent run proving the tool-call → synthesis
  loop actually works. **Advisor review caught two real bugs the mocked
  test suite structurally couldn't see** (every test either mocks
  `perform_search` or overrides the model, so nothing ever built the real
  `AnthropicModel` or called `search_corpus` with an LLM-chosen domain):
  (1) `settings.agent_model` was `"anthropic:claude-haiku-4-5-20251001"` —
  wrong for `AnthropicModel`, which (unlike `Agent(model=str)`'s
  string-inference path) does not strip a provider prefix; the prefixed
  name would have gone on the wire and been rejected as unknown model.
  Fixed to the bare name. (2) `search_corpus` had no domain validation
  (unlike `/search`'s `SearchRequest.domain_must_be_valid`) — an
  LLM-chosen domain is untrusted input at a system boundary (security.md),
  and an invalid one silently returned an empty result list with no
  signal for the model to self-correct on; now raises `ModelRetry` naming
  the valid domains. 146→150 tests. Runnable via
  `uv run python -m dev_rag.agent "question"`. **Live-verified against the
  real Anthropic API (2026-07-15)**, after Ed hit and resolved an
  unrelated gotcha first: a Claude Pro/Max subscription does NOT fund the
  Developer API (`ANTHROPIC_API_KEY`) — separate product, separate
  billing pool; neither pydantic-ai nor Anthropic's raw SDK changes that,
  since pydantic-ai's `AnthropicProvider` just wraps the same official SDK
  hitting the same endpoint. (The Claude Agent SDK is the one path that
  *does* draw from subscription credit instead of API billing, but it's a
  different, opinionated framework — not a drop-in for pydantic-ai's
  `capabilities` API — so Ed chose to fund the API key instead of
  rewriting agent.py.) Once funded: `search_corpus` was called twice by
  the model (tried more than one search before giving up, per its
  instructions) for "What is BGE-M3?" and it correctly declined to
  answer — the `ai` domain's books discuss embeddings/RAG generally but
  don't name BGE-M3 explicitly, a genuine corpus-coverage gap in the same
  category as `python-003`'s GIL negative test, not a bug.
  `search_graph`/`graph.py`/GraphRAG remain deferred and untouched — see
  the dated update on the GraphRAG scope decision in
  DEV-RAG-ARCHITECTURE.md.
- **agent.py wired into HTTP — POST /ask (2026-07-15,
  `feat/agent-ask-route`):** the `search_corpus` agent is no longer
  standalone-CLI-only. New `POST /ask` in `api.py` (`AskRequest` →
  `await agent.run(query)` → `{"answer": ..., "query": ...}`), built lazily
  per-request via a function-local `from .agent import build_agent` (breaks
  the circular import — `agent.py` imports from `api.py` at module level —
  and keeps the server usable for `/search` with no key configured, since
  `build_agent()` raises immediately on an empty key). `async`, not
  streaming: confirmed empirically that `agent.run_sync()` raises inside
  FastAPI's already-running event loop, so the route uses `await
  agent.run(...)`. **A real design choice made explicitly, not picked
  silently:** an MCP `ask_dev_rag` tool (thin proxy to `/ask`, matching
  every existing MCP tool's pattern) was considered and **deliberately not
  built**, per Ed's call via AskUserQuestion — the MCP consumer (Claude
  Code) is already an agent that can call `search_devops`/`search_python`/
  `search_ai`/`search_all` directly and synthesize with its own reasoning,
  so a tool that delegates synthesis to a Haiku sub-agent would be
  redundant for that consumer and cost an extra funded API call for little
  benefit; `/ask` still serves other real consumers (curl, scripts, a
  future UI) without their own LLM. No `mcp/` changes at all this branch.
  150→153 tests (`tests/test_ask_route.py`, 3 new — 503 without a key, a
  `FunctionModel`-driven 200 with the expected synthesized answer, a clean
  502 on agent failure with no exception text leaked to the caller — same
  injection seam as `tests/test_agent.py`, monkeypatching `build_agent`/
  `perform_search` on the `dev_rag.agent` module). **Live-verified
  (2026-07-15):** a real Docker bind-mounts question returned a cited,
  multi-paragraph answer sourced correctly from *A Developer's Essential
  Guide to Docker Compose*; the known BGE-M3 corpus-gap question produced
  the same honest decline as the CLI; restarting the server with
  `ANTHROPIC_API_KEY=""` kept `/health`/`/search` at `"status": "ok"` while
  `/ask` returned a clean `503`, not a crash.

These are still stubs, not working code:
- `graph.py` (unwired — nothing imports it), `mcp/compress.py` (no-op).
  (`agent.py` is no longer a stub — see the search_corpus entry above.)
So contract/fixture/test guarantees are **correct by construction**, not yet proven
against a live pipeline. When implementing a stub, follow the matching `planning/`
spec and add an **end-to-end test hitting the real endpoint** — hand-written
fixtures can't guard a producer that doesn't exist yet.

## Known open items (not bugs to fix blindly)
- **OBS-003** eval `expected_source`: placeholders must become real filenames
  post-ingest (Phase 4b, with FBL-002 + FBL-005 scorer fixes — see docs/TODO.md).
- *(OBS-006 and OBS-009 resolved in Phase 2 — see "Current state" above.)*
- **Context compression (Headroom):** deferred / removed from the build path — see
  the "Deferred" section in `docs/TODO.md`. **Do NOT re-add `headroom`** — the real
  library is `headroom-ai` (imported as `headroom`); bare `headroom` is an unrelated
  CLI. Only revisit after a working, evaluated baseline.
- **GraphRAG:** referenced across the codebase but has **no spec** yet — decide
  scope before implementing `graph.py`.

## Key reference docs
- `docs/RUNBOOK.md` — **how to run everything that currently works** (ingest
  pipeline, store checks, what's still stubbed). Keep it updated every phase.
- `docs/reviews/OPUS-REVIEW.md` — original architecture review
- `docs/reviews/OPUS-REVIEW-VERIFICATION.md` — per-finding re-verification (current)
- `DEV-RAG-ARCHITECTURE.md`, `IMPLEMENTATION-ORDER.md`, `docs/TODO.md`, `planning/*.md`

## If the branch isn't applied yet
Until `review/opus-fixes` is merged: `uv sync` fails on the old `headroom>=0.3.0`
pin — set up with `uv venv --python 3.12 && uv pip install '.[dev]'`, and run tests
with `uv run pytest tests mcp/tests`.
