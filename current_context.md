# Current Context — dev-rag
_Last updated: 2026-07-10_

## Active File
None — `main` is clean and fully pushed. No feature branch in progress.

## Current Step
Today's session (in order): ingested Art of Unit Testing (2nd Ed) and
Writing Great Specifications, both merged — `python` domain now 4 books /
1949 chunks (corpus overall: 12 books / 6354 chunks / 3 domains). Had a
usage-readiness conversation, which surfaced that the MCP server is only
a thin HTTP proxy — the FastAPI backend must be started manually. Live-
tested the reranker (`RERANKER_ENABLED=true`) and found/corrected a real
misunderstanding: the bare flag uses `reranker_candidates=50` (~112s/query),
not `search_all`'s fast `force_rerank_candidates=10` (~15-20s) path — logged
in CLAUDE.md Lessons and a TODO note about adding startup-time visibility
for this.

Then merged `feat/global-mcp-registration`: dev-rag is now registered as a
**user-scope** MCP server (`claude mcp add -s user`), so its tools are
visible in every Claude Code session, not just this repo — matching how
Gmail/Calendar/Drive are always available. Found and fixed a real bug in
the process: `settings.py`'s DB paths are relative, so starting the
backend from outside the repo silently pointed at empty stores (no error).
Added `scripts/serve.sh` (cd's into repo root first) and live-verified
from `/tmp`: real `rag_health` counts, real `search_python` results.
Backend persistence (always-on daemon) was explicitly deferred — see
`docs/TODO.md`'s new "Backend persistence" entry for the options table
(systemd --user is the lead candidate) and re-open trigger.

Also saved two project memories this session:
[[graphrag-graphify-reference]] and [[agent-py-pydantic-ai-capabilities]].

## Next Action
Nothing in progress. Candidates for next session: (a) live with the
manual-start-from-anywhere workflow for a while before deciding on backend
persistence, (b) resume corpus building from `docs/TODO.md`'s backlog
(Rothman/Kimothi for the `ai` domain, Ansible book title confirmation), or
(c) revisit `agent.py`/GraphRAG per the two memories above. No blockers on
any of these — Ed's call which to pick up.

## Done When
N/A — no task in progress.

## Blockers
None. The backend still requires a manual start
(`scripts/serve.sh`, or `uv run uvicorn dev_rag.api:app --host 127.0.0.1
--port 8000` from the repo root) before dev-rag's MCP tools return real
results — this is a deliberate, documented gap (see `docs/TODO.md`), not
an oversight.

## Housekeeping (optional, not blocking)
A backend server (`scripts/serve.sh`, reranker OFF/default) is currently
running in the background, started from `/tmp` during verification. Fine
to leave running; kill by PID (not job number) when no longer wanted.

## Phase
Corpus-building track / MCP registration phase 1 complete. No active
implementation phase.
