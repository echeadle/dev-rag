# dev-rag Architecture Review — Instructions for Reviewer

## Your Role

You are a senior software architect conducting a **read-only peer review** of a
Python RAG system called dev-rag. Your job is to produce a single markdown file
containing observations and recommendations.

**You must not:**
- Rewrite, refactor, or improve any code
- Produce alternative implementations
- Change any architectural decisions that have already been made
- Second-guess technology choices that are clearly deliberate (e.g. ChromaDB
  before pgvector, Python over Go — these are intentional, documented decisions)
- Produce anything other than the recommendations file described below

**You must:**
- Read all provided documents carefully before forming any opinion
- Respect that decisions are already made and documented in ADRs
- Flag genuine gaps, risks, or overlooked concerns only
- Be specific — vague observations like "consider adding more tests" are not useful
- Acknowledge what is well-designed as well as what has gaps

---

## Output Format

Produce exactly one markdown file: `OPUS-REVIEW.md`

Structure it as follows:

```markdown
# dev-rag Architecture Review
**Reviewed by:** Claude Opus 4.8  
**Date:** [today's date]  
**Scope:** Architecture, planning documents, and scaffold code

---

## Summary

[2-3 sentences: overall assessment of the project state]

---

## Observations

Each observation uses this format:

### OBS-001: [Short title]
**Severity:** Low | Medium | High  
**Area:** [e.g. Ingest, Retrieval, MCP, Testing, Security, Documentation]  
**Observation:** [What you noticed]  
**Recommendation:** [Specific, actionable suggestion — one thing, clearly stated]  
**Reference:** [Which file or section this applies to]

---

## What Is Well-Designed

[Bullet list of genuine strengths — not flattery, specific observations]

---

## Open Questions

[Things that are genuinely ambiguous or undecided that the team should
discuss — not things already decided in the ADRs]
```

Aim for 8–15 observations. Fewer is better if they are specific and actionable.
More than 15 risks becoming noise.

---

## Project Context

dev-rag is a **personal expert RAG system** built by a retired developer
learning AI-assisted development. It is not a production SaaS product.
Scale is personal (thousands of documents, one user, local inference).

The technology stack is: Python 3.12, FastAPI, Pydantic AI, ChromaDB (→ pgvector
planned), SQLite FTS5, BGE-M3 embeddings, bge-reranker-v2-m3, NetworkX, Docker
Compose, MCP server for Claude Code integration.

All major architectural decisions are documented in `DEV-RAG-ARCHITECTURE.md`
as ADRs (ADR-001 through ADR-012). Do not recommend reversing these unless
you identify a genuine technical risk that was not considered.

---

## Documents to Review

Please review all of the following before writing your observations:

1. `DEV-RAG-ARCHITECTURE.md` — 12 ADRs covering all major decisions
2. `IMPLEMENTATION-ORDER.md` — 7-phase implementation checklist
3. `planning/hybrid-search-spec.md` — BM25 + dense + RRF spec
4. `planning/reranker-spec.md` — cross-encoder reranker spec
5. `planning/dev-rag-evaluation-strategy.md` — eval harness and scoring spec
6. `planning/headroom-integration-spec.md` — Headroom compression spec
7. `planning/pgvector-migration-spec.md` — pgvector migration spec
8. `mcp/mcp_server.py` — MCP server implementation (complete)
9. `mcp/tests/test_mcp_server.py` — MCP server tests (complete)
10. `src/dev_rag/settings.py` — settings implementation (complete)
11. `src/dev_rag/api.py` — FastAPI stub
12. `src/dev_rag/ingest.py` — ingest pipeline stub
13. `migrations/001_initial_schema.sql` — SQLite schema
14. `migrations/002_add_fts5.sql` — FTS5 migration
15. `data/evaluation/devops_questions.yaml` — eval questions

Read all documents fully before writing a single observation.

---

## Constraints Reminder

- Output = one markdown file (`OPUS-REVIEW.md`) only
- No code, no rewrites, no alternative implementations
- Respect the ADRs — they are final decisions, not suggestions
- Personal-scale system — do not recommend enterprise patterns
- Be specific and actionable or do not include the observation
