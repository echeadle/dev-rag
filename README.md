# dev-rag MCP Server

Exposes your **dev-rag** FastAPI retrieval system as an
[MCP](https://modelcontextprotocol.io) server so Claude Code terminal sessions
can query your curated corpora directly.

---

## Tools exposed

| Tool | Description |
|------|-------------|
| `search_devops` | Semantic search over Docker, Ansible, Ubuntu Server docs |
| `search_python` | Semantic search over Python books and references |
| `search_ai` | Semantic search over the AI/RAG corpus |
| `search_all` | Cross-domain search with domain tags on results |
| `get_document` | Fetch full document by ID |
| `list_collections` | List available domains + document counts |
| `rag_health` | Check dev-rag server reachability |

---

## Quick start — stdio mode (recommended for local dev)

### 1. Install

```bash
# From this directory
uv pip install -e .
# or plain pip
pip install -e .
```

### 2. Register with Claude Code

```bash
claude mcp add --transport stdio dev-rag \
  --env DEV_RAG_BASE_URL=http://localhost:8000 \
  -- python /path/to/dev-rag-mcp/mcp_server.py
```

Verify it loaded:

```bash
claude mcp list
# dev-rag   stdio   ✓ Connected
```

### 3. Use it in Claude Code

```
Search the devops corpus for how to configure Docker bridge networks.
```

```
Use search_all to find anything about pgvector indexes.
```

---

## HTTP/SSE mode (multi-session or remote access)

Use this when you want multiple Claude Code sessions (or Argos) to share one
running MCP server.

### Run directly

```bash
DEV_RAG_BASE_URL=http://localhost:8000 \
  python mcp_server.py --http --port 9000
```

### Register with Claude Code

```bash
claude mcp add --transport sse dev-rag http://localhost:9000/sse
```

### Via Docker Compose

Merge the provided `docker-compose.mcp.yml` into your project:

```bash
docker compose -f docker-compose.yml -f docker-compose.mcp.yml up -d
```

Then register:

```bash
claude mcp add --transport sse dev-rag http://localhost:9000/sse \
  --header "Authorization: Bearer ${DEV_RAG_API_KEY}"
```

---

## Configuration

All settings via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `DEV_RAG_BASE_URL` | `http://localhost:8000` | dev-rag FastAPI URL |
| `DEV_RAG_API_KEY` | *(empty)* | Optional bearer token |
| `DEV_RAG_TIMEOUT` | `30` | Request timeout in seconds |

For stdio mode, pass env vars via `--env` flags in the `claude mcp add` command:

```bash
claude mcp add --transport stdio dev-rag \
  --env DEV_RAG_BASE_URL=http://localhost:8000 \
  --env DEV_RAG_API_KEY=my-secret-token \
  -- python /path/to/mcp_server.py
```

The config is stored in `~/.claude.json` (user scope, all projects) or
`.mcp.json` in your project root (project scope, shared via git).

---

## MCP config JSON reference

If you prefer editing JSON directly (`~/.claude.json` or `.mcp.json`):

```json
{
  "mcpServers": {
    "dev-rag": {
      "type": "stdio",
      "command": "python",
      "args": ["/absolute/path/to/mcp_server.py"],
      "env": {
        "DEV_RAG_BASE_URL": "http://localhost:8000",
        "DEV_RAG_API_KEY": "optional-token"
      }
    }
  }
}
```

For HTTP mode:

```json
{
  "mcpServers": {
    "dev-rag": {
      "type": "sse",
      "url": "http://localhost:9000/sse",
      "headers": {
        "Authorization": "Bearer optional-token"
      }
    }
  }
}
```

---

## API compatibility

The server tries the most common endpoint shapes and falls back gracefully:

- Search: `POST /search` with `{"query", "domain", "n_results"}` → falls back to `POST /search/{domain}`
- Documents: `GET /documents/{id}`
- Collections: `GET /collections` → `/domains` → `/status` → `/health`

Adjust `mcp_server.py` if your dev-rag FastAPI uses different routes.

---

## Running tests

```bash
uv pip install -e ".[dev]"
pytest tests/ -v
```

17 tests covering all tool handlers, fallback routing, error handling,
empty results, and n_results clamping. No live server required (uses `respx`
to mock `httpx`).

---

## Argos integration (future)

When Argos comes online, add it as an HTTP client pointing at the same MCP
server URL, or call the dev-rag FastAPI directly. The MCP server is stateless
so multiple agents can share it safely.
