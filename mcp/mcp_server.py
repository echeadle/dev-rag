"""
dev-rag MCP Server
==================
Exposes your dev-rag FastAPI retrieval system as an MCP server
for use in Claude Code terminal sessions.

Transport: stdio (default) or HTTP (see --http flag)
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from typing import Any

import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

RAG_BASE_URL = os.getenv("DEV_RAG_BASE_URL", "http://localhost:8000")
RAG_API_KEY = os.getenv("DEV_RAG_API_KEY", "")          # optional bearer token
REQUEST_TIMEOUT = float(os.getenv("DEV_RAG_TIMEOUT", "30"))

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,   # MCP uses stdout; always log to stderr
)
log = logging.getLogger("dev-rag-mcp")

# ---------------------------------------------------------------------------
# HTTP client helpers
# ---------------------------------------------------------------------------

def _build_headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if RAG_API_KEY:
        headers["Authorization"] = f"Bearer {RAG_API_KEY}"
    return headers


async def _get(path: str, params: dict | None = None) -> Any:
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        r = await client.get(
            f"{RAG_BASE_URL}{path}",
            headers=_build_headers(),
            params=params or {},
        )
        r.raise_for_status()
        return r.json()


async def _post(path: str, payload: dict) -> Any:
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        r = await client.post(
            f"{RAG_BASE_URL}{path}",
            headers=_build_headers(),
            json=payload,
        )
        r.raise_for_status()
        return r.json()


# ---------------------------------------------------------------------------
# Result formatting
# ---------------------------------------------------------------------------

def _format_results(results: list[dict], include_score: bool = True) -> str:
    """Convert RAG result list into readable markdown for Claude Code.

    Reads the canonical `relevance_score` field that /search always populates
    regardless of search mode (dense, hybrid, or reranked). OBS-001 fix.
    """
    if not results:
        return "_No results found._"

    parts: list[str] = []
    for i, r in enumerate(results, 1):
        source = r.get("source") or r.get("metadata", {}).get("source", "unknown")
        domain = r.get("domain") or r.get("metadata", {}).get("domain", "")
        content = r.get("content") or r.get("text", "")
        # Canonical field — always set by /search regardless of search mode
        score = r.get("relevance_score")

        header = f"### [{i}] {source}"
        if domain:
            header += f"  `{domain}`"
        if include_score and score is not None:
            header += f"  (score: {score:.3f})"

        parts.append(f"{header}\n\n{content.strip()}")

    return "\n\n---\n\n".join(parts)


def _format_error(exc: Exception) -> list[types.TextContent]:
    msg = str(exc)
    if isinstance(exc, httpx.ConnectError):
        msg = (
            f"Cannot reach dev-rag server at {RAG_BASE_URL}. "
            "Is it running? Check DEV_RAG_BASE_URL."
        )
    elif isinstance(exc, httpx.HTTPStatusError):
        msg = f"dev-rag API error {exc.response.status_code}: {exc.response.text}"
    log.error("Tool error: %s", msg)
    return [types.TextContent(type="text", text=f"**Error:** {msg}")]


# ---------------------------------------------------------------------------
# MCP Server definition
# ---------------------------------------------------------------------------

server = Server("dev-rag")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="search_devops",
            description=(
                "Semantic search over the DevOps documentation corpus "
                "(Docker, Ansible, Python, FastAPI, etc.). "
                "Returns the most relevant passages ranked by similarity."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural-language search query",
                    },
                    "n_results": {
                        "type": "integer",
                        "description": "Number of results to return (default 5, max 20)",
                        "default": 5,
                        "minimum": 1,
                        "maximum": 20,
                    },
                },
                "required": ["query"],
            },
        ),
        types.Tool(
            name="search_travel",
            description=(
                "Semantic search over the Travel documentation corpus "
                "(trip reports, guides, accessibility notes, etc.)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural-language search query",
                    },
                    "n_results": {
                        "type": "integer",
                        "description": "Number of results to return (default 5, max 20)",
                        "default": 5,
                        "minimum": 1,
                        "maximum": 20,
                    },
                },
                "required": ["query"],
            },
        ),
        types.Tool(
            name="search_python",
            description=(
                "Semantic search over the Python documentation corpus "
                "(Python books, language reference, standard library, "
                "production patterns, advanced language features). "
                "Use for Python-specific questions: language internals, "
                "idioms, async patterns, packaging, performance, and "
                "production best practices drawn from curated sources."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural-language search query",
                    },
                    "n_results": {
                        "type": "integer",
                        "description": "Number of results to return (default 5, max 20)",
                        "default": 5,
                        "minimum": 1,
                        "maximum": 20,
                    },
                },
                "required": ["query"],
            },
        ),
        types.Tool(
            name="search_ai",
            description=(
                "Semantic search over the AI and RAG corpus "
                "(RAG architecture, LLM patterns, evaluation metrics, "
                "chunking strategies, hallucination reduction, reranking). "
                "Use for meta questions about building AI systems — "
                "asking dev-rag about how to build dev-rag."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural-language search query",
                    },
                    "n_results": {
                        "type": "integer",
                        "description": "Number of results to return (default 5, max 20)",
                        "default": 5,
                        "minimum": 1,
                        "maximum": 20,
                    },
                },
                "required": ["query"],
            },
        ),
        types.Tool(
            name="search_all",
            description=(
                "Cross-domain semantic search across ALL corpora "
                "(DevOps + Travel + Python + AI). Results include a domain tag "
                "so you can see which collection each passage came from. "
                "Use when you are unsure which domain holds the answer, "
                "or when Argos needs to query the full knowledge base."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural-language search query",
                    },
                    "n_results": {
                        "type": "integer",
                        "description": "Total results to return (default 10, max 30)",
                        "default": 10,
                        "minimum": 1,
                        "maximum": 30,
                    },
                },
                "required": ["query"],
            },
        ),
        types.Tool(
            name="get_document",
            description=(
                "Fetch the full content of a specific document by its ID. "
                "Use when a search result looks relevant but you need "
                "the complete text rather than just the passage chunk."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "document_id": {
                        "type": "string",
                        "description": "The document ID (from search result metadata)",
                    },
                    "domain": {
                        "type": "string",
                        "description": "Optional domain hint (devops | travel | python)",
                        "enum": ["devops", "travel", "python"],
                    },
                },
                "required": ["document_id"],
            },
        ),
        types.Tool(
            name="list_collections",
            description=(
                "List all available domains/collections in the dev-rag system, "
                "with document counts and index status. Useful for understanding "
                "what's been ingested."
            ),
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
        types.Tool(
            name="rag_health",
            description="Check that the dev-rag server is reachable and return its status.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    try:
        if name == "search_devops":
            return await _handle_domain_search("devops", arguments)

        elif name == "search_travel":
            return await _handle_domain_search("travel", arguments)

        elif name == "search_python":
            return await _handle_domain_search("python", arguments)

        elif name == "search_ai":
            return await _handle_domain_search("ai", arguments)

        elif name == "search_all":
            return await _handle_search_all(arguments)

        elif name == "get_document":
            return await _handle_get_document(arguments)

        elif name == "list_collections":
            return await _handle_list_collections()

        elif name == "rag_health":
            return await _handle_health()

        else:
            return [types.TextContent(type="text", text=f"Unknown tool: {name}")]

    except Exception as exc:
        return _format_error(exc)


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------

async def _handle_domain_search(
    domain: str, args: dict
) -> list[types.TextContent]:
    query = args["query"]
    n = min(int(args.get("n_results", 5)), 20)

    # Try /search?domain=X first; fall back to /search/{domain} pattern
    try:
        data = await _post("/search", {"query": query, "domain": domain, "n_results": n})
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            data = await _post(f"/search/{domain}", {"query": query, "n_results": n})
        else:
            raise

    raw = data.get("results") or data.get("documents")
    results: list = raw if isinstance(raw, list) else ([raw] if raw else [])
    text = _format_results(results)
    label = {"devops": "DevOps", "travel": "Travel", "python": "Python", "ai": "AI"}.get(domain, domain.capitalize())
    header = f"## {label} search: \"{query}\"\n\n"
    return [types.TextContent(type="text", text=header + text)]


async def _handle_search_all(args: dict) -> list[types.TextContent]:
    query = args["query"]
    n = min(int(args.get("n_results", 10)), 30)

    # Try unified endpoint first
    try:
        data = await _post("/search", {"query": query, "n_results": n})
        results = data.get("results") or data.get("documents") or []
    except httpx.HTTPStatusError:
        # Fallback: fan-out to all four domain endpoints
        devops_task  = _post("/search", {"query": query, "domain": "devops",  "n_results": n // 4})
        travel_task  = _post("/search", {"query": query, "domain": "travel",  "n_results": n // 4})
        python_task  = _post("/search", {"query": query, "domain": "python",  "n_results": n // 4})
        ai_task      = _post("/search", {"query": query, "domain": "ai",      "n_results": n // 4})
        devops_data, travel_data, python_data, ai_data = await asyncio.gather(
            devops_task, travel_task, python_task, ai_task, return_exceptions=True
        )

        results = []
        for d, dom in [
            (devops_data, "devops"),
            (travel_data, "travel"),
            (python_data, "python"),
            (ai_data,     "ai"),
        ]:
            if isinstance(d, Exception):
                log.warning("Domain %s failed during fan-out: %s", dom, d)
                continue
            chunk = d.get("results") or d.get("documents") or []
            for r in chunk:
                r.setdefault("domain", dom)
            results.extend(chunk)

    text = _format_results(results)
    return [types.TextContent(
        type="text",
        text=f"## Cross-domain search: \"{query}\"\n\n{text}"
    )]


async def _handle_get_document(args: dict) -> list[types.TextContent]:
    doc_id = args["document_id"]
    domain = args.get("domain", "")

    params = {"domain": domain} if domain else {}
    try:
        data = await _get(f"/documents/{doc_id}", params)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return [types.TextContent(type="text", text=f"Document `{doc_id}` not found.")]
        raise

    source = data.get("source") or doc_id
    content = data.get("content") or data.get("text") or json.dumps(data, indent=2)
    metadata = data.get("metadata", {})

    meta_lines = "\n".join(f"- **{k}**: {v}" for k, v in metadata.items()) if metadata else ""
    text = f"## Document: {source}\n\n"
    if meta_lines:
        text += f"{meta_lines}\n\n"
    text += content.strip()

    return [types.TextContent(type="text", text=text)]


async def _handle_list_collections() -> list[types.TextContent]:
    # Try common collection/domain listing endpoints
    for path in ["/collections", "/domains", "/status", "/health"]:
        try:
            data = await _get(path)
            text = f"## dev-rag collections\n\n```json\n{json.dumps(data, indent=2)}\n```"
            return [types.TextContent(type="text", text=text)]
        except httpx.HTTPStatusError:
            continue

    return [types.TextContent(
        type="text",
        text="Could not retrieve collection list. "
             "Check your dev-rag API for a `/collections` or `/domains` endpoint."
    )]


async def _handle_health() -> list[types.TextContent]:
    try:
        data = await _get("/health")
        status = data.get("status", "unknown")
        text = f"## dev-rag health\n\nStatus: **{status}**\n\n"
        text += f"```json\n{json.dumps(data, indent=2)}\n```"
        return [types.TextContent(type="text", text=text)]
    except httpx.ConnectError:
        return [types.TextContent(
            type="text",
            text=f"**Unreachable** — dev-rag server not responding at {RAG_BASE_URL}"
        )]


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

async def _run_stdio() -> None:
    log.info("Starting dev-rag MCP server (stdio) → %s", RAG_BASE_URL)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main() -> None:
    parser = argparse.ArgumentParser(description="dev-rag MCP server")
    parser.add_argument(
        "--http",
        action="store_true",
        help="Run as HTTP/SSE server instead of stdio (requires mcp[http] extra)",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9000)
    args = parser.parse_args()

    if args.http:
        # HTTP/SSE mode — useful for remote access or Argos integration
        try:
            from mcp.server.sse import SseServerTransport
            from starlette.applications import Starlette
            from starlette.routing import Route
            import uvicorn

            sse = SseServerTransport("/messages")

            async def handle_sse(request):
                async with sse.connect_sse(request.scope, request.receive, request._send) as streams:
                    await server.run(streams[0], streams[1], server.create_initialization_options())

            app = Starlette(routes=[Route("/sse", endpoint=handle_sse)])
            print(f"dev-rag MCP server (HTTP/SSE) on http://{args.host}:{args.port}/sse", file=sys.stderr)
            uvicorn.run(app, host=args.host, port=args.port)
        except ImportError as e:
            print(f"HTTP mode requires extra deps: {e}", file=sys.stderr)
            print("Install with: uv add 'mcp[http]' starlette uvicorn", file=sys.stderr)
            sys.exit(1)
    else:
        asyncio.run(_run_stdio())


if __name__ == "__main__":
    main()
