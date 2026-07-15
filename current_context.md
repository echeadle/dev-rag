# Current Context — dev-rag
_Last updated: 2026-07-15_

## Active File
None — `feat/agent-ask-route` implemented and live-verified, not yet
merged to `main`. `feat/agent-search-corpus` merged and deleted locally
not yet done (see Housekeeping).

## Current Step
`agent.py`'s `search_corpus` agent is now reachable over HTTP: new
`POST /ask` in `api.py` (`AskRequest` → `await agent.run(query)` →
`{"answer", "query"}`), built lazily per-request via a function-local
import to avoid a circular import with `agent.py` and to keep `/search`
usable on a keyless server. An MCP `ask_dev_rag` tool was considered and
**deliberately not built** — Ed's call via AskUserQuestion: the MCP
consumer (Claude Code) is already an agent that can call the existing
`search_*` MCP tools and synthesize with its own reasoning, so a tool
delegating synthesis to a Haiku sub-agent would be redundant for that
consumer and cost an extra funded API call. 150→153 tests
(`tests/test_ask_route.py`). Live-verified: a real Docker bind-mounts
question got a cited answer; the known BGE-M3 corpus-gap question got the
same honest decline as the CLI; a keyless restart kept `/health`/`/search`
healthy while `/ask` returned a clean 503. Full detail in
`docs/BRANCH-REVIEW-CHECKLIST.md`'s "Agent /ask Route Review" and
`CLAUDE.md`'s current-state log.

## Next Action
Ed to review `feat/agent-ask-route` (checklist steps 1-9 in
`docs/BRANCH-REVIEW-CHECKLIST.md`) and merge to `main` if satisfied. After
that, candidates for next session: (a) resume corpus building from
`docs/TODO.md`'s backlog, or (b) write the GraphRAG spec so
`graph.py`/`search_graph` can finally start. The MCP `ask_dev_rag` tool is
a deliberately-parked option, not a TODO bug — revisit only if a real need
for it shows up (e.g. a non-Claude-Code MCP consumer).

## Done When
- [x] `POST /ask` implemented, tested (153 passed), live-verified
- [ ] Ed reviews and merges `feat/agent-ask-route`

## Blockers
None. `ANTHROPIC_API_KEY` is funded in `.env` and confirmed working via
both the CLI and the new `/ask` route.

## Housekeeping (optional, not blocking)
`feat/agent-search-corpus` was merged with `--no-ff` and still exists as a
local branch (`git branch -d feat/agent-search-corpus` is safe once Ed
confirms nothing else is needed from it) and hasn't been pushed to
`origin` yet. No server running in the background.

## Phase
`agent.py` Phase 8 decomposition — `/ask` HTTP wiring slice complete,
pending merge. No active implementation phase after that.
