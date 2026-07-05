"""Orchestrator tests — stage selection logic + end-to-end on a tiny PDF
with a fake embedding model (never real BGE-M3)."""
import sqlite3
from pathlib import Path

import fitz
import numpy as np

from dev_rag.ingest.pipeline import PipelineConfig, run_pipeline, select_stages

MIGRATIONS = Path(__file__).resolve().parents[2] / "migrations"


class FakeModel:
    """1024-dim mock (embed_chunks asserts dim 1024)."""

    def encode(self, texts, **kwargs):
        n = 1 if isinstance(texts, str) else len(texts)
        rng = np.random.default_rng(seed=1)
        out = rng.normal(size=(n, 1024)).astype(np.float32)
        out /= np.linalg.norm(out, axis=1, keepdims=True)
        return out[0] if isinstance(texts, str) else out


def cfg(**overrides):
    defaults = dict(source=Path("data/books/tiny.pdf"), domain="devops")
    defaults.update(overrides)
    return PipelineConfig(**defaults)


def test_select_stages_full_run():
    assert select_stages(cfg()) == [1, 2, 4, 6, 7, 8]


def test_select_stages_start_and_stop():
    assert select_stages(cfg(start_stage=4, stop_stage=7)) == [4, 6, 7]
    assert select_stages(cfg(stop_stage=2)) == [1, 2]
    assert select_stages(cfg(start_stage=8)) == [8]


def test_select_stages_dry_run_skips_store_stages():
    assert select_stages(cfg(dry_run=True)) == [1, 2, 4, 6]


def test_pipeline_end_to_end_on_tiny_pdf(tmp_path, monkeypatch, capsys):
    # Tiny 2-page PDF with enough prose to survive the too-short filter
    pdf = tmp_path / "tiny-book.pdf"
    doc = fitz.open()
    for text in (
        "Docker restart policies allow the engine to automatically restart "
        "failed containers, providing simple self-healing for services "
        "running on a single host without an orchestrator.",
        "Docker secrets are encrypted in the cluster store and mounted into "
        "containers as in-memory files, which is the production-safe way to "
        "provide credentials to services in swarm mode deployments.",
    ):
        page = doc.new_page()
        # narrow column so text spans enough lines to look like prose
        rect = fitz.Rect(72, 72, 300, 700)
        page.insert_textbox(rect, text)
    doc.save(str(pdf))
    doc.close()

    # migrations dir must be visible from the cwd the pipeline runs in
    monkeypatch.chdir(MIGRATIONS.parent)

    config = cfg(
        source=pdf,
        data_dir=tmp_path / "data",
        chroma_path=str(tmp_path / "chroma"),
        sqlite_path=tmp_path / "dev_rag.db",
        query="how do I store secrets safely",
    )
    run_pipeline(config, model_factory=FakeModel)

    out = capsys.readouterr().out
    for marker in ("[1 extract]", "[2 clean]", "[4 chunk]", "[6 embed]",
                   "[7 load]", "[8 verify] parity OK"):
        assert marker in out, f"missing {marker} in output"

    # artifacts exist for every text stage
    assert (tmp_path / "data/raw/tiny-book.json").exists()
    assert (tmp_path / "data/cleaned/tiny-book_cleaned.json").exists()
    assert (tmp_path / "data/chunks/tiny-book_chunks.json").exists()
    assert (tmp_path / "data/embeddings/tiny-book_embeddings.json").exists()

    # stores populated with parity
    conn = sqlite3.connect(tmp_path / "dev_rag.db")
    n_chunks = conn.execute("SELECT count(*) FROM chunks").fetchone()[0]
    n_fts = conn.execute("SELECT count(*) FROM chunks_fts").fetchone()[0]
    conn.close()
    assert n_chunks == n_fts > 0


def test_pipeline_dry_run_writes_no_stores(tmp_path, monkeypatch):
    pdf = tmp_path / "tiny.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_textbox(
        fitz.Rect(72, 72, 300, 700),
        "Enough prose about container networking to pass the noise filter "
        "and produce at least one chunk for the dry-run pipeline test case.",
    )
    doc.save(str(pdf))
    doc.close()

    monkeypatch.chdir(MIGRATIONS.parent)
    config = cfg(
        source=pdf,
        dry_run=True,
        data_dir=tmp_path / "data",
        chroma_path=str(tmp_path / "chroma"),
        sqlite_path=tmp_path / "dev_rag.db",
    )
    run_pipeline(config, model_factory=FakeModel)

    assert (tmp_path / "data/embeddings/tiny_embeddings.json").exists()
    assert not (tmp_path / "dev_rag.db").exists()
    assert not (tmp_path / "chroma").exists()
