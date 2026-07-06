"""
dev-rag evaluation harness entry point.

Usage:
    uv run python eval/run_eval.py --domain devops
    uv run python eval/run_eval.py --category security negative
    uv run python eval/run_eval.py --compare eval/baselines/2026-07-06_hybrid_rrf.json
    uv run python eval/run_eval.py --domain devops --no-save

Spec: planning/dev-rag-evaluation-strategy.md (§run_eval.py). The server
must be running (see docs/RUNBOOK.md); the run's config block records the
server's /health search_mode + reranker state so saved baselines are
self-describing.
"""
import argparse
import asyncio
from pathlib import Path

import httpx

from loader import load_questions
from reporter import is_failure, print_compare, print_report, save_results
from runner import run_question
from scorer import compute_aggregate_metrics, score_question

RESULTS_DIR = Path(__file__).resolve().parent / "results"


def server_config(base_url: str) -> dict:
    """Read /health so the saved results record what they measured."""
    try:
        h = httpx.get(f"{base_url}/health", timeout=10).json()
    except httpx.HTTPError as exc:
        raise SystemExit(
            f"Cannot reach dev-rag server at {base_url} ({exc}). "
            "Start it first — see docs/RUNBOOK.md §5."
        )
    return {
        "base_url": base_url,
        "search_mode": h.get("search_mode"),
        "reranker_enabled": h.get("reranker_enabled"),
        "stores_in_sync": h.get("stores_in_sync"),
    }


async def main(args) -> None:
    config = server_config(args.base_url)
    if args.label:
        config["label"] = args.label

    questions = load_questions()
    if args.domain:
        questions = [q for q in questions if q.domain == args.domain]
    if args.category:
        questions = [q for q in questions if q.category in args.category]
    if not questions:
        raise SystemExit("No questions matched the filters.")

    mode = config["search_mode"] + (
        " + reranker" if config["reranker_enabled"] else ""
    )
    print(f"Running {len(questions)} questions against {args.base_url} [{mode}] ...")

    scores = []
    for q in questions:
        result = await run_question(
            q, n_results=5, include_graph=args.graph, base_url=args.base_url,
        )
        score = score_question(q, result)
        scores.append(score)
        print("." if not is_failure(score) else "F", end="", flush=True)
    print()

    aggregate = compute_aggregate_metrics(scores)
    print_report(aggregate, scores, search_mode=config["search_mode"])

    if args.save:
        save_results(aggregate, scores, RESULTS_DIR, config=config)

    if args.compare:
        print_compare(aggregate, Path(args.compare))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="dev-rag evaluation harness")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--domain",
                        choices=["devops", "travel", "python", "ai", "cross_domain"])
    parser.add_argument("--category", nargs="+")
    parser.add_argument("--graph", action="store_true",
                        help="include graph traversal (gated off until /search/graph exists)")
    parser.add_argument("--compare",
                        help="path to a previous results JSON for delta comparison")
    parser.add_argument("--label", help="label recorded in the saved config block")
    parser.add_argument("--no-save", dest="save", action="store_false",
                        help="don't write eval/results/<timestamp>.json")
    asyncio.run(main(parser.parse_args()))
