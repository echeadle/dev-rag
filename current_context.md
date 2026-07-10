# Current Context — dev-rag
_Last updated: 2026-07-09_

## Active File
src/dev_rag/settings.py, mcp/mcp_server.py, eval/loader.py, eval/run_eval.py
(code changes), plus tests/*, mcp/tests/*, and doc/spec updates across
DEV-RAG-ARCHITECTURE.md, RUNBOOK.md, README.md, pyproject.toml,
docs/TODO.md, planning/*.md.

## Current Step
Removed the `travel` domain from dev-rag entirely, on branch
`feat/remove-travel-domain`, NOT yet merged — Ed's call: no travel books
exist or are planned, travel research belongs in web search, not this
RAG system. Full removal, not just docs cleanup:
- `settings.valid_domains` no longer includes `travel`
- `search_travel` MCP tool removed (registration, dispatch, label, docs)
- `data/evaluation/travel_questions.yaml` deleted (was a never-populated stub)
- `eval/loader.py`/`eval/run_eval.py` no longer reference it
- Tests repointed from `travel` fixtures to `python`/`ai` fixtures where a
  second domain was needed for meaningful multi-domain coverage
- DEV-RAG-ARCHITECTURE.md's premise statement + ADR-002/007/011,
  RUNBOOK.md, README.md, pyproject.toml, and all `planning/*.md` specs
  updated
- Historical records deliberately left alone: past
  docs/BRANCH-REVIEW-CHECKLIST.md sections, docs/reviews/
  OPUS-REVIEW-VERIFICATION.md, docs/plans/dev-rag-phase1a-plan.md

Live-verified, not just unit-tested: `/health` no longer lists travel,
`POST /search {"domain": "travel"}` is correctly rejected with a clear
validation error, and the MCP `list_tools()` no longer offers
`search_travel`.

## Next Action
1. Write Branch Review Checklist section.
2. Ed reviews + merges.

## Done When
- [x] travel removed from settings.valid_domains
- [x] search_travel MCP tool fully removed
- [x] travel_questions.yaml deleted, loader/run_eval updated
- [x] All tests updated and passing (146, was 147)
- [x] Live-verified: /health, /search rejection, MCP tool list
- [x] Docs/specs updated (architecture, runbook, README, pyproject, planning/*)
- [ ] Branch Review Checklist section written
- [ ] Ed reviews + merges

## Blockers
None.

## Phase
Corpus: 9 books / 4626 chunks / 3 domains (devops, python, ai) — `travel`
no longer exists as a domain concept. No active implementation phase —
this was a scope-correction task, not corpus building.
