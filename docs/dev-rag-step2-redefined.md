# dev-rag — Claude Code STEP 2 (REDEFINED — v2, with headroom removal)

**Context:** Step 1 re-verification is committed on branch `review/opus-fixes`.
It found the review already absorbed: 11/12 findings resolved, both High findings
no longer reproduce, 29 tests pass. The ORIGINAL Step 2 ("revert FAKE_RESULTS to
force red tests") is **CANCELLED** — it would reintroduce the OBS-001 bug.

This pass = **three mechanical tasks**, each its own commit, then a docs commit.
Paste into Claude Code from the repo root, on branch `review/opus-fixes`.

---

```
You are on branch review/opus-fixes in the dev-rag repo. Conventions: uv ONLY (never
pip), Python 3.12. See CLAUDE.md. The OPUS review is already absorbed at the contract
level (docs/reviews/OPUS-REVIEW-VERIFICATION.md); this is a narrow hardening pass.

RESOLUTIONS to the two questions you raised at the end of STEP 1 (settled — do not re-ask):
1. FAKE_RESULTS / relevance_score — ACCEPTED as-is. Do NOT revert fixtures to
   rrf_score/reranker_score; that was the old plan and would reintroduce OBS-001.
   relevance_score is the canonical field. (Also on the DO NOT TOUCH list below.)
2. The findings needing a corpus / ingestion / the real Headroom library (OBS-003,
   OBS-006, OBS-008) are correctly DEFERRED — out of scope here. This pass does the
   genuinely mechanical work instead: the two cleanups you flagged yourself (testpaths
   skipping mcp/tests; the dead cross-domain flag + missing "ai" domain) plus removing
   the unsatisfiable headroom dependency.

Do exactly these tasks in order, each as its own commit. Nothing else.

TASK 1 — remove the deferred Headroom dependency (unblocks `uv sync`).
Headroom (context compression) is deferred to a nice-to-have and is being removed now.
Finding: the dep is misnamed AND unsatisfiable — pyproject pins `headroom>=0.3.0`, but
bare `headroom` on PyPI is an unrelated CLI stuck at 0.2.7 (the real compression lib is
`headroom-ai`). It is not needed for a working RAG pipeline. Remove it cleanly:
- grep the repo for `headroom` and the `compress` extra. In pyproject.toml, remove the
  `compress` optional-dependency group (the `headroom>=0.3.0` line) and any reference to
  the `compress` extra from other extras (e.g. an `all` aggregate) or tooling.
- Leave mcp/compress.py as-is (it's a no-op stub that imports no headroom at runtime).
  Do NOT delete compress.py or its call sites.
- Verify `uv sync` now resolves cleanly (no headroom error).
- Verify tests still pass: `uv run pytest tests mcp/tests` (expect 29 passed).
- Commit: `build: drop unsatisfiable headroom dep; compression deferred (OBS-008)`.

TASK 2 — make the default test run include the MCP tests (guards OBS-001/002).
Problem: pyproject `testpaths = ["tests"]` makes a bare `pytest` collect only 7 tests
and SKIP mcp/tests/ (22) — the tests guarding the two High findings. Fix so a bare
`uv run pytest` from the repo root collects and passes all 29.
- Preferred: add "mcp/tests" to `testpaths`.
- VERIFY: `uv run pytest` (no args) reports 29 passed. If collection breaks (mcp/ is a
  separate package with its own pyproject.toml — possible import/rootdir issues),
  diagnose and fix properly (conftest / path). Do NOT paper over it by reverting to
  tests-only. If you cannot get a bare run to collect all 29 cleanly, STOP and report.
- Commit: `test: run mcp/tests by default so OBS-001/002 guards aren't skipped`.

TASK 3 — clean up eval/runner.py cross-domain handling (OBS-004 residue).
(a) Remove the dead `CROSS_DOMAIN_ENDPOINT_AVAILABLE` flag (defined, never read).
(b) The cross-domain fan-out hardcodes ["devops","travel","python"], omitting "ai"
    even though ai is in settings.valid_domains and data/evaluation/ai_questions.yaml
    exists. Derive the fan-out list from settings.valid_domains so it can't drift again.
- FIRST print settings.valid_domains and confirm it is exactly the intended set
  (expected: devops, travel, python, ai). If anything unexpected appears, STOP and ask.
- Run `uv run pytest` (must be 29 passed).
- Commit: `fix(eval): derive cross-domain fan-out from valid_domains; drop dead flag (OBS-004)`.

TASK 4 — docs (only if the files are present in the working tree).
(a) If CLAUDE.md (repo root) and an updated docs/TODO.md have been placed in the repo,
    stage and commit them.
(b) In IMPLEMENTATION-ORDER.md, strike the Phase 6 (Headroom compression) entry and add
    a one-line note "deferred — see docs/TODO.md Deferred section". Leave the Phase 7/8
    numbering UNCHANGED (matches docs/TODO.md; lowest cross-doc drift).
Commit (a)+(b) together: `docs: add CLAUDE.md; defer headroom (TODO + IMPLEMENTATION-ORDER)`.
If the CLAUDE.md/TODO.md files aren't present, still do (b) and tell me (a) was skipped.

DO NOT TOUCH (deferred by the verification doc — out of scope):
- FAKE_RESULTS / relevance_score / any OBS-001/002 fixtures or consumers (already correct).
- OBS-003 expected_source, OBS-006 FTS5 tokenizer, OBS-009 parity counts.
- The ingest.py-vs-spec tension, GraphRAG, agent.py — handled in a later session.
- Do NOT implement compression or add `headroom-ai` now — it's deferred.

When all applicable tasks are committed and `uv run pytest` is 29 passed, STOP and
summarize the commits. Do NOT push — I'll review the branch and push myself.
```

---

## Recommended order for the batch
1. Run this Step 2 prompt in Claude Code (Tasks 1–3 land; `uv sync` works; 29 tests pass).
2. Drop the updated `CLAUDE.md` (repo root) and `docs/TODO.md` into the tree,
   then let Task 4 commit them — or re-run just Task 4.
3. Also apply the "Phase 6 removed" one-line edit to `IMPLEMENTATION-ORDER.md`
   (kept out of this prompt since numbering there is yours to decide).

## After Step 2
Review is closed. Next: the **planning-gaps (b) session** (own branch — GraphRAG spec,
ingest sequencing, agent layer) or **implementation** of the stubbed pipeline per
`planning/*` + `IMPLEMENTATION-ORDER.md`.
