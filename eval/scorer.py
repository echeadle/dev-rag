"""
dev-rag evaluation harness — metric computation.

OBS-001 fix: negative precision reads `relevance_score`, not `score`.
OBS-003 note: expected_source must be populated on questions for
  Retrieval@k, MRR, and composite to compute. Questions with
  expected_source=null contribute only to chunk_match and
  negative_precision metrics.
FBL-002 fix: expected_source matching is EXACT everywhere (== on the
  ingested filename) — Retrieval@k and MRR agree. Substring matching
  would blur the two devops books, whose only discriminator is `source`.
FBL-005 fix: negative precision is per-mode (see _negative_correct) —
  under plain hybrid RRF it is None/not-computable, never a fake pass.
"""
from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class QuestionScore:
    question_id: str
    category: str
    failure_mode: str
    retrieval_at_1: float | None = None
    retrieval_at_3: float | None = None
    retrieval_at_5: float | None = None
    mrr: float | None = None
    chunk_match: float | None = None
    negative_correct: bool | None = None
    paraphrase_group: str | None = None
    top_1_source: str | None = None
    graph_lift: float | None = None


def score_question(q, result) -> QuestionScore:
    sources = [r.get("source", "") for r in result.results]
    top_chunk = result.results[0].get("content", "") if result.results else ""

    score = QuestionScore(
        question_id=q.id,
        category=q.category,
        failure_mode=q.failure_mode,
        top_1_source=sources[0] if sources else None,
        paraphrase_group=getattr(q, "paraphrase_group", None),
    )

    # Retrieval@k and MRR — only when expected_source is set (OBS-003 note)
    if q.expected_source and not q.no_answer:
        score.retrieval_at_1 = 1.0 if q.expected_source in sources[:1] else 0.0
        score.retrieval_at_3 = 1.0 if q.expected_source in sources[:3] else 0.0
        score.retrieval_at_5 = 1.0 if q.expected_source in sources[:5] else 0.0

        score.mrr = 0.0
        for rank, source in enumerate(sources, 1):
            if source == q.expected_source:   # FBL-002: exact, like Retrieval@k
                score.mrr = 1.0 / rank
                break

    # Chunk content match
    if q.expected_chunk_contains:
        score.chunk_match = 1.0 if all(
            s.lower() in top_chunk.lower()
            for s in q.expected_chunk_contains
        ) else 0.0

    # Negative precision — OBS-001: read relevance_score; FBL-005: per-mode
    if q.no_answer:
        score.negative_correct = _negative_correct(result)

    return score


def _negative_correct(result) -> bool | None:
    """
    FBL-005: "no answer" is only judgeable on a score that carries
    relevance semantics. Cross-encoder logits (< 0 ≈ irrelevant, sigmoid
    < 0.5) and dense cosine (< 0.5) qualify. Plain hybrid RRF scores
    encode RANK, not relevance (max ≈ 0.033), so no threshold on them
    means anything — return None (metric not computable this run) rather
    than the old always-true `< 0.5` fake pass.
    """
    if not result.results:
        return True
    top = result.results[0]
    if top.get("reranker_score") is not None:
        return top["reranker_score"] < 0.0
    if getattr(result, "search_mode", None) == "dense":
        return top.get("relevance_score", 1.0) < 0.5
    return None


def compute_aggregate_metrics(scores: list[QuestionScore]) -> dict:
    def mean(vals):
        vals = [v for v in vals if v is not None]
        return sum(vals) / len(vals) if vals else None

    # Paraphrase consistency
    groups = defaultdict(list)
    for s in scores:
        if s.paraphrase_group:
            groups[s.paraphrase_group].append(s.top_1_source)

    paraphrase_consistency = mean([
        1.0 if len(set(srcs)) == 1 else 0.0
        for srcs in groups.values()
    ]) if groups else None

    source_specific = [s for s in scores if s.category == "source_specific"]
    negative = [s for s in scores if s.negative_correct is not None]
    graph_questions = [s for s in scores if s.graph_lift is not None]

    r3  = mean([s.retrieval_at_3 for s in scores])
    mrr = mean([s.mrr for s in scores])
    cm  = mean([s.chunk_match for s in scores])
    neg = mean([1.0 if s.negative_correct else 0.0 for s in negative])
    pc  = paraphrase_consistency
    sp  = mean([s.retrieval_at_1 for s in source_specific])

    # OBS-003: composite only computes when all components are available
    composite = None
    non_none = [v for v in [r3, mrr, cm, neg] if v is not None]
    if len(non_none) >= 2:   # partial composite rather than all-or-nothing
        weights = [(r3, 0.35), (mrr, 0.25), (cm, 0.25), (neg, 0.15)]
        total_w = sum(w for v, w in weights if v is not None)
        composite = sum(v * w for v, w in weights if v is not None) / total_w

    return {
        "retrieval_at_1":         mean([s.retrieval_at_1 for s in scores]),
        "retrieval_at_3":         r3,
        "retrieval_at_5":         mean([s.retrieval_at_5 for s in scores]),
        "mrr":                    mrr,
        "chunk_match":            cm,
        "negative_precision":     neg,
        "hallucination_rate":     1 - neg if neg is not None else None,
        "paraphrase_consistency": pc,
        "source_precision":       sp,
        "graph_lift":             mean([s.graph_lift for s in graph_questions]),
        "composite_score":        composite,
        "questions_scored":       len(scores),
        # OBS-003: surface how many questions contributed to each metric
        "questions_with_expected_source": sum(
            1 for s in scores if s.retrieval_at_3 is not None
        ),
        "questions_negative":     len(negative),
    }
