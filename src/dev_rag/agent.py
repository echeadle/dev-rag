"""
dev-rag Pydantic AI agent — search_corpus capability over the hybrid search pipeline.

Phase 8 decomposition (see harness memory agent-py-pydantic-ai-capabilities.md, 2026-07-10):
GraphRAG (graph.py, ADR-005) has no spec yet, but a search-only agent doesn't need it — this
wraps the already-working hybrid search (api.py's perform_search) in a Pydantic AI Agent using
the `capabilities` API. A `search_graph` capability can be added later once graph.py exists;
that does NOT reopen ADR-007's deferral.
"""
from pydantic_ai import Agent
from pydantic_ai.capabilities import Capability
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.models import KnownModelName, Model
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.providers.anthropic import AnthropicProvider

from .api import SearchResult, perform_search
from .settings import settings

AGENT_INSTRUCTIONS = (
    "You are a research assistant answering questions from the user's personal technical "
    "library using the search_corpus tool. Only answer from retrieved passages — say so "
    "plainly if the corpus doesn't cover something rather than guessing. Always cite the "
    "source book for factual claims."
)

# defer_loading=False (Ed's call, 2026-07-15): search_corpus is currently the agent's only
# tool, used on essentially every turn — deferring it would add a load_capability round trip
# for zero context savings. Revisit once search_graph exists as a genuine second bundle.
search_capability = Capability(
    id="search_corpus",
    description="Search the dev-rag personal library (devops, python, ai domains).",
    instructions=(
        f"Call search_corpus with one of these domains: {', '.join(settings.valid_domains)}. "
        "If unsure which domain holds the answer, try the most likely one first; call again "
        "with a different domain if the results don't look relevant."
    ),
)


@search_capability.tool_plain
def search_corpus(query: str, domain: str, n_results: int = 5) -> list[SearchResult]:
    """Search one domain of the dev-rag corpus for relevant passages."""
    # domain is model-chosen input, not validated by perform_search (unlike the
    # /search route's SearchRequest) — an invalid domain would otherwise silently
    # return zero results with no signal for the model to self-correct on.
    if domain not in settings.valid_domains:
        raise ModelRetry(
            f"'{domain}' is not a valid domain. Valid domains: "
            f"{', '.join(settings.valid_domains)}."
        )
    # RRF-only by default (force_rerank=False) — matches ADR-012 and the existing
    # single-domain MCP tools; stays fast even if the agent checks multiple domains in one turn.
    results, _used_reranker = perform_search(query=query, domain=domain, n_results=n_results)
    return results


def build_agent(model: Model | KnownModelName | str | None = None) -> Agent:
    """Construct the dev-rag agent. Pass `model=` (e.g. a TestModel or FunctionModel) in
    tests to avoid constructing the real Anthropic provider, which raises immediately if
    settings.anthropic_api_key is unset — this repo has no .env by default."""
    if model is None:
        model = AnthropicModel(
            settings.agent_model,
            provider=AnthropicProvider(api_key=settings.anthropic_api_key),
        )
    return Agent(
        model,
        name="dev_rag_agent",
        instructions=AGENT_INSTRUCTIONS,
        capabilities=[search_capability],
    )


def _main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Ask the dev-rag agent a question")
    parser.add_argument("query", help="Natural-language question")
    args = parser.parse_args()

    if not settings.anthropic_api_key:
        raise SystemExit("ANTHROPIC_API_KEY not set — add it to .env before running the agent.")

    agent = build_agent()
    result = agent.run_sync(args.query)
    print(result.output)


if __name__ == "__main__":
    _main()
