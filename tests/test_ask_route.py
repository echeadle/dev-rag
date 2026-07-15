"""Tests for POST /ask — the HTTP surface over dev_rag.agent's search_corpus agent.

Never constructs the real AnthropicProvider or touches real stores: build_agent is
monkeypatched to inject a FunctionModel-backed agent (mirrors tests/test_agent.py),
and perform_search is monkeypatched directly so search_corpus never hits BGE-M3/
ChromaDB/SQLite (mirrors tests/test_api.py's convention of never loading real models).
"""
import pytest
from fastapi.testclient import TestClient
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import FunctionModel

import dev_rag.agent as agent
from dev_rag.api import SearchResult, app
from dev_rag.settings import settings

client = TestClient(app)

CANNED_RESULTS = [
    SearchResult(
        chunk_id="c1",
        source="Some Book",
        domain="ai",
        content="RAG combines retrieval and generation.",
        relevance_score=0.9,
    )
]


@pytest.fixture(autouse=True)
def has_api_key(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")


def test_ask_returns_503_without_api_key(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    r = client.post("/ask", json={"query": "what is RAG?"})

    assert r.status_code == 503
    assert "ANTHROPIC_API_KEY" in r.json()["detail"]


def test_ask_returns_synthesized_answer(monkeypatch):
    monkeypatch.setattr(agent, "perform_search", lambda *, query, domain, n_results=5: (CANNED_RESULTS, False))

    calls = {"n": 0}

    def model_fn(messages, info):
        calls["n"] += 1
        if calls["n"] == 1:
            return ModelResponse(
                parts=[ToolCallPart(tool_name="search_corpus", args={"query": "what is RAG", "domain": "ai"})]
            )
        return ModelResponse(parts=[TextPart(content="RAG combines retrieval and generation [Some Book].")])

    real_build_agent = agent.build_agent
    monkeypatch.setattr(agent, "build_agent", lambda: real_build_agent(model=FunctionModel(model_fn)))

    r = client.post("/ask", json={"query": "what is RAG?"})

    assert r.status_code == 200
    body = r.json()
    assert "Some Book" in body["answer"]
    assert body["query"] == "what is RAG?"
    assert calls["n"] == 2


def test_ask_returns_502_on_agent_failure(monkeypatch):
    def failing_model_fn(messages, info):
        raise RuntimeError("simulated provider outage")

    real_build_agent = agent.build_agent
    monkeypatch.setattr(agent, "build_agent", lambda: real_build_agent(model=FunctionModel(failing_model_fn)))

    r = client.post("/ask", json={"query": "what is RAG?"})

    assert r.status_code == 502
    assert "simulated provider outage" not in r.text
