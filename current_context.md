# Current Context — dev-rag
_Last updated: 2026-07-04_

## Active File
pyproject.toml, eval/runner.py, IMPLEMENTATION-ORDER.md, docs/TODO.md, CLAUDE.md,
docs/reviews/OPUS-REVIEW-VERIFICATION.md

## Current Step
OPUS review CLOSED. Branch `review/opus-fixes` merged to `main`.
- Step 1 re-verification: all 12 OPUS-REVIEW findings checked against current code —
  11/12 already fixed.
- Step 2 hardening pass:
  - Headroom dep removed (`headroom>=0.3.0` was unsatisfiable; the real compression
    lib is `headroom-ai`, deferred). `uv sync` now resolves; `uv.lock` is tracked.
  - Test gate fixed: `mcp/tests` now runs by default via
    `--import-mode=importlib` + `pythonpath=["mcp"]` — bare `uv run pytest` = 29
    passed, guarding OBS-001/002.
  - `eval/runner.py` cross-domain fan-out now derives from `settings.valid_domains`
    (adds "ai").
  - Phase 6 (Headroom) struck in `IMPLEMENTATION-ORDER.md` and `docs/TODO.md`;
    `CLAUDE.md` added.
  - Hygiene: `resume.sh` and the step2 prompt doc are untracked (gitignored /
    archived).

## Next Action
Reconcile `planning/ingest-pipeline-spec.md` vs `src/dev_rag/ingest.py`'s docstring
(OBS-007) before starting Phase 1a.

## Done When
- [ ] Decision made & documented on which supersedes which (spec vs docstring) for OBS-007
- [ ] Phase 1a (staged ingest pipeline) has an unambiguous chunking approach to build against

## Blockers
None currently. Remaining deferred items (OBS-003 expected_source, OBS-006 FTS5
tokenizer, OBS-008 real `headroom-ai` integration) all require an ingested corpus
first; GraphRAG has no spec; `agent.py` is unwired. All intentionally out of scope
until Phase 1a lands.

## Phase
Between Phase 0 (review/hardening, now closed) and Phase 1a (staged ingest pipeline)
— see `IMPLEMENTATION-ORDER.md`.
