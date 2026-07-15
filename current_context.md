# Current Context — dev-rag
_Last updated: 2026-07-15_

## Active File
None — `main` is clean, `feat/agent-search-corpus` merged and deleted
locally not yet done (see Housekeeping). Not yet pushed to `origin`.

## Current Step
`agent.py` is no longer a stub: built a `search_corpus`-only Pydantic AI
agent (`Capability` API, `defer_loading=False`, Haiku 4.5 default model),
per the confirmed decomposition that agent.py doesn't need `graph.py`/
GraphRAG to exist first (ADR-007's Phase 8 deferral is unchanged for
GraphRAG itself). Extracted `perform_search()` out of `api.py`'s `/search`
route so the agent tool and the HTTP route share one canonical
`relevance_score` implementation. Advisor review caught two real bugs the
mocked test suite couldn't see (stray `"anthropic:"` prefix on the model
name; missing domain validation on the LLM-chosen tool arg) — both fixed.
146→150 tests. Added `.env.example`. Live-verified end-to-end against the
real Anthropic API after Ed hit and resolved an unrelated billing gotcha
(a Claude subscription doesn't fund the Developer API — separate product/
billing pool; the Claude Agent SDK is the one path that draws from
subscription credit instead, but it's a different framework, not a
drop-in for pydantic-ai — Ed chose to fund the API key instead of
rewriting). Full detail in `docs/BRANCH-REVIEW-CHECKLIST.md`'s "Agent.py
Search_Corpus Review" and `CLAUDE.md`'s current-state log. Merged to
`main` (commit `9747618`).

## Next Action
Nothing in progress. `agent.py` is currently a standalone CLI only
(`uv run python -m dev_rag.agent "question"`) — deliberately NOT wired
into `api.py` (no `/ask` route) or `mcp_server.py` (no MCP tool) yet,
flagged out of scope on the branch. Candidates for next session: (a) live
with the standalone CLI for a while before deciding whether to wire it
into the API/MCP surface (mirrors the backend-persistence precedent —
prove manual first), (b) resume corpus building from `docs/TODO.md`'s
backlog (Ansible book title confirmation, a possible 2nd `ai`-domain
book), or (c) write the GraphRAG spec so `graph.py`/`search_graph` can
finally start. No blockers on any of these — Ed's call which to pick up.

## Done When
N/A — no task in progress.

## Blockers
None. Correction to an earlier draft of this note: the `python -m
dev_rag.agent` CLI does **not** need `scripts/serve.sh` running —
`agent.py` imports `perform_search` directly from `dev_rag.api` and calls
it as a plain in-process function, not over HTTP (confirmed: the live
test earlier ran with zero server processes up). The manual-start
requirement still applies to the MCP `search_*` tools and the `/search`
HTTP route (both go through the FastAPI backend) — just not to this CLI.
This distinction matters for the next-action item below: an `/ask` FastAPI
route would run in-process same as today; an MCP tool would need a design
decision about whether it proxies to a new HTTP route (requires backend
running, consistent with existing MCP tools) or imports the agent directly
into `mcp_server.py` (bypasses the backend, like the CLI, but changes
MCP's current "thin proxy" architecture). The agent's own model calls need
`ANTHROPIC_API_KEY` funded in `.env` (now done, verified working).

## Housekeeping (optional, not blocking)
`feat/agent-search-corpus` was merged with `--no-ff` and still exists as a
local branch (`git branch -d feat/agent-search-corpus` is safe once Ed
confirms nothing else is needed from it) and hasn't been pushed to
`origin` yet. No server running in the background.

## Phase
`agent.py` Phase 8 decomposition (search_corpus slice) complete. No
active implementation phase.
