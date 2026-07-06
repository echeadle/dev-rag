# Current Context — dev-rag
_Last updated: 2026-07-05_

## Active Files
mcp/server.py, mcp/tests/, src/dev_rag/{api,settings}.py, .mcp.json

## Current Step
MCP smoke slice MERGED to main (after Phase 2 merge earlier today):
- e2e stdio smoke tests: MCP server against the real API
- /collections endpoint: real ChromaDB counts per domain
- project .mcp.json registers the dev-rag stdio server
- Live check passed in a real Claude Code session: rag_health (311 devops
  chunks, stores in parity), list_collections, search_devops end-to-end
- reranker_enabled default flipped to False — health was advertising a
  reranker that is still a Phase 3 stub; flip back when reranker.py is real
- Suite 111 passed (tests/ + mcp/tests both collected)

## Next Action
Pick next slice:
1. Ingest second book (Docker Compose PDF) — RECOMMENDED: live check
   confirmed the "bind mount permissions" corpus gap (query returned only
   loosely related passages); also regression-tests the ingest pipeline.
2. Phase 3 reranker — more measurable once the corpus has >1 book.

## Done When (MCP smoke) — ALL MET
- [x] MCP server smoke-tested e2e against the real API (stdio)
- [x] .mcp.json registration works in a real session (live check passed)
- [x] Reviewed by Ed, tests green (111), merged to main

## Blockers
None. Parked: eval baseline P4 (FBL-002/FBL-005 scorer fixes + OBS-003),
structure+enrich (FBL-004 cost gate), reranker P3, GraphRAG P8, headroom-ai.

## Phase
Between phases: Phase 2 + MCP smoke both merged. Next: second-book ingest
(recommended) or Phase 3 reranker.
