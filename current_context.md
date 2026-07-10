# Current Context — dev-rag
_Last updated: 2026-07-10_

## Active File
On branch `feat/ingest-writing-great-specifications` (not yet merged).

## Current Step
Ingested **Writing Great Specifications** (Nicieja): 539 chunks,
`python` domain now 1949/1949 in_sync (4th python book — this one and
Art of Unit Testing, both merged today, were picked by Ed specifically
as references for improving dev-rag itself, e.g. spec-writing/BDD and
testing-practice content, not just corpus growth). Stage-8 verify
passed, GIL negative re-checked, 6-question baseline reproduces clean,
new baseline `eval/baselines/2026-07-10_python_4books_6q.json`, full
146-test suite passes. Not yet merged to main — branch review checklist
entry written, merge still pending.

Also discussed and saved a project memory
([[agent-py-pydantic-ai-capabilities]]) about Pydantic AI's new
`capabilities` feature as the likely building block for `agent.py`
when that phase starts, and that `agent.py` doesn't strictly need to
wait on GraphRAG despite being bundled with it in ADR-007.

## Next Action
1. Finish this branch: commit, merge to main, push.
2. Have the usage-readiness conversation with Ed — what's needed to
   actually use the RAG system day-to-day (see Blockers below for what's
   already known).

## Done When
- [x] Art of Unit Testing branch reviewed, merged, pushed (2026-07-10)
- [ ] Writing Great Specifications branch merged, pushed
- [ ] Usage-readiness conversation had with Ed

## Blockers
None. Note for the usage conversation: the MCP server (`.mcp.json`,
auto-launched by Claude Code) is only a thin HTTP proxy — the FastAPI
backend (`uv run uvicorn dev_rag.api:app --host 127.0.0.1 --port 8000`)
must be started manually before MCP search tools work. Confirmed
2026-07-10 (a `list_collections` call failed with a connection error
until the backend was started by hand; it's been left running in the
background since, for eval verification). No automation added yet per
"manual first" rule.

## Housekeeping (optional, not blocking)
A `uv run uvicorn` API server process has been running in the background
since 2026-07-10 (started for eval verification during these two
ingests). Fine to leave up for the usage conversation; kill it by PID
(not job number) when done if it's no longer wanted.

## Phase
Corpus-building track, between books. No active implementation phase.
