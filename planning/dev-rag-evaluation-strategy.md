# dev-rag Evaluation Strategy & Scoring Specification

**Version:** 2.0  
**Date:** June 2026  
**Status:** Planning — implement after Phase 1 (system build) is complete

---

## Purpose

This document captures the complete strategy for building and running an evaluation
harness for dev-rag. It covers question design, question categories, the YAML schema
for encoding questions, scoring metrics, and the implementation spec for the harness
itself.

The goal is not merely to collect questions. The goal is to build a benchmark that:

1. Reveals specific retrieval weaknesses
2. Allows future architectural changes to be measured objectively
3. Prevents regressions when components are swapped (ChromaDB → pgvector, adding a reranker, etc.)
4. Transforms architecture discussions into measurable engineering decisions

---

## Core Principle

The real value of an evaluation question is not the answer.

The value is:

> What failure mode does this question expose?

When creating a new evaluation question, always ask:

- What weakness am I testing?
- What retrieval behavior am I validating?
- What failure would indicate a problem in the retrieval pipeline?

---

## Recommended Development Approach

### Phase 1 — Build the System First

Do not write eval questions until the system works end-to-end.
Premature evaluation is noise. Focus on:

1. Ingestion (PyMuPDF, httpx)
2. Chunking (sliding window)
3. Embeddings (BGE-M3)
4. ChromaDB storage
5. Retrieval (vector search + graph traversal)
6. MCP integration
7. End-to-end search via Claude Code

### Phase 2 — Collect Real Questions

Once the system is working, create and continually expand:

```
data/evaluation/
├── devops_questions.yaml
├── travel_questions.yaml
└── cross_domain_questions.yaml
```

Every time you encounter a genuinely useful question during real usage, add it.
Questions that arise organically from real work are almost always better than
questions invented in the abstract.

### Phase 3 — Add Measurement

After collecting 50–100 realistic questions:

- Run the scoring harness (`eval/run_eval.py`)
- Measure retrieval quality against defined metrics
- Establish a baseline score before making any pipeline changes
- Compare architecture changes against the baseline
- Detect regressions automatically in CI

---

## Question YAML Schema

Every question is a YAML record. The schema is designed so the harness can score
automatically without manual inspection for most cases.

```yaml
- id: devops-001
  question: "What is the production-safe way to store secrets in Docker Compose?"
  domain: devops
  category: security
  failure_mode: production_vs_tutorial_confusion
  expected_source: "docker-deep-dive.pdf"   # null if any source is acceptable
  expected_chunk_contains:                   # all strings must appear in top-1 chunk
    - "Docker secrets"
    - "secrets:"
  no_answer: false                           # true = corpus should NOT answer this
  requires_graph: false                      # true = answer requires graph traversal
  requires_multi_source: false               # true = answer spans multiple documents
  notes: >
    Tests whether the system retrieves production secret-management guidance
    rather than the insecure env-var pattern that dominates tutorials.
```

### Schema Field Reference

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | yes | Unique identifier, e.g. `devops-001` |
| `question` | string | yes | The natural language question |
| `domain` | string | yes | `devops`, `travel`, or `cross_domain` |
| `category` | string | yes | See question categories below |
| `failure_mode` | string | yes | The specific weakness being tested |
| `expected_source` | string/null | yes | Filename or URL that should appear in results; null = any |
| `expected_chunk_contains` | list[string] | no | Strings that must appear in the top result chunk |
| `no_answer` | bool | yes | Whether the correct answer is "not in corpus" |
| `requires_graph` | bool | yes | Whether graph traversal is needed for a complete answer |
| `requires_multi_source` | bool | yes | Whether the answer spans multiple documents |
| `notes` | string | no | Human-readable rationale for the question |

---

## Question Categories

### 1. Factual

Tests basic retrieval and semantic matching against a clear, single-source answer.

```
What is a Docker bridge network?
```

**Failure mode tested:** Basic semantic mismatch — the embedding model fails to
connect the query vocabulary to the document vocabulary.

---

### 2. Troubleshooting

Tests retrieval of operational guidance and problem-solving content.

```
Why can't two containers on the same host communicate?
```

**Failure mode tested:** Symptom-description queries failing to match
cause-explanation chunks (common when chunking splits problem from solution).

---

### 3. Comparison

Tests multi-concept retrieval and comparative information gathering.

```
Compare Docker Secrets and HashiCorp Vault for secret management.
```

**Failure mode tested:** Retrieval returning only one side of the comparison,
or ranking one source concept above the other without coverage of both.

---

### 4. Security

Tests retrieval of security guidance and best-practice content.

```
Why should containers not run as root?
```

**Failure mode tested:** Production-vs-tutorial confusion — the system returning
the insecure tutorial pattern when the question asks for security rationale.

---

### 5. Architecture

Tests architectural reasoning and decision-support content.

```
When should a team adopt Kubernetes instead of Docker Compose?
```

**Failure mode tested:** Decision-support queries retrieving factual descriptions
instead of contextual guidance about when and why to make a choice.

---

### 6. Source-Specific

Tests provenance, source ranking, and citation accuracy.

```
According to Docker Deep Dive, what are the key container security recommendations?
```

**Failure mode tested:** The system returning correct content from the wrong source,
or failing to attribute answers to the correct book/URL.

---

### 7. Cross-Document

Tests multi-source retrieval and information synthesis.

```
How do Python applications, Docker containers, and PostgreSQL work together in production?
```

**Failure mode tested:** Single-source bias — the retrieval system returning all
chunks from one document when the complete answer requires synthesising across
multiple books or sources.

---

### 8. Negative (No-Answer)

**New in v2.** Tests whether the system correctly handles questions outside the corpus.

```
What are the best practices for configuring Podman rootless containers?
```

*Expected: empty result set or explicit "not found" — not hallucinated Docker chunks.*

**Failure mode tested:** Hallucination-via-retrieval — the system returning
plausible-but-wrong chunks when the correct answer is that the corpus doesn't
cover this topic. This is one of the most dangerous failure modes in practice
because confident wrong answers are harder to detect than empty results.

---

### 9. Chunk Boundary

**New in v2.** Tests whether the chunking strategy preserves complete answers.

```
What are the complete steps to configure a Docker bridge network according to Docker Deep Dive?
```

*Designed to require two or more adjacent chunks for a complete answer.*

**Failure mode tested:** Chunker splitting a multi-step explanation mid-sequence,
causing retrieval to return only the first half of a procedure or the last half
of an explanation. If the top-1 chunk is incomplete, the chunking window or
overlap settings need adjustment.

---

### 10. Adversarial Paraphrase

**New in v2.** Tests embedding model robustness to vocabulary variation.

Each paraphrase set contains 3 different phrasings of the same question.
All three should return the same top chunk.

```yaml
- id: devops-para-001a
  question: "How do Docker secrets work?"
  paraphrase_group: docker-secrets-mechanism
  ...

- id: devops-para-001b
  question: "What is the mechanism for passing sensitive data to containers securely?"
  paraphrase_group: docker-secrets-mechanism
  ...

- id: devops-para-001c
  question: "Explain Docker's secret management system."
  paraphrase_group: docker-secrets-mechanism
  ...
```

**Failure mode tested:** Vocabulary mismatch between query phrasing and indexed
chunk text. If paraphrase 001a scores 0.95 and 001c scores 0.40, the embedding
model is sensitive to surface form in a way that will produce inconsistent
real-world retrieval. This drives chunking decisions (add more context per chunk)
and embedding model choices.

---

### 11. GraphRAG-Specific

**New in v2.** Tests questions that *require* graph traversal and cannot be answered
by vector search alone.

```
What concepts do I need to understand before Docker networking makes sense?
How are Python decorators conceptually related to Docker entrypoints?
```

**Failure mode tested:** Graph traversal returning no value over pure vector search —
which would mean the NetworkX knowledge graph isn't earning its place in the
architecture. Every GraphRAG question should have a paired "vector-only" run for
comparison. If graph traversal never improves results, the graph should be removed.

---

### 12. Staleness / Update Validation

**New in v2.** Tests the document update pipeline (ADR-006).

These questions are run as part of an update test fixture, not as standalone eval:

1. Ingest document version A
2. Run retrieval — expect content from version A
3. Run the update pipeline with version B
4. Re-run retrieval — expect content from version B, not version A

**Failure mode tested:** Old chunks surviving an update (wholesale replacement
didn't fully delete), or new chunks missing after an incremental upsert
(content hash comparison failed silently).

---

## Initial Evaluation Questions

### DevOps Questions

```yaml
- id: devops-001
  question: "What is the production-safe way to store secrets in Docker Compose and why are environment variables not sufficient?"
  domain: devops
  category: security
  failure_mode: production_vs_tutorial_confusion
  expected_source: null
  expected_chunk_contains:
    - "secrets"
  no_answer: false
  requires_graph: false
  requires_multi_source: false
  notes: >
    Core motivating question for the entire dev-rag project. If this doesn't
    return production secret-management guidance, the corpus or retrieval has
    a fundamental problem.

- id: devops-002
  question: "What is the difference between bridge, host, and overlay networks in Docker, and when should each be used?"
  domain: devops
  category: comparison
  failure_mode: single_concept_bias
  expected_source: null
  expected_chunk_contains:
    - "bridge"
    - "host"
  no_answer: false
  requires_graph: false
  requires_multi_source: false
  notes: >
    Tests multi-concept retrieval. All three network types should appear in
    the result set. If only bridge is returned, the retrieval is failing on
    the comparison dimension.

- id: devops-003
  question: "Why is running a container as root considered a security risk and what are the recommended alternatives?"
  domain: devops
  category: security
  failure_mode: best_practice_vs_default_behavior
  expected_source: null
  expected_chunk_contains:
    - "root"
  no_answer: false
  requires_graph: false
  requires_multi_source: false
  notes: >
    Tests security guidance retrieval. The system should return rationale
    (why root is dangerous) and alternatives (user namespaces, non-root
    USER directive), not just a description of how root works.

- id: devops-004
  question: "At what point does an organization outgrow Docker Compose and need Kubernetes?"
  domain: devops
  category: architecture
  failure_mode: description_vs_decision_support
  expected_source: null
  expected_chunk_contains: []
  no_answer: false
  requires_graph: false
  requires_multi_source: true
  notes: >
    Tests architectural decision-support retrieval. The answer should
    discuss thresholds and tradeoffs, not just describe Kubernetes features.

- id: devops-005
  question: "What techniques are commonly used to achieve zero-downtime deployments and what tradeoffs does each approach have?"
  domain: devops
  category: architecture
  failure_mode: single_technique_bias
  expected_source: null
  expected_chunk_contains: []
  no_answer: false
  requires_graph: false
  requires_multi_source: true
  notes: >
    Tests cross-document retrieval. Blue-green, rolling, and canary
    deployments may each live in different source documents. All three
    should appear in results.

- id: devops-006
  question: "According to Docker Deep Dive, what are the most important container security recommendations?"
  domain: devops
  category: source_specific
  failure_mode: provenance_failure
  expected_source: "docker-deep-dive.pdf"
  expected_chunk_contains:
    - "security"
  no_answer: false
  requires_graph: false
  requires_multi_source: false
  notes: >
    Tests source attribution. If the correct content is returned from the
    wrong source, or the expected source doesn't rank first, provenance
    tracking has a problem.

- id: devops-007
  question: "What are the best practices for managing Podman rootless containers in production?"
  domain: devops
  category: negative
  failure_mode: hallucination_via_retrieval
  expected_source: null
  expected_chunk_contains: []
  no_answer: true
  requires_graph: false
  requires_multi_source: false
  notes: >
    Negative test. If the corpus doesn't contain Podman content, the
    system should return empty results, not Docker chunks dressed up as
    Podman guidance. A false positive here is a serious retrieval failure.

- id: devops-008
  question: "What are the complete steps to configure a custom Docker bridge network as described in your sources?"
  domain: devops
  category: chunk_boundary
  failure_mode: chunker_splits_procedure
  expected_source: null
  expected_chunk_contains:
    - "docker network create"
  no_answer: false
  requires_graph: false
  requires_multi_source: false
  notes: >
    Designed to require at least two adjacent chunks for a complete answer.
    If the top-1 result is clearly incomplete (cuts off mid-step), the
    chunk overlap setting needs to increase.

- id: devops-para-001a
  question: "How do Docker secrets work?"
  domain: devops
  category: adversarial_paraphrase
  failure_mode: vocabulary_mismatch
  paraphrase_group: docker-secrets-mechanism
  expected_source: null
  expected_chunk_contains: ["secrets"]
  no_answer: false
  requires_graph: false
  requires_multi_source: false

- id: devops-para-001b
  question: "What is the mechanism for passing sensitive data to containers securely?"
  domain: devops
  category: adversarial_paraphrase
  failure_mode: vocabulary_mismatch
  paraphrase_group: docker-secrets-mechanism
  expected_source: null
  expected_chunk_contains: ["secrets"]
  no_answer: false
  requires_graph: false
  requires_multi_source: false

- id: devops-para-001c
  question: "Explain Docker's secret management system."
  domain: devops
  category: adversarial_paraphrase
  failure_mode: vocabulary_mismatch
  paraphrase_group: docker-secrets-mechanism
  expected_source: null
  expected_chunk_contains: ["secrets"]
  no_answer: false
  requires_graph: false
  requires_multi_source: false

- id: devops-graph-001
  question: "What concepts do I need to understand before Docker networking makes sense?"
  domain: devops
  category: graph_rag
  failure_mode: missing_prerequisite_chain
  expected_source: null
  expected_chunk_contains: []
  no_answer: false
  requires_graph: true
  requires_multi_source: true
  notes: >
    Requires graph traversal to identify prerequisite concept chains.
    Vector search alone will return networking chunks; graph traversal
    should additionally surface foundational concepts (namespaces, cgroups,
    Linux bridge interfaces) that the knowledge graph links as prerequisites.
```

---

## Scoring Metrics

### Metric 1: Retrieval@k (Primary metric)

**Definition:** Is the expected source present in the top-k results?

- **Retrieval@1** — expected source is the top result
- **Retrieval@3** — expected source is in the top 3
- **Retrieval@5** — expected source is in the top 5

**When to use:** All questions with a non-null `expected_source`.

**Target baseline:** Retrieval@3 ≥ 0.80 before shipping any pipeline change.
Retrieval@1 ≥ 0.60 is a reasonable initial target; 0.80+ indicates a mature system.

**Scoring:**
```
score = 1.0 if expected_source in results[:k] else 0.0
retrieval_at_k = mean(scores across all applicable questions)
```

---

### Metric 2: Mean Reciprocal Rank (MRR)

**Definition:** Where does the right answer rank on average?

```
MRR = mean(1 / rank_of_first_correct_result)
```

If the correct chunk is rank 1: score = 1.0  
If rank 2: score = 0.5  
If rank 3: score = 0.33  
If not in top 10: score = 0.0

**When to use:** All questions with a non-null `expected_source` or
`expected_chunk_contains`.

**Target baseline:** MRR ≥ 0.60 before making pipeline changes.

---

### Metric 3: Chunk Content Match

**Definition:** Do all strings in `expected_chunk_contains` appear in the
top-1 result chunk?

```
score = 1.0 if all(s in top_chunk.content for s in expected_chunk_contains) else 0.0
chunk_match = mean(scores across all applicable questions)
```

**When to use:** Questions where the answer vocabulary is predictable enough
to specify expected strings. Don't over-specify — one or two key terms is enough.

---

### Metric 4: Negative Precision (Hallucination Rate)

**Definition:** For questions where `no_answer = true`, what fraction of the
time does the system correctly return empty or below-threshold results?

```
negative_precision = (correct_empty_results / total_no_answer_questions)
hallucination_rate = 1 - negative_precision
```

**Target:** Hallucination rate ≤ 0.10. A system that hallucinates on more than
10% of out-of-corpus questions is not trustworthy for production guidance.

---

### Metric 5: Paraphrase Consistency

**Definition:** For each paraphrase group, do all phrasings return the same
top-1 source?

```
group_consistent = len(set(top_1_source for q in group)) == 1
paraphrase_consistency = mean(group_consistent across all groups)
```

**Target:** Paraphrase consistency ≥ 0.80. If three phrasings of the same
question return three different top chunks, the embedding model has a vocabulary
robustness problem.

---

### Metric 6: Graph Lift

**Definition:** For `requires_graph = true` questions, does adding graph
traversal improve Retrieval@3 compared to vector-only retrieval?

```
graph_lift = retrieval@3_with_graph - retrieval@3_without_graph
```

**Target:** Graph lift > 0.0 on at least 50% of graph-specific questions.
If graph lift is consistently zero or negative, the NetworkX graph is not
earning its place in the architecture and should be reconsidered.

---

### Metric 7: Source Precision (for source-specific questions)

**Definition:** For questions with `category = source_specific`, does the
`expected_source` rank first?

```
source_precision = mean(1.0 if top_1_source == expected_source else 0.0
                        for q in source_specific_questions)
```

**Target:** Source precision ≥ 0.75. If the correct book isn't ranking first
when explicitly asked about it, the metadata filtering or source weighting
in the retrieval pipeline has a problem.

---

### Composite Score

A single number for tracking overall system health over time:

```
composite = (
    0.30 * retrieval_at_3 +
    0.20 * mrr +
    0.20 * chunk_match +
    0.15 * (1 - hallucination_rate) +
    0.10 * paraphrase_consistency +
    0.05 * source_precision
)
```

Graph lift is tracked separately (it's an architectural signal, not an
end-to-end quality signal).

---

## Harness Implementation Spec

### File Layout

```
dev-rag/
├── data/
│   └── evaluation/
│       ├── devops_questions.yaml
│       ├── travel_questions.yaml
│       └── cross_domain_questions.yaml
├── eval/
│   ├── run_eval.py          # Main entry point
│   ├── loader.py            # Load and validate YAML question files
│   ├── runner.py            # Call dev-rag API for each question
│   ├── scorer.py            # Compute all metrics
│   ├── reporter.py          # Print and save results
│   └── results/             # Auto-created, gitignored
│       └── YYYY-MM-DD_HH-MM.json
```

---

### `loader.py` — Question Loading

```python
from dataclasses import dataclass, field
from pathlib import Path
import yaml


@dataclass
class EvalQuestion:
    id: str
    question: str
    domain: str
    category: str
    failure_mode: str
    no_answer: bool
    requires_graph: bool
    requires_multi_source: bool
    expected_source: str | None = None
    expected_chunk_contains: list[str] = field(default_factory=list)
    paraphrase_group: str | None = None
    notes: str = ""


def load_questions(paths: list[Path]) -> list[EvalQuestion]:
    questions = []
    for path in paths:
        raw = yaml.safe_load(path.read_text())
        for item in raw:
            questions.append(EvalQuestion(**item))
    return questions
```

---

### `runner.py` — Retrieval Runner

```python
import httpx
from dataclasses import dataclass

RAG_BASE = "http://localhost:8000"


@dataclass
class RetrievalResult:
    question_id: str
    question: str
    results: list[dict]   # each: {"source": str, "content": str, "score": float}
    graph_results: list[dict] | None = None   # populated for requires_graph=True


async def run_question(
    q: "EvalQuestion",
    n_results: int = 5,
    include_graph: bool = False,
) -> RetrievalResult:
    async with httpx.AsyncClient(timeout=30) as client:
        payload = {
            "query": q.question,
            "domain": q.domain if q.domain != "cross_domain" else None,
            "n_results": n_results,
        }
        r = await client.post(f"{RAG_BASE}/search", json=payload)
        r.raise_for_status()
        data = r.json()

        graph_results = None
        if include_graph and q.requires_graph:
            gr = await client.post(f"{RAG_BASE}/search/graph", json=payload)
            if gr.status_code == 200:
                graph_results = gr.json().get("results", [])

    return RetrievalResult(
        question_id=q.id,
        question=q.question,
        results=data.get("results", []),
        graph_results=graph_results,
    )
```

---

### `scorer.py` — Metric Computation

```python
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
    negative_correct: bool | None = None   # for no_answer questions
    paraphrase_group: str | None = None
    top_1_source: str | None = None
    graph_lift: float | None = None        # populated post-hoc


def score_question(q: "EvalQuestion", result: "RetrievalResult") -> QuestionScore:
    sources = [r.get("source", "") for r in result.results]
    top_chunk = result.results[0].get("content", "") if result.results else ""

    score = QuestionScore(
        question_id=q.id,
        category=q.category,
        failure_mode=q.failure_mode,
        top_1_source=sources[0] if sources else None,
        paraphrase_group=q.paraphrase_group,
    )

    # Retrieval@k — only if expected_source is specified
    if q.expected_source and not q.no_answer:
        score.retrieval_at_1 = 1.0 if q.expected_source in sources[:1] else 0.0
        score.retrieval_at_3 = 1.0 if q.expected_source in sources[:3] else 0.0
        score.retrieval_at_5 = 1.0 if q.expected_source in sources[:5] else 0.0

        # MRR
        for rank, source in enumerate(sources, 1):
            if q.expected_source in source:
                score.mrr = 1.0 / rank
                break
        if score.mrr is None:
            score.mrr = 0.0

    # Chunk content match
    if q.expected_chunk_contains:
        score.chunk_match = 1.0 if all(
            s.lower() in top_chunk.lower()
            for s in q.expected_chunk_contains
        ) else 0.0

    # Negative precision
    if q.no_answer:
        # Pass if no results OR all results below similarity threshold
        score.negative_correct = len(result.results) == 0 or (
            result.results[0].get("score", 1.0) < 0.5
        )

    return score


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
        1.0 if len(set(sources)) == 1 else 0.0
        for sources in groups.values()
    ])

    # Source precision (source_specific category only)
    source_specific = [s for s in scores if s.category == "source_specific"]

    # Negative precision
    negative = [s for s in scores if s.negative_correct is not None]

    # Graph lift — computed externally by comparing two run results
    graph_questions = [s for s in scores if s.graph_lift is not None]

    r3 = mean([s.retrieval_at_3 for s in scores])
    mrr = mean([s.mrr for s in scores])
    cm = mean([s.chunk_match for s in scores])
    neg = mean([1.0 if s.negative_correct else 0.0 for s in negative])
    pc = paraphrase_consistency
    sp = mean([s.retrieval_at_1 for s in source_specific])

    composite = None
    if all(v is not None for v in [r3, mrr, cm, neg, pc, sp]):
        composite = (
            0.30 * r3 +
            0.20 * mrr +
            0.20 * cm +
            0.15 * neg +
            0.10 * pc +
            0.05 * sp
        )

    return {
        "retrieval_at_1":          mean([s.retrieval_at_1 for s in scores]),
        "retrieval_at_3":          r3,
        "retrieval_at_5":          mean([s.retrieval_at_5 for s in scores]),
        "mrr":                     mrr,
        "chunk_match":             cm,
        "negative_precision":      neg,
        "hallucination_rate":      1 - neg if neg is not None else None,
        "paraphrase_consistency":  pc,
        "source_precision":        sp,
        "graph_lift":              mean([s.graph_lift for s in graph_questions]),
        "composite_score":         composite,
        "questions_scored":        len(scores),
    }
```

---

### `reporter.py` — Results Output

```python
import json
from datetime import datetime
from pathlib import Path


def print_report(aggregate: dict, scores: list) -> None:
    print("\n" + "=" * 60)
    print("dev-rag Evaluation Report")
    print(f"Run: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"Questions scored: {aggregate['questions_scored']}")
    print("=" * 60)

    metrics = [
        ("Retrieval@1",           "retrieval_at_1",         0.60),
        ("Retrieval@3",           "retrieval_at_3",         0.80),
        ("Retrieval@5",           "retrieval_at_5",         0.85),
        ("MRR",                   "mrr",                    0.60),
        ("Chunk Match",           "chunk_match",            0.70),
        ("Negative Precision",    "negative_precision",     0.90),
        ("Hallucination Rate",    "hallucination_rate",     None),   # lower is better
        ("Paraphrase Consistency","paraphrase_consistency", 0.80),
        ("Source Precision",      "source_precision",       0.75),
        ("Graph Lift",            "graph_lift",             0.0),
        ("Composite Score",       "composite_score",        0.70),
    ]

    for label, key, target in metrics:
        val = aggregate.get(key)
        if val is None:
            print(f"  {label:<28} n/a")
            continue
        pct = f"{val:.1%}"
        if target is not None and key != "hallucination_rate":
            status = "✓" if val >= target else "✗"
        elif key == "hallucination_rate":
            status = "✓" if val <= 0.10 else "✗"
        else:
            status = " "
        target_str = f"(target: {target:.0%})" if target is not None else ""
        print(f"  {label:<28} {pct:>7}  {status}  {target_str}")

    print("=" * 60)

    # Flag failures by category
    failures = [s for s in scores if _is_failure(s, aggregate)]
    if failures:
        print(f"\nFailed questions ({len(failures)}):")
        for s in failures:
            print(f"  [{s.question_id}] {s.failure_mode}")

    print()


def _is_failure(score, aggregate) -> bool:
    if score.retrieval_at_3 is not None and score.retrieval_at_3 == 0.0:
        return True
    if score.negative_correct is False:
        return True
    return False


def save_results(aggregate: dict, scores: list, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    path = output_dir / f"{timestamp}.json"
    path.write_text(json.dumps({
        "timestamp": timestamp,
        "aggregate": aggregate,
        "questions": [vars(s) for s in scores],
    }, indent=2))
    print(f"Results saved to {path}")
```

---

### `run_eval.py` — Entry Point

```python
#!/usr/bin/env python
"""
dev-rag evaluation harness entry point.

Usage:
    uv run python eval/run_eval.py
    uv run python eval/run_eval.py --domain devops
    uv run python eval/run_eval.py --category security negative
    uv run python eval/run_eval.py --compare results/2026-06-01.json
"""

import argparse
import asyncio
from pathlib import Path

from loader import load_questions
from runner import run_question
from scorer import score_question, compute_aggregate_metrics
from reporter import print_report, save_results

QUESTION_FILES = [
    Path("data/evaluation/devops_questions.yaml"),
    Path("data/evaluation/travel_questions.yaml"),
    Path("data/evaluation/cross_domain_questions.yaml"),
]

RESULTS_DIR = Path("eval/results")


async def main(args):
    questions = load_questions([p for p in QUESTION_FILES if p.exists()])

    # Filter by domain or category if requested
    if args.domain:
        questions = [q for q in questions if q.domain == args.domain]
    if args.category:
        questions = [q for q in questions if q.category in args.category]

    print(f"Running {len(questions)} questions against {args.base_url} ...")

    scores = []
    for q in questions:
        result = await run_question(q, n_results=5, include_graph=args.graph)
        score = score_question(q, result)
        scores.append(score)
        status = "." if not _failed(score) else "F"
        print(status, end="", flush=True)

    print()

    aggregate = compute_aggregate_metrics(scores)
    print_report(aggregate, scores)
    save_results(aggregate, scores, RESULTS_DIR)

    # Optional: compare against a previous run
    if args.compare:
        import json
        prev = json.loads(Path(args.compare).read_text())
        print("\nComparison vs previous run:")
        for key in ["retrieval_at_3", "mrr", "composite_score"]:
            prev_val = prev["aggregate"].get(key)
            curr_val = aggregate.get(key)
            if prev_val and curr_val:
                delta = curr_val - prev_val
                sign = "+" if delta >= 0 else ""
                print(f"  {key:<28} {sign}{delta:.1%}")


def _failed(score) -> bool:
    return (score.retrieval_at_3 == 0.0 and score.retrieval_at_3 is not None) \
        or score.negative_correct is False


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--domain", choices=["devops", "travel", "cross_domain"])
    parser.add_argument("--category", nargs="+")
    parser.add_argument("--graph", action="store_true", help="Include graph traversal")
    parser.add_argument("--compare", help="Path to previous results JSON for delta comparison")
    args = parser.parse_args()
    asyncio.run(main(args))
```

---

## Target Baselines

These are the minimum acceptable scores before making any pipeline change.
They are starting targets, not final goals.

| Metric | Minimum | Good | Excellent |
|--------|---------|------|-----------|
| Retrieval@1 | 0.50 | 0.70 | 0.85 |
| Retrieval@3 | 0.70 | 0.85 | 0.95 |
| MRR | 0.50 | 0.65 | 0.80 |
| Chunk Match | 0.60 | 0.75 | 0.90 |
| Negative Precision | 0.80 | 0.90 | 0.98 |
| Paraphrase Consistency | 0.70 | 0.80 | 0.95 |
| Source Precision | 0.65 | 0.75 | 0.90 |
| Composite Score | 0.60 | 0.72 | 0.85 |

---

## What the Question Counts Tell You

This maps to the long-term progression originally outlined in v1:

| Count | What gets exposed |
|-------|-------------------|
| 10 | Major retrieval failures — wrong corpus, wrong domain, empty results on obvious questions |
| 25 | Chunking problems — boundary failures, incomplete answers |
| 50 | Ranking problems — right content retrieved but ranked too low |
| 100 | Architectural limitations — where hybrid search would help, where the graph adds value |
| 200+ | Edge cases and long-tail vocabulary — the eval set becomes genuinely predictive |

The first 10 questions typically expose whether the system works at all.
The evaluation harness becomes genuinely valuable around 50 questions —
that is when metric deltas between pipeline changes become meaningful.

---

## Running the Harness

```bash
# Full evaluation
uv run python eval/run_eval.py

# DevOps domain only
uv run python eval/run_eval.py --domain devops

# Security and negative categories only
uv run python eval/run_eval.py --category security negative

# Include graph traversal comparison
uv run python eval/run_eval.py --graph

# Compare against previous baseline
uv run python eval/run_eval.py --compare eval/results/2026-06-01_10-00.json
```

---

## Using the Harness for Architecture Decisions

This is the primary long-term value. Every major change to dev-rag should
follow this workflow:

```
1. Run eval — save baseline JSON
2. Make the architectural change (e.g. add reranker, swap vector store)
3. Run eval again with --compare pointing at the baseline
4. Read the delta report
5. Commit the change if composite score improves, revert if it regresses
```

This is how "adding a reranker improved Retrieval@3 by 12 points" becomes a
fact rather than a guess. Without the harness, pipeline decisions are intuition.
With it, they are engineering.

---

*This document combines v1 (question strategy) with new additions in v2:
negative questions, chunk boundary questions, adversarial paraphrase groups,
GraphRAG-specific questions, staleness validation questions, full metric
definitions, and the complete harness implementation spec.*
