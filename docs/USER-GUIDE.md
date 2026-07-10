# dev-rag User Guide — how to actually use it

This is the "how do I use my RAG tool today" guide — starting the server, asking
questions in Claude Code, and adding more books. For pipeline internals, stage-by-stage
detail, and dev-only flags, see `docs/RUNBOOK.md`. For what's deferred and why, see
`docs/TODO.md`.

## 1. Start the server

dev-rag's tools are registered globally in Claude Code (`claude mcp add -s user`,
2026-07-10) — they show up in *any* Claude Code session, not just this repo. But the
actual search backend (a small FastAPI server) is **not** always-on yet; it has to be
started by hand each time you want to use it. This is a deliberate choice, not an
oversight — see the "Backend persistence" entry in `docs/TODO.md` for why, and the
options for making it automatic later.

```bash
scripts/serve.sh
```

Works from **any directory** — the script `cd`s into the repo root itself before
launching, so it won't silently point at empty data (a real bug from before
2026-07-10, now fixed).

Run it in the foreground and leave the terminal open, or background it:

```bash
scripts/serve.sh &
```

Optional one-time convenience: symlink it onto your `PATH` so you can just type
`dev-rag-serve` from anywhere —

```bash
ln -s /home/echeadle/Projects/coding_projects/learning/dev-rag/scripts/serve.sh \
      ~/.local/bin/dev-rag-serve
```

**Confirm it's up:**

```bash
curl -s http://127.0.0.1:8000/health | python3 -m json.tool
```

or just ask Claude "check dev-rag health" — it'll call the `rag_health` tool.

## 2. Example: using it in a Claude Code session

Once the server is running, you don't need to name tools yourself — just ask a
question and Claude will pick the right one:

> "What does my devops corpus say about container restart policies?"

Claude calls `search_devops` automatically, retrieves real chunks from your ingested
books, and answers with citations back to the specific PDF and page. Same pattern for
Python or AI/RAG questions — just ask naturally; mention "devops"/"python"/"ai" if you
want to hint the domain, or ask across all of them and let it use `search_all`.

**Available tools** (all under the `dev-rag` MCP server):

| Tool | What it does |
|---|---|
| `search_devops` / `search_python` / `search_ai` | Natural-language search within one domain. Fast (~0.15s), reranker off by default. |
| `search_all` | Cross-domain search, genuinely reranked so results from different domains are comparable. Slow by design (~20s × number of populated domains) — use when you're not sure which domain has the answer. |
| `get_document` | Pull a specific chunk/document by ID. |
| `list_collections` | See what's ingested — domains and chunk counts. |
| `rag_health` | Status check — is the backend reachable, are the stores in sync. |

Current corpus (as of 2026-07-10): 12 books, 6,354 chunks across `devops` (7 books,
3,797 chunks), `python` (4 books, 1,949 chunks), and `ai` (1 book, 608 chunks).

## 3. Ingesting more PDFs

Drop the PDF into `data/books/`, then from the repo root:

```bash
uv run python -m dev_rag.ingest.pipeline \
    --source data/books/YourBook.pdf \
    --domain devops \
    --query "A question only this specific book should answer"
```

- `--domain`: `devops` | `python` | `ai`
- `--query` is required — it's used by the pipeline's last stage to verify the new
  book is actually retrievable. Pick something this book covers that others in the
  same domain don't, or the verify step can fail even though ingestion worked fine.
- Takes roughly 15–30 minutes for a 250–600 page book, almost all of it in the
  embedding stage (CPU-bound). Safe to run in the background.
- **No server restart needed** — ChromaDB and SQLite are just files on disk; a
  running server picks up newly-ingested chunks on the very next search. Confirmed
  empirically: two books were ingested back-to-back in one session today without
  restarting the server in between, and `rag_health`/searches reflected each one
  immediately after its ingest finished.
- Full stage-by-stage detail (what each of the 8 stages does, useful flags like
  `--dry-run`/`--stop-stage`/`--start-stage` for resuming or inspecting partial
  output) is in `docs/RUNBOOK.md` §3.

## 4. Quick troubleshooting

- **"Cannot reach dev-rag server" from a tool call** — the backend isn't running.
  Go back to step 1.
- **`rag_health` responds but chunk counts are 0** — the backend was started from a
  directory other than the repo root without using `scripts/serve.sh` (its DB paths
  are relative, so this silently points at empty stores instead of erroring). Kill it
  and restart via the script.
- **A single search feels slow (~15s+)** — the reranker is on. It's off by default
  for a reason: turning it on globally (`RERANKER_ENABLED=true`) uses a 50-candidate
  pool (~112s/query) unless you also set `RERANKER_CANDIDATES=10` (~15-20s/query):
  ```bash
  RERANKER_ENABLED=true RERANKER_CANDIDATES=10 scripts/serve.sh
  ```
- **`search_all` takes 40-60+ seconds** — expected, not a bug. It reranks each
  populated domain in turn (single-process server, so this is serial, not parallel) —
  it's the "willing to wait for the best cross-domain answer" tool, not a routine
  lookup. Use `search_devops`/`search_python`/`search_ai` for everyday questions.

## 5. Where to look next

- `docs/RUNBOOK.md` — full pipeline internals, stage tables, eval harness usage
- `docs/TODO.md` — what's deferred (backend persistence, GraphRAG, `agent.py`) and why
- `DEV-RAG-ARCHITECTURE.md` — the ADRs behind the big design decisions
