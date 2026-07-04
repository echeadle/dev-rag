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

FAKE_TRAVEL_RESULTS = [
    {
        "source": "crete-guide.md",
        "domain": "travel",
        "content": "Heraklion airport has scooter-friendly drop-off zones near the terminal.",
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
# _handle_domain_search (travel)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@respx.mock
async def test_search_travel_success():
    respx.post("http://localhost:8000/search").mock(
        return_value=httpx.Response(200, json={"results": FAKE_TRAVEL_RESULTS})
    )
    result = await _handle_domain_search("travel", {"query": "scooter accessibility Crete"})
    text = result[0].text
    assert "Travel search" in text
    assert "crete-guide.md" in text


# ---------------------------------------------------------------------------
# _handle_search_all
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@respx.mock
async def test_search_all_unified_endpoint():
    all_results = FAKE_RESULTS + FAKE_TRAVEL_RESULTS
    respx.post("http://localhost:8000/search").mock(
        return_value=httpx.Response(200, json={"results": all_results})
    )
    result = await _handle_search_all({"query": "Docker and Crete"})
    text = result[0].text
    assert "Cross-domain search" in text
    assert "docker-compose.md" in text
    assert "crete-guide.md" in text


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
    assert "Travel" not in result[0].text


# ---------------------------------------------------------------------------
# _handle_search_all — updated for three domains
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@respx.mock
async def test_search_all_fanout_three_domains():
    """Fan-out should query devops, travel, AND python."""
    call_count = {"n": 0}

    def side_effect(request):
        call_count["n"] += 1
        body = json.loads(request.content)
        domain = body.get("domain", "")
        if domain == "devops":
            return httpx.Response(200, json={"results": FAKE_RESULTS})
        elif domain == "travel":
            return httpx.Response(200, json={"results": FAKE_TRAVEL_RESULTS})
        elif domain == "python":
            return httpx.Response(200, json={"results": FAKE_PYTHON_RESULTS})
        else:
            return httpx.Response(500)

    respx.post("http://localhost:8000/search").mock(side_effect=side_effect)
    result = await _handle_search_all({"query": "anything", "n_results": 9})
    text = result[0].text
    # All three domains should appear in the merged results
    assert "docker-compose.md" in text      # devops
    assert "crete-guide.md" in text        # travel
    assert "fluent-python.pdf" in text      # python


@pytest.mark.asyncio
@respx.mock
async def test_search_all_fanout_on_500():
    """Unified /search 500 → fan-out to per-domain endpoints."""
    call_count = {"n": 0}

    def side_effect(request):
        call_count["n"] += 1
        body = json.loads(request.content)
        domain = body.get("domain", "")
        if domain == "devops":
            return httpx.Response(200, json={"results": FAKE_RESULTS})
        elif domain == "travel":
            return httpx.Response(200, json={"results": FAKE_TRAVEL_RESULTS})
        else:
            return httpx.Response(500, json={"error": "server error"})

    respx.post("http://localhost:8000/search").mock(side_effect=side_effect)
    result = await _handle_search_all({"query": "anything"})
    text = result[0].text
    assert "docker-compose.md" in text or "crete-guide.md" in text


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
                {"name": "travel", "documents": 38},
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
        return_value=httpx.Response(200, json={"domains": ["devops", "travel"]})
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
