"""Eval harness tests — loader/scorer units + full-harness e2e.

The eval/ modules are scripts (bare imports, run from repo root), so the
tests import them the same way: eval/ goes on sys.path. The e2e test
reuses the in-process-uvicorn + temp-store + fake-embedder pattern from
mcp/tests/test_mcp_e2e.py — the real harness runs against the real API.

FBL-002 guard: expected_source matching must be EXACT (a source that
merely contains the expected name must not match).
FBL-005 guard: negative precision is None (not a fake pass) under plain
hybrid RRF; computable via reranker logits or dense cosine.
"""
import argparse
import asyncio
import sys
import threading
import time
from pathlib import Path

import numpy as np
import pytest
import uvicorn

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "eval"))

import loader                                    # noqa: E402
import run_eval                                  # noqa: E402
from runner import RetrievalResult               # noqa: E402
from scorer import (                             # noqa: E402
    compute_aggregate_metrics,
    score_question,
)

MIGRATIONS = REPO / "migrations"
DIM = 8


def q(**overrides):
    defaults = dict(
        id="t-001", question="how do docker secrets work", domain="devops",
        category="factual", failure_mode="basic_semantic_mismatch",
    )
    defaults.update(overrides)
    return loader.EvalQuestion(**defaults)


def rr(results, search_mode="hybrid"):
    return RetrievalResult(
        question_id="t-001", question="q", results=results,
        search_mode=search_mode,
    )


# -- loader --------------------------------------------------------------------

def test_loader_parses_real_devops_file():
    questions = loader.load_questions(
        [REPO / "data/evaluation/devops_questions.yaml"])
    assert len(questions) >= 25
    by_id = {x.id: x for x in questions}
    # OBS-003: placeholders are gone — every expected_source is a real filename
    real = {"dockerdeepdive.pdf",
            "A_DEVELOPERS_ESSENTIAL_GUIDE_TO_DOCKER_COMPOSE.pdf"}
    populated = [x for x in questions if x.expected_source]
    assert len(populated) >= 25
    assert {x.expected_source for x in populated} == real
    # negatives stay unlabelled
    assert all(x.expected_source is None for x in questions if x.no_answer)
    # paraphrase group intact
    group = [x for x in questions
             if x.paraphrase_group == "docker-secrets-mechanism"]
    assert len(group) == 3
    assert by_id["devops-006"].expected_source == "dockerdeepdive.pdf"


def test_loader_skips_missing_files(tmp_path):
    assert loader.load_questions([tmp_path / "nope.yaml"]) == []


def test_loader_rejects_unknown_fields(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "- id: x-1\n  question: q\n  domain: devops\n  category: factual\n"
        "  failure_mode: f\n  expected_sourc: typo.pdf\n")
    with pytest.raises(TypeError):
        loader.load_questions([bad])


# -- scorer: FBL-002 exact matching --------------------------------------------

def test_retrieval_and_mrr_agree_on_exact_match():
    question = q(expected_source="dockerdeepdive.pdf")
    result = rr([{"source": "dockerdeepdive.pdf", "content": "x",
                  "relevance_score": 0.03}])
    s = score_question(question, result)
    assert s.retrieval_at_1 == 1.0 and s.mrr == 1.0


def test_mrr_rejects_substring_match():
    """FBL-002: 'deepdive.pdf' must NOT match source 'dockerdeepdive.pdf'."""
    question = q(expected_source="deepdive.pdf")
    result = rr([{"source": "dockerdeepdive.pdf", "content": "x",
                  "relevance_score": 0.03}])
    s = score_question(question, result)
    assert s.mrr == 0.0 and s.retrieval_at_1 == 0.0


def test_mrr_rank_position():
    question = q(expected_source="b.pdf")
    result = rr([{"source": "a.pdf", "content": "x", "relevance_score": 0.03},
                 {"source": "b.pdf", "content": "x", "relevance_score": 0.02}])
    s = score_question(question, result)
    assert s.mrr == pytest.approx(0.5)
    assert s.retrieval_at_1 == 0.0 and s.retrieval_at_3 == 1.0


# -- scorer: FBL-005 mode-aware negatives ---------------------------------------

def test_negative_none_under_plain_rrf():
    """FBL-005: RRF scores have no relevance scale — metric not computable."""
    question = q(no_answer=True)
    result = rr([{"source": "a.pdf", "content": "x", "relevance_score": 0.03,
                  "reranker_score": None}])
    s = score_question(question, result)
    assert s.negative_correct is None


def test_negative_uses_reranker_logit():
    question = q(no_answer=True)
    low = rr([{"source": "a.pdf", "content": "x", "relevance_score": -4.2,
               "reranker_score": -4.2}])
    high = rr([{"source": "a.pdf", "content": "x", "relevance_score": 3.0,
                "reranker_score": 3.0}])
    assert score_question(question, low).negative_correct is True
    assert score_question(question, high).negative_correct is False


def test_negative_uses_dense_cosine():
    question = q(no_answer=True)
    weak = rr([{"source": "a.pdf", "content": "x", "relevance_score": 0.2}],
              search_mode="dense")
    strong = rr([{"source": "a.pdf", "content": "x", "relevance_score": 0.9}],
                search_mode="dense")
    assert score_question(question, weak).negative_correct is True
    assert score_question(question, strong).negative_correct is False


def test_negative_empty_results_correct_in_any_mode():
    question = q(no_answer=True)
    assert score_question(question, rr([])).negative_correct is True


def test_aggregate_excludes_uncomputable_negatives():
    question = q(no_answer=True)
    scores = [score_question(question, rr(
        [{"source": "a.pdf", "content": "x", "relevance_score": 0.03,
          "reranker_score": None}]))]
    agg = compute_aggregate_metrics(scores)
    assert agg["negative_precision"] is None
    assert agg["hallucination_rate"] is None
    assert agg["questions_negative"] == 0


# -- e2e: real harness against the real API -------------------------------------

class QueryModel:
    def encode(self, text, **kwargs):
        v = np.zeros(DIM, dtype=np.float32)
        v[1] = 1.0
        return v


@pytest.fixture
def live_api(tmp_path, monkeypatch):
    import dev_rag.reranker as reranker
    import dev_rag.retrieve as retrieve
    from dev_rag.api import app
    from dev_rag.ingest.load import load_to_stores
    from dev_rag.ingest.util import content_hash
    from dev_rag.settings import settings

    contents = [
        "Docker images are built in layers from a Dockerfile.",
        "Docker secrets are encrypted in the swarm cluster store.",
        "Bridge networks are the default Docker network mode.",
    ]
    chunks = [
        {"chunk_id": f"tiny_{i:04d}", "source_id": "tiny", "source": "tiny.pdf",
         "domain": "devops", "title": "Tiny", "page_number": i + 1,
         "content": text, "content_hash": content_hash(text)}
        for i, text in enumerate(contents)
    ]
    embeds = [[1.0 if j == i else 0.0 for j in range(DIM)] for i in range(3)]
    load_to_stores(chunks, embeds, chroma_path=str(tmp_path / "chroma"),
                   sqlite_path=tmp_path / "dev_rag.db",
                   migrations_dir=MIGRATIONS)

    monkeypatch.setattr(settings, "chroma_db_path", str(tmp_path / "chroma"))
    monkeypatch.setattr(settings, "sqlite_db_path", tmp_path / "dev_rag.db")
    monkeypatch.setattr(retrieve, "_embedder", QueryModel())
    monkeypatch.setattr(settings, "reranker_enabled", False)
    monkeypatch.setattr(reranker, "_reranker", None)

    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("uvicorn did not start within 10s")
        time.sleep(0.02)
    port = server.servers[0].sockets[0].getsockname()[1]
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=5)


def test_harness_end_to_end(live_api, tmp_path, monkeypatch, capsys):
    qfile = tmp_path / "e2e_questions.yaml"
    qfile.write_text("""
- id: e2e-001
  question: "docker secrets"
  domain: devops
  category: factual
  failure_mode: basic_semantic_mismatch
  expected_source: "tiny.pdf"
  expected_chunk_contains:
    - "secrets"
- id: e2e-002
  question: "how to configure nomad"
  domain: devops
  category: negative
  failure_mode: hallucination_via_retrieval
  no_answer: true
""")
    monkeypatch.setattr(
        run_eval, "load_questions",
        lambda paths=None: loader.load_questions([qfile]))
    results_dir = tmp_path / "results"
    monkeypatch.setattr(run_eval, "RESULTS_DIR", results_dir)

    args = argparse.Namespace(
        base_url=live_api, domain="devops", category=None, graph=False,
        save=True, compare=None, label="e2e-test",
    )
    asyncio.run(run_eval.main(args))

    out = capsys.readouterr().out
    assert "Running 2 questions" in out
    assert "Results saved to" in out
    # FBL-005 surfaced honestly: hybrid RRF run can't judge negatives
    assert "RRF has no relevance scale" in out

    saved = list(results_dir.glob("*.json"))
    assert len(saved) == 1
    import json
    data = json.loads(saved[0].read_text())
    assert data["config"]["label"] == "e2e-test"
    assert data["config"]["search_mode"] == "hybrid"
    assert data["aggregate"]["retrieval_at_1"] == 1.0   # secrets chunk wins
    assert data["aggregate"]["negative_precision"] is None
    assert data["aggregate"]["questions_with_expected_source"] == 1
