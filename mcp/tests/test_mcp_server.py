"""
Tests for dev-rag MCP server tool handlers.
Uses respx to mock httpx calls — no live dev-rag server required.
"""

import json
import pytest
import respx
import httpx

# Patch the base URL before importing server module
import os
os.environ["DEV_RAG_BASE_URL"] = "http://localhost:8000"

from mcp_server import (
    _handle_domain_search,
    _handle_search_all,
    _handle_get_document,
    _handle_list_collections,
    _handle_health,
    _format_results,
)

FAKE_RESULTS = [
    {
        "source": "docker-compose.md",
        "domain": "devops",
        "content": "Use `docker compose up -d` to start services in detached mode.",
        "relevance_score": 0.92,   # OBS-001: canonical field name
    },
    {
        "source": "ansible-basics.md",
        "domain": "devops",
        "content": "Ansible uses YAML playbooks to describe automation tasks.",
        "relevance_score": 0.87,
    },
]

FAKE_PYTHON_RESULTS = [
    {
        "source": "fluent-python.pdf",
        "domain": "python",
        "content": "Descriptors are the mechanism behind properties, methods, and slots.",
        "relevance_score": 0.91,
    }
]

FAKE_AI_RESULTS = [
    {
        "source": "unlocking-rag.md",
        "domain": "ai",
        "content": "Hybrid RAG combines dense and sparse retrieval via reciprocal rank fusion.",
        "relevance_score": 0.95,
    }
]


# ---------------------------------------------------------------------------
# _format_results
# ---------------------------------------------------------------------------

def test_format_results_empty():
    assert "_No results found._" in _format_results([])


def test_format_results_includes_source():
    out = _format_results(FAKE_RESULTS)
    assert "docker-compose.md" in out
    assert "docker compose up" in out


def test_format_results_includes_score():
    out = _format_results(FAKE_RESULTS, include_score=True)
    assert "0.92" in out   # relevance_score from FAKE_RESULTS[0]


def test_format_results_no_score():
    out = _format_results(FAKE_RESULTS, include_score=False)
    assert "score" not in out


def test_format_results_relevance_score_field():
    """relevance_score is the canonical field — score/distance are not read."""
    result_with_only_relevance = [{
        "source": "test.md",
        "domain": "devops",
        "content": "test content",
        "relevance_score": 0.75,
        # no 'score' or 'distance' key — should still show 0.75
    }]
    out = _format_results(result_with_only_relevance, include_score=True)
    assert "0.75" in out


def test_format_results_flags_weak_match():
    """FBL-006: a low-confidence hit (weak_match=True) is annotated so the
    caller knows the corpus may not actually answer the query."""
    weak = [{"source": "x.pdf", "domain": "devops", "content": "c",
             "relevance_score": 0.2, "weak_match": True}]
    strong = [{"source": "x.pdf", "domain": "devops", "content": "c",
               "relevance_score": 0.9, "weak_match": False}]
    assert "weak match" in _format_results(weak)
    assert "weak match" not in _format_results(strong)
    # absent flag (reranker off / non-reranked result) → no annotation
    assert "weak match" not in _format_results(FAKE_RESULTS)


# ---------------------------------------------------------------------------
# _handle_domain_search (devops)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@respx.mock
async def test_search_devops_success():
    respx.post("http://localhost:8000/search").mock(
        return_value=httpx.Response(200, json={"results": FAKE_RESULTS})
    )
    result = await _handle_domain_search("devops", {"query": "docker compose", "n_results": 5})
    assert len(result) == 1
    text = result[0].text
    assert "docker-compose.md" in text
    assert "DevOps search" in text


@pytest.mark.asyncio
@respx.mock
async def test_search_devops_fallback_endpoint():
    """If /search returns 404, should fall back to /search/devops."""
    respx.post("http://localhost:8000/search").mock(
        return_value=httpx.Response(404, json={"detail": "not found"})
    )
    respx.post("http://localhost:8000/search/devops").mock(
        return_value=httpx.Response(200, json={"results": FAKE_RESULTS})
    )
    result = await _handle_domain_search("devops", {"query": "ansible playbook"})
    assert "ansible-basics.md" in result[0].text


@pytest.mark.asyncio
@respx.mock
async def test_search_devops_empty_results():
    respx.post("http://localhost:8000/search").mock(
        return_value=httpx.Response(200, json={"results": []})
    )
    result = await _handle_domain_search("devops", {"query": "nonexistent topic"})
    assert "_No results found._" in result[0].text


# ---------------------------------------------------------------------------
# _handle_search_all — Phase 5b: /health-driven domain discovery,
# force_rerank on every fan-out call, results sorted by relevance_score
# across domains (not concatenated in a fixed order).
# ---------------------------------------------------------------------------

def _health_response(populated: dict[str, int]) -> httpx.Response:
    """populated: {domain: chroma_chunks}. Unlisted domains default to 0."""
    all_domains = {"devops": 0, "python": 0, "ai": 0, **populated}
    return httpx.Response(200, json={
        "status": "ok",
        "store_parity": {
            dom: {"chroma_chunks": n, "sqlite_chunks": n, "in_sync": True}
            for dom, n in all_domains.items()
        },
    })


@pytest.mark.asyncio
@respx.mock
async def test_search_all_only_queries_populated_domains():
    """Only devops populated -> search_all must not call python/ai."""
    respx.get("http://localhost:8000/health").mock(
        return_value=_health_response({"devops": 1495})
    )
    calls = []

    def side_effect(request):
        body = json.loads(request.content)
        calls.append(body.get("domain"))
        assert body.get("force_rerank") is True
        return httpx.Response(200, json={"results": FAKE_RESULTS})

    respx.post("http://localhost:8000/search").mock(side_effect=side_effect)
    result = await _handle_search_all({"query": "Docker", "n_results": 8})
    text = result[0].text
    assert "Cross-domain search" in text
    assert "docker-compose.md" in text
    assert calls == ["devops"]


@pytest.mark.asyncio
@respx.mock
async def test_search_all_no_populated_domains():
    respx.get("http://localhost:8000/health").mock(
        return_value=_health_response({})
    )
    result = await _handle_search_all({"query": "anything"})
    assert "No domains have any content" in result[0].text


@pytest.mark.asyncio
@respx.mock
async def test_search_all_sorts_by_relevance_across_domains():
    """A higher-scored python result must outrank a lower-scored devops one —
    proves genuine cross-domain ranking, not domain-block concatenation."""
    respx.get("http://localhost:8000/health").mock(
        return_value=_health_response({"devops": 1495, "python": 532})
    )

    def side_effect(request):
        body = json.loads(request.content)
        domain = body.get("domain")
        if domain == "devops":
            # Lower score than the python result below
            return httpx.Response(200, json={"results": [
                {**FAKE_RESULTS[0], "relevance_score": 0.40}
            ]})
        elif domain == "python":
            return httpx.Response(200, json={"results": [
                {**FAKE_PYTHON_RESULTS[0], "relevance_score": 0.90}
            ]})
        return httpx.Response(500)

    respx.post("http://localhost:8000/search").mock(side_effect=side_effect)
    result = await _handle_search_all({"query": "anything", "n_results": 4})
    text = result[0].text
    # devops came first alphabetically/iteration-order in the old code;
    # the higher-scored python result must now appear first in the text.
    assert text.index("fluent-python.pdf") < text.index("docker-compose.md")


# ---------------------------------------------------------------------------
# _handle_domain_search (python)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@respx.mock
async def test_search_python_success():
    respx.post("http://localhost:8000/search").mock(
        return_value=httpx.Response(200, json={"results": FAKE_PYTHON_RESULTS})
    )
    result = await _handle_domain_search("python", {"query": "descriptors", "n_results": 5})
    text = result[0].text
    assert "Python search" in text
    assert "fluent-python.pdf" in text


@pytest.mark.asyncio
@respx.mock
async def test_search_python_empty_results():
    respx.post("http://localhost:8000/search").mock(
        return_value=httpx.Response(200, json={"results": []})
    )
    result = await _handle_domain_search("python", {"query": "nonexistent topic"})
    assert "_No results found._" in result[0].text


@pytest.mark.asyncio
@respx.mock
async def test_search_python_label_in_header():
    """Header should say 'Python search' not 'Devops search'."""
    respx.post("http://localhost:8000/search").mock(
        return_value=httpx.Response(200, json={"results": FAKE_PYTHON_RESULTS})
    )
    result = await _handle_domain_search("python", {"query": "generators"})
    assert "Python search" in result[0].text
    assert "Devops" not in result[0].text


# ---------------------------------------------------------------------------
# _handle_search_all — all three domains populated
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@respx.mock
async def test_search_all_fanout_three_domains():
    """All 3 valid domains populated -> fan-out queries devops, python,
    AND ai, with budget split 3 ways."""
    respx.get("http://localhost:8000/health").mock(
        return_value=_health_response({"devops": 1495, "python": 532, "ai": 608})
    )
    calls = []

    def side_effect(request):
        body = json.loads(request.content)
        calls.append(body.get("domain"))
        assert body.get("force_rerank") is True
        domain = body.get("domain", "")
        if domain == "devops":
            return httpx.Response(200, json={"results": FAKE_RESULTS})
        elif domain == "python":
            return httpx.Response(200, json={"results": FAKE_PYTHON_RESULTS})
        elif domain == "ai":
            return httpx.Response(200, json={"results": FAKE_AI_RESULTS})
        else:
            return httpx.Response(500)

    respx.post("http://localhost:8000/search").mock(side_effect=side_effect)
    result = await _handle_search_all({"query": "anything", "n_results": 9})
    text = result[0].text
    # All three populated domains should appear in the merged results
    assert "docker-compose.md" in text      # devops
    assert "fluent-python.pdf" in text      # python
    assert "unlocking-rag.md" in text       # ai
    assert sorted(calls) == ["ai", "devops", "python"]


@pytest.mark.asyncio
@respx.mock
async def test_search_all_fanout_on_500():
    """One populated domain's /search call 500s -> the others' results
    still come back (per-domain failure tolerance, not a hard failure)."""
    respx.get("http://localhost:8000/health").mock(
        return_value=_health_response({"devops": 1495, "python": 532, "ai": 608})
    )

    def side_effect(request):
        body = json.loads(request.content)
        domain = body.get("domain", "")
        if domain == "devops":
            return httpx.Response(200, json={"results": FAKE_RESULTS})
        elif domain == "ai":
            return httpx.Response(200, json={"results": FAKE_AI_RESULTS})
        else:
            return httpx.Response(500, json={"error": "server error"})

    respx.post("http://localhost:8000/search").mock(side_effect=side_effect)
    result = await _handle_search_all({"query": "anything"})
    text = result[0].text
    assert "docker-compose.md" in text and "unlocking-rag.md" in text
    assert "fluent-python.pdf" not in text


# ---------------------------------------------------------------------------
# _handle_get_document
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@respx.mock
async def test_get_document_success():
    respx.get("http://localhost:8000/documents/doc-123").mock(
        return_value=httpx.Response(200, json={
            "source": "docker-networking.md",
            "content": "Docker bridge networks allow containers to communicate.",
            "metadata": {"domain": "devops", "pages": 3},
        })
    )
    result = await _handle_get_document({"document_id": "doc-123"})
    text = result[0].text
    assert "docker-networking.md" in text
    assert "bridge networks" in text
    assert "domain" in text


@pytest.mark.asyncio
@respx.mock
async def test_get_document_not_found():
    respx.get("http://localhost:8000/documents/missing-id").mock(
        return_value=httpx.Response(404, json={"detail": "not found"})
    )
    result = await _handle_get_document({"document_id": "missing-id"})
    assert "not found" in result[0].text.lower()


# ---------------------------------------------------------------------------
# _handle_list_collections
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@respx.mock
async def test_list_collections_success():
    respx.get("http://localhost:8000/collections").mock(
        return_value=httpx.Response(200, json={
            "collections": [
                {"name": "devops", "documents": 142},
                {"name": "python", "documents": 38},
            ]
        })
    )
    result = await _handle_list_collections()
    text = result[0].text
    assert "collections" in text.lower()
    assert "devops" in text


@pytest.mark.asyncio
@respx.mock
async def test_list_collections_tries_multiple_paths():
    """/collections 404 → should try /domains or /status."""
    respx.get("http://localhost:8000/collections").mock(
        return_value=httpx.Response(404)
    )
    respx.get("http://localhost:8000/domains").mock(
        return_value=httpx.Response(200, json={"domains": ["devops", "python"]})
    )
    result = await _handle_list_collections()
    assert "domains" in result[0].text.lower() or "devops" in result[0].text


# ---------------------------------------------------------------------------
# _handle_health
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@respx.mock
async def test_health_ok():
    respx.get("http://localhost:8000/health").mock(
        return_value=httpx.Response(200, json={"status": "ok", "version": "0.3.1"})
    )
    result = await _handle_health()
    text = result[0].text
    assert "ok" in text.lower()
    assert "0.3.1" in text


@pytest.mark.asyncio
@respx.mock
async def test_health_unreachable():
    respx.get("http://localhost:8000/health").mock(side_effect=httpx.ConnectError("refused"))
    result = await _handle_health()
    assert "Unreachable" in result[0].text


# ---------------------------------------------------------------------------
# n_results clamping
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@respx.mock
async def test_n_results_clamped_to_max():
    """Requesting 999 results should be clamped to 20."""
    captured = {}

    def capture(request):
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"results": []})

    respx.post("http://localhost:8000/search").mock(side_effect=capture)
    await _handle_domain_search("devops", {"query": "test", "n_results": 999})
    assert captured["body"]["n_results"] <= 20
