# Branch Review Checklist

How Ed reviews a feature branch before merging to main. Steps 1–4 apply to
any branch; steps 5–11 are the live A/B for reranker-related changes (adapt
the curl/env vars to whatever the branch touches — the pattern is
"run it OFF, run it ON, compare").

Written at Phase 3 close (2026-07-06); the example values are from the
`feat/phase3-reranker` review.

## Steps

1. Check out the branch:
   ```bash
   git checkout feat/phase3-reranker
   ```

2. See which files changed:
   ```bash
   git diff main..feat/phase3-reranker --stat
   ```

3. Read the full diff:
   ```bash
   git diff main..feat/phase3-reranker
   ```

4. Run the whole suite:
   ```bash
   uv run pytest
   ```
   Expect the count the branch's commit message states (Phase 3: **127 passed**),
   with BOTH `tests/` and `mcp/tests/` collected.

5. Start the server with defaults:
   ```bash
   uv run uvicorn dev_rag.api:app --host 127.0.0.1 --port 8000
   ```

6. In a second terminal — health check:
   ```bash
   curl -s http://127.0.0.1:8000/health | python3 -m json.tool
   ```
   Expect `"reranker_enabled": false`.

7. Baseline search (fast path):
   ```bash
   curl -s -X POST http://127.0.0.1:8000/search \
     -H 'Content-Type: application/json' \
     -d '{"query": "How do bind mount permissions work in Docker?", "domain": "devops", "n_results": 3}' \
     | python3 -m json.tool
   ```
   Expect ~0.15 s (after the first query's ~10 s embedder load) and
   `"reranker_score": null` on every result.

8. Stop the server (Ctrl-C).

9. Start the server with the feature enabled (one command; the NAME=value
   pairs are env vars for that process only — defaults return on restart):
   ```bash
   RERANKER_ENABLED=true RERANKER_CANDIDATES=10 uv run uvicorn dev_rag.api:app --host 127.0.0.1 --port 8000
   ```
   Wait for `Application startup complete` before querying — the reranker
   loads eagerly first (you'll see a `Loading weights: ... 393/393` progress
   bar; first-ever run also downloads ~2.2 GB). The app's own
   "Reranker loaded" INFO log does NOT appear under uvicorn's default
   logging config — confirm instead with the step 6 health check, which
   should now show `"reranker_enabled": true`.

10. Repeat the step 7 curl.
    Expect ~15 s, a numeric `"reranker_score"` on every result, and
    `"reranker": "BAAI/bge-reranker-v2-m3"` in the response.

11. Stop the server (Ctrl-C).

12. If satisfied, merge and push:
    ```bash
    git checkout main
    git merge --no-ff feat/phase3-reranker
    git push origin main
    ```

## Notes

- Env var names have NO `DEV_RAG_` prefix (`RERANKER_ENABLED`, not
  `DEV_RAG_RERANKER_ENABLED`) — see runbook §5b.
- No-curl option: with the server up, http://127.0.0.1:8000/docs gives a
  browser UI for firing searches (expand POST /search → "Try it out").
- After merging, update `current_context.md` if the merge closes a phase.
