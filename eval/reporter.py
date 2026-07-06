"""Print and save evaluation results.

Spec: planning/dev-rag-evaluation-strategy.md (§reporter.py), extended:
- saved JSON includes a `config` block (search_mode, reranker on/off,
  candidates) so every baseline is self-describing;
- negative precision prints "n/a (RRF has no relevance scale)" when the
  run couldn't compute it (FBL-005 — plain hybrid runs);
- print_compare() lives here so run_eval stays thin.
"""
import json
from datetime import datetime
from pathlib import Path

METRICS = [
    ("Retrieval@1",            "retrieval_at_1",         0.60),
    ("Retrieval@3",            "retrieval_at_3",         0.80),
    ("Retrieval@5",            "retrieval_at_5",         0.85),
    ("MRR",                    "mrr",                    0.60),
    ("Chunk Match",            "chunk_match",            0.70),
    ("Negative Precision",     "negative_precision",     0.90),
    ("Hallucination Rate",     "hallucination_rate",     None),   # lower is better
    ("Paraphrase Consistency", "paraphrase_consistency", 0.80),
    ("Source Precision",       "source_precision",       0.75),
    ("Graph Lift",             "graph_lift",             0.0),
    ("Composite Score",        "composite_score",        0.70),
]


def print_report(aggregate: dict, scores: list, search_mode: str | None = None) -> None:
    print("\n" + "=" * 60)
    print("dev-rag Evaluation Report")
    print(f"Run: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"Questions scored: {aggregate['questions_scored']} "
          f"(with expected_source: {aggregate['questions_with_expected_source']}, "
          f"negatives: {aggregate['questions_negative']})")
    print("=" * 60)

    for label, key, target in METRICS:
        val = aggregate.get(key)
        if val is None:
            reason = ""
            if key in ("negative_precision", "hallucination_rate") and search_mode == "hybrid":
                reason = "(RRF has no relevance scale — FBL-005; rerun with reranker or dense)"
            print(f"  {label:<28} {'n/a':>7}     {reason}")
            continue
        pct = f"{val:.1%}"
        if key == "hallucination_rate":
            status = "✓" if val <= 0.10 else "✗"
        elif target is not None:
            status = "✓" if val >= target else "✗"
        else:
            status = " "
        target_str = f"(target: {target:.0%})" if target is not None else ""
        print(f"  {label:<28} {pct:>7}  {status}  {target_str}")

    print("=" * 60)

    failures = [s for s in scores if is_failure(s)]
    if failures:
        print(f"\nFailed questions ({len(failures)}):")
        for s in failures:
            print(f"  [{s.question_id}] {s.failure_mode} — top-1: {s.top_1_source}")
    print()


def is_failure(score) -> bool:
    if score.retrieval_at_3 is not None and score.retrieval_at_3 == 0.0:
        return True
    if score.negative_correct is False:
        return True
    return False


def save_results(aggregate: dict, scores: list, output_dir: Path,
                 config: dict | None = None) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    path = output_dir / f"{timestamp}.json"
    path.write_text(json.dumps({
        "timestamp": timestamp,
        "config": config or {},
        "aggregate": aggregate,
        "questions": [vars(s) for s in scores],
    }, indent=2))
    print(f"Results saved to {path}")
    return path


def print_compare(aggregate: dict, baseline_path: Path) -> None:
    """Delta of this run vs a saved baseline JSON (R@3, MRR, composite)."""
    prev = json.loads(Path(baseline_path).read_text())
    prev_agg = prev.get("aggregate", {})
    label = prev.get("config", {}).get("label") or prev.get("timestamp", str(baseline_path))
    print(f"\nComparison vs baseline [{label}]:")
    for key in ("retrieval_at_1", "retrieval_at_3", "mrr", "composite_score"):
        prev_val, curr_val = prev_agg.get(key), aggregate.get(key)
        if prev_val is None or curr_val is None:
            print(f"  {key:<28} n/a (missing in one run)")
            continue
        delta = curr_val - prev_val
        sign = "+" if delta >= 0 else ""
        print(f"  {key:<28} {prev_val:.1%} -> {curr_val:.1%}  ({sign}{delta:.1%})")
