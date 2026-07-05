"""
dev-rag evaluation harness — retrieval runner.

OBS-004 fixes:
  - cross_domain questions post domain="devops" fan-out rather than domain=None
  - graph lift scoring is gated behind a GRAPH_ENDPOINT_AVAILABLE flag
    (defaults False until /search/graph is implemented)
"""
import httpx
from dataclasses import dataclass

from dev_rag.settings import settings

RAG_BASE = "http://localhost:8000"

# OBS-004: gate graph endpoint off until /search/graph is implemented
GRAPH_ENDPOINT_AVAILABLE = False


@dataclass
class RetrievalResult:
    question_id: str
    question: str
    results: list[dict]   # each: {"source", "content", "relevance_score"}
    graph_results: list[dict] | None = None


async def run_question(
    q,   # EvalQuestion
    n_results: int = 5,
    include_graph: bool = False,
) -> RetrievalResult:
    async with httpx.AsyncClient(timeout=30) as client:

        # OBS-004: cross_domain questions fan out to each domain separately
        # rather than posting domain=None (which would fail SearchRequest validation)
        if q.domain == "cross_domain":
            results = await _run_cross_domain(client, q.question, n_results)
            return RetrievalResult(
                question_id=q.id,
                question=q.question,
                results=results,
            )

        payload = {
            "query": q.question,
            "domain": q.domain,
            "n_results": n_results,
        }
        r = await client.post(f"{RAG_BASE}/search", json=payload)
        r.raise_for_status()
        data = r.json()

        # OBS-004: graph lift only attempted if endpoint exists
        graph_results = None
        if include_graph and q.requires_graph and GRAPH_ENDPOINT_AVAILABLE:
            gr = await client.post(f"{RAG_BASE}/search/graph", json=payload)
            if gr.status_code == 200:
                graph_results = gr.json().get("results", [])

    return RetrievalResult(
        question_id=q.id,
        question=q.question,
        results=data.get("results", []),
        graph_results=graph_results,
    )


async def _run_cross_domain(
    client: httpx.AsyncClient,
    query: str,
    n_results: int,
) -> list[dict]:
    """Fan-out to every valid domain for cross-domain questions."""
    import asyncio
    domains = settings.valid_domains
    per_domain = max(1, n_results // len(domains))

    tasks = [
        client.post(f"{RAG_BASE}/search", json={
            "query": query,
            "domain": domain,
            "n_results": per_domain,
        })
        for domain in domains
    ]
    responses = await asyncio.gather(*tasks, return_exceptions=True)

    results = []
    for domain, resp in zip(domains, responses):
        if isinstance(resp, Exception):
            continue
        for r in resp.json().get("results", []):
            r.setdefault("domain", domain)
            results.append(r)
    return results
