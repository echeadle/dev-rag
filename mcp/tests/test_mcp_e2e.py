"""End-to-end MCP tests: real stdio subprocess → real HTTP → real retrieval.

Proves the full path a Claude Code session takes: MCP client spawns
mcp/mcp_server.py over stdio, which calls a live uvicorn instance of the
real FastAPI app backed by temp ChromaDB + SQLite built by the REAL
migrations and loader (same harness as tests/test_api_e2e.py). Only the
embedding model is fake — real BGE-M3 never loads in tests.

The API runs IN-PROCESS (uvicorn.Server in a thread) so the monkeypatched
settings paths and fake embedder apply; the MCP server is a genuine
subprocess, so the stdio framing, initialize handshake, and tool
serialization are exercised for real.
"""
import asyncio
import os
import sys
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

import numpy as np
import pytest
import uvicorn
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

REPO = Path(__file__).resolve().parent.parent.parent
MIGRATIONS = REPO / "migrations"
SERVER_SCRIPT = REPO / "mcp" / "mcp_server.py"
DIM = 8

CONTENTS = [
    "Docker images are built in layers from a Dockerfile.",
    "Docker secrets are encrypted in the swarm cluster store.",
    "Bridge networks are the default Docker network mode.",
]


class QueryModel:
    """Query always embeds one-hot(1) → dense favours the secrets chunk."""

    def encode(self, text, **kwargs):
        v = np.zeros(DIM, dtype=np.float32)
        v[1] = 1.0
        return v


@pytest.fixture(scope="module")
def live_api(tmp_path_factory):
    """Real app on an ephemeral localhost port, temp stores, fake embedder."""
    import dev_rag.retrieve as retrieve
    from dev_rag.api import app
    from dev_rag.ingest.load import load_to_stores
    from dev_rag.ingest.util import content_hash
    from dev_rag.settings import settings

    tmp_path = tmp_path_factory.mktemp("mcp_e2e")
    chunks = [
        {
            "chunk_id": f"tiny_{i:04d}", "source_id": "tiny", "source": "tiny.pdf",
            "domain": "devops", "title": "Tiny Book", "page_number": i + 1,
            "content": text, "content_hash": content_hash(text),
        }
        for i, text in enumerate(CONTENTS)
    ]
    embeds = []
    for i in range(3):
        v = [0.0] * DIM
        v[i] = 1.0
        embeds.append(v)
    load_to_stores(chunks, embeds, chroma_path=str(tmp_path / "chroma"),
                   sqlite_path=tmp_path / "dev_rag.db", migrations_dir=MIGRATIONS)

    mp = pytest.MonkeyPatch()
    mp.setattr(settings, "chroma_db_path", str(tmp_path / "chroma"))
    mp.setattr(settings, "sqlite_db_path", tmp_path / "dev_rag.db")
    mp.setattr(retrieve, "_embedder", QueryModel())
    # uvicorn runs the real lifespan — keep it from loading the real
    # bge-reranker-v2-m3; the stdio path is what this file exercises
    mp.setattr(settings, "reranker_enabled", False)

    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("uvicorn did not start within 10s")
        time.sleep(0.02)
    port = server.servers[0].sockets[0].getsockname()[1]

    yield f"http://127.0.0.1:{port}"

    server.should_exit = True
    thread.join(timeout=5)
    mp.undo()


@asynccontextmanager
async def mcp_session(base_url: str):
    """Spawn the real MCP server subprocess over stdio, pointed at base_url."""
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(SERVER_SCRIPT)],
        env={**os.environ, "DEV_RAG_BASE_URL": base_url},
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


async def _tool_text(session, name: str, args: dict) -> str:
    result = await session.call_tool(name, args)
    return "\n".join(c.text for c in result.content)


async def test_lists_all_eight_tools(live_api):
    async with asyncio.timeout(30):
        async with mcp_session(live_api) as session:
            tools = await session.list_tools()
            names = {t.name for t in tools.tools}
    assert names == {
        "search_devops", "search_python", "search_ai",
        "search_all", "get_document", "list_collections", "rag_health",
    }


async def test_search_devops_returns_real_chunk_with_score(live_api):
    async with asyncio.timeout(30):
        async with mcp_session(live_api) as session:
            text = await _tool_text(
                session, "search_devops",
                {"query": "docker secrets", "n_results": 3},
            )
    # Top hit is the secrets chunk (dense one-hot + BM25 both favour it),
    # rendered with source and the canonical relevance_score (OBS-001).
    assert "Docker secrets are encrypted in the swarm cluster store." in text
    assert "tiny.pdf" in text
    assert "(score: 0.0" in text            # RRF scale ~0.03, formatted %.3f


async def test_rag_health_reports_real_store_counts(live_api):
    async with asyncio.timeout(30):
        async with mcp_session(live_api) as session:
            text = await _tool_text(session, "rag_health", {})
    assert "Status: **ok**" in text
    assert '"chroma_chunks": 3' in text
    assert '"sqlite_chunks": 3' in text


async def test_get_document_stub_degrades_gracefully(live_api):
    async with asyncio.timeout(30):
        async with mcp_session(live_api) as session:
            text = await _tool_text(
                session, "get_document", {"document_id": "nope-123"},
            )
    assert "not found" in text.lower()
