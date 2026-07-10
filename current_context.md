# Current Context — dev-rag
_Last updated: 2026-07-10_

## Active File
On branch `feat/ingest-art-of-unit-testing` (not yet merged). Next: a
new branch to ingest Writing Great Specifications.

## Current Step
Ingested **The Art of Unit Testing, 2nd Edition** (Osherove): 481
chunks, `python` domain now 1410/1410 in_sync (3rd python book,
alongside Five Lines of Code and Practices of the Python Pro). Corrected
two stale TODO facts against real content (2nd Edition not 3rd; C#/.NET
examples not JavaScript — see docs/TODO.md). Stage-8 verify passed,
GIL negative re-checked, 6-question baseline reproduces clean, new
baseline `eval/baselines/2026-07-10_python_3books_6q.json`, full 146-test
suite passes. Not yet merged to main — branch review checklist entry and
merge still pending.

## Next Action
1. Finish this branch: append its review section to
   `docs/BRANCH-REVIEW-CHECKLIST.md`, commit, merge to main, push.
2. Then ingest **Writing Great Specifications** (Nicieja) into the
   `python` domain (confirmed by Ed 2026-07-10 — same general
   software-craft bucket as Five Lines of Code / Practices of the Python
   Pro / Art of Unit Testing) on a new branch.
3. After that, Ed wants to pause ingesting and discuss what's needed to
   actually *use* the RAG system day-to-day, plus a couple of candidate
   books (not yet named) for improving dev-rag itself.

## Done When
- [ ] Art of Unit Testing branch reviewed, merged, pushed
- [ ] Writing Great Specifications ingested and merged
- [ ] Usage-readiness conversation had with Ed

## Blockers
None. Note for the usage conversation: the MCP server (`.mcp.json`,
auto-launched by Claude Code) is only a thin HTTP proxy — the FastAPI
backend (`uv run uvicorn dev_rag.api:app --host 127.0.0.1 --port 8000`)
must be started manually before MCP search tools work. Confirmed
2026-07-10 (a `list_collections` call failed with a connection error
until the backend was started by hand). No automation added yet per
"manual first" rule.

## Housekeeping (optional, not blocking)
None — all 8 merged local feature branches were deleted 2026-07-10.
Only `main` (plus this in-progress branch) remains locally.

## Phase
Corpus-building track, between books. No active implementation phase.
