"""Tests for dev_rag.agent — the search_corpus Pydantic AI capability.

Never constructs the real AnthropicProvider (requires a real API key and hits the network):
every test either calls search_corpus directly or passes build_agent(model=FunctionModel(...))
so the real provider path is never exercised. Mirrors tests/test_api.py's convention of never
loading real BGE-M3/reranker models.
"""
import pytest
from pydantic_ai.exceptions import ModelRetry, UserError
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import FunctionModel

import dev_rag.agent as agent
from dev_rag.api import SearchResult
from dev_rag.settings import settings

CANNED_RESULTS = [
    SearchResult(
        chunk_id="c1",
        source="Some Book",
        domain="ai",
        content="RAG combines retrieval and generation.",
        relevance_score=0.9,
    )
]


def test_search_corpus_returns_perform_search_results(monkeypatch):
    captured = {}

    def fake_perform_search(*, query, domain, n_results=5):
        captured["args"] = (query, domain, n_results)
        return CANNED_RESULTS, False

    monkeypatch.setattr(agent, "perform_search", fake_perform_search)

    results = agent.search_corpus("what is RAG", "ai", n_results=3)

    assert results == CANNED_RESULTS
    assert captured["args"] == ("what is RAG", "ai", 3)


def test_search_corpus_rejects_invalid_domain(monkeypatch):
    def fail_if_called(*, query, domain, n_results=5):
        raise AssertionError("perform_search should not be called for an invalid domain")

    monkeypatch.setattr(agent, "perform_search", fail_if_called)

    with pytest.raises(ModelRetry):
        agent.search_corpus("what is RAG", "not_a_domain")


def test_build_agent_raises_without_api_key(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    # AnthropicProvider falls back to os.environ["ANTHROPIC_API_KEY"] when the
    # explicit api_key is falsy — clear it too, or this test would silently
    # pass-through on a machine that has the real var exported.
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(UserError):
        agent.build_agent()


def test_agent_run_calls_search_corpus_and_synthesizes_answer(monkeypatch):
    def fake_perform_search(*, query, domain, n_results=5):
        return CANNED_RESULTS, False

    monkeypatch.setattr(agent, "perform_search", fake_perform_search)

    calls = {"n": 0}

    def model_fn(messages, info):
        calls["n"] += 1
        if calls["n"] == 1:
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name="search_corpus",
                        args={"query": "what is RAG", "domain": "ai"},
                    )
                ]
            )
        return ModelResponse(
            parts=[TextPart(content="RAG combines retrieval and generation [Some Book].")]
        )

    a = agent.build_agent(model=FunctionModel(model_fn))
    result = a.run_sync("what is RAG?")

    assert calls["n"] == 2
    assert "Some Book" in result.output
