#!/usr/bin/env bash
# Starts the dev-rag FastAPI backend. Always cd's into the repo root first —
# settings.py's DB paths are relative, so running this from elsewhere would
# boot cleanly but silently point at empty/nonexistent stores (empty search
# results, not an error). Safe to call from any directory.
#
# --on enables the reranker for this run, using the fast candidate pool
# (RERANKER_CANDIDATES=10, ~15-20s/query) instead of the slow default pool
# that bare RERANKER_ENABLED=true would otherwise use (50, ~112s/query —
# see the CLAUDE.md Lessons entry from 2026-07-10). ADR-012 still decides
# the server-wide default (OFF); this is a per-run opt-in only.
cd /home/echeadle/Projects/coding_projects/learning/dev-rag

if [[ "$1" == "--on" ]]; then
    export RERANKER_ENABLED=true
    export RERANKER_CANDIDATES=10
fi

exec uv run uvicorn dev_rag.api:app --host 127.0.0.1 --port 8000
