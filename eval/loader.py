"""Load and validate evaluation questions from YAML files.

Spec: planning/dev-rag-evaluation-strategy.md (§loader.py). Unknown YAML
keys fail loudly (EvalQuestion(**item) raises) — a typo in a question
file should stop the run, not silently drop a field.
"""
from dataclasses import dataclass, field
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent

# All question files; the spec's list predates the ai/python domains.
QUESTION_FILES = [
    REPO / "data/evaluation/devops_questions.yaml",
    REPO / "data/evaluation/travel_questions.yaml",
    REPO / "data/evaluation/python_questions.yaml",
    REPO / "data/evaluation/ai_questions.yaml",
    REPO / "data/evaluation/cross_domain_questions.yaml",
]


@dataclass
class EvalQuestion:
    id: str
    question: str
    domain: str
    category: str
    failure_mode: str
    no_answer: bool = False
    requires_graph: bool = False
    requires_multi_source: bool = False
    expected_source: str | None = None
    expected_chunk_contains: list[str] = field(default_factory=list)
    paraphrase_group: str | None = None
    notes: str = ""


def load_questions(paths: list[Path] | None = None) -> list[EvalQuestion]:
    questions = []
    for path in paths if paths is not None else QUESTION_FILES:
        if not path.exists():
            continue
        raw = yaml.safe_load(path.read_text())
        for item in raw or []:
            questions.append(EvalQuestion(**item))
    return questions
