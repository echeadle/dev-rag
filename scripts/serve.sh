#!/usr/bin/env bash
# Starts the dev-rag FastAPI backend. Always cd's into the repo root first —
# settings.py's DB paths are relative, so running this from elsewhere would
# boot cleanly but silently point at empty/nonexistent stores (empty search
# results, not an error). Safe to call from any directory.
cd /home/echeadle/Projects/coding_projects/learning/dev-rag
exec uv run uvicorn dev_rag.api:app --host 127.0.0.1 --port 8000
