"""
Thin-slice ingest pipeline orchestrator (Phase 1a).

Wires spec stages 1 -> 2 -> 4 -> 6 -> 7 -> 8, skipping 3 (LLM structure)
and 5 (LLM enrich), which are deferred to Phase 1b. Each stage reads the
previous stage's data/ artifact, so any stage can be re-run alone.

Usage:
    uv run python -m dev_rag.ingest.pipeline \
        --source data/books/dockerdeepdive.pdf --domain devops \
        --query "How does Docker isolate containers?"

Flags:
    --start-stage N   resume from spec stage N (after inspection)
    --stop-stage N    stop after spec stage N (for inspection)
    --dry-run         run text stages only; skip load/verify (no store writes)
    --query TEXT      verify-stage sample query — a question THIS book should
                      answer; required whenever stage 8 runs (a shared default
                      graded new books against the first book's content)
"""
import argparse
from dataclasses import dataclass, field
from pathlib import Path

from .chunk import chunk_document, load_cleaned, save_chunks
from .clean import clean_document, load_raw, save_cleaned
from .embed import embed_chunks, get_embedder, load_chunks, save_embeddings
from .extract import extract_pdf, save_extracted
from .load import load_embeddings, load_to_stores
from .verify import verify_ingest

STAGE_NUMBERS = (1, 2, 4, 6, 7, 8)   # spec numbering; 3 and 5 are Phase 1b
STORE_STAGES = (7, 8)                # skipped by --dry-run


@dataclass
class PipelineConfig:
    source: Path
    domain: str
    start_stage: int = 1
    stop_stage: int = 8
    dry_run: bool = False
    query: str = ""                  # required by stage 8; main() enforces
    data_dir: Path = Path("data")
    chroma_path: str = ""            # defaults from settings in run_pipeline
    sqlite_path: Path | None = None

    @property
    def slug(self) -> str:
        return self.source.stem.lower().replace(" ", "-")

    def artifact(self, kind: str, suffix: str) -> Path:
        return self.data_dir / kind / f"{self.slug}{suffix}"


def select_stages(cfg: PipelineConfig) -> list[int]:
    stages = [n for n in STAGE_NUMBERS if cfg.start_stage <= n <= cfg.stop_stage]
    if cfg.dry_run:
        stages = [n for n in stages if n not in STORE_STAGES]
    return stages


def run_pipeline(cfg: PipelineConfig, model_factory=get_embedder) -> None:
    """Run the selected stages in order, printing a summary per stage."""
    from dev_rag.settings import settings

    chroma_path = cfg.chroma_path or settings.chroma_db_path
    sqlite_path = cfg.sqlite_path or settings.sqlite_db_path

    model = None

    def get_model():
        nonlocal model
        if model is None:
            model = model_factory()
        return model

    for stage in select_stages(cfg):
        if stage == 1:
            doc = extract_pdf(cfg.source)
            path = save_extracted(doc, cfg.data_dir / "raw")
            print(f"[1 extract] {doc.total_pages} pages -> {path}")

        elif stage == 2:
            raw = load_raw(cfg.artifact("raw", ".json"))
            pages = clean_document(raw["pages"])
            removed = sum(1 for p in pages if p.was_removed)
            path = save_cleaned(raw, pages, cfg.data_dir / "cleaned")
            print(f"[2 clean] kept {len(pages) - removed}, removed {removed} -> {path}")

        elif stage == 4:
            cleaned = load_cleaned(cfg.artifact("cleaned", "_cleaned.json"))
            chunks = chunk_document(cleaned, domain=cfg.domain)
            path = save_chunks(chunks, cfg.data_dir / "chunks")
            sizes = [len(c.content) for c in chunks]
            print(f"[4 chunk] {len(chunks)} chunks, avg {sum(sizes) // len(sizes)} chars -> {path}")

        elif stage == 6:
            chunks = load_chunks(cfg.artifact("chunks", "_chunks.json"))
            embeddings = embed_chunks(chunks, get_model())
            path = save_embeddings(chunks, embeddings, cfg.data_dir / "embeddings")
            print(f"[6 embed] {len(embeddings)} vectors, dim {len(embeddings[0])} -> {path}")

        elif stage == 7:
            chunks = load_chunks(cfg.artifact("chunks", "_chunks.json"))
            embeds = load_embeddings(cfg.artifact("embeddings", "_embeddings.json"))
            stats = load_to_stores(
                chunks, [e["embedding"] for e in embeds],
                chroma_path=chroma_path, sqlite_path=sqlite_path,
            )
            print(f"[7 load] inserted {stats.inserted}, skipped {stats.skipped}; "
                  f"parity {stats.chroma_count}/{stats.sqlite_count}/{stats.fts_count}")

        elif stage == 8:
            report = verify_ingest(
                domain=cfg.domain,
                expected_source=cfg.source.name,
                query=cfg.query,
                chroma_path=chroma_path,
                sqlite_path=sqlite_path,
                model=get_model(),
            )
            top = report.top_results[0]
            print(f"[8 verify] parity OK ({report.chroma_count}); "
                  f"top hit {top['chunk_id']} p{top['page_number']} "
                  f"dist={top['distance']:.3f}")

    if cfg.dry_run:
        print("[dry-run] stages 7 (load) and 8 (verify) skipped — no store writes")


def main() -> None:
    parser = argparse.ArgumentParser(description="dev-rag thin-slice ingest pipeline")
    parser.add_argument("--source", type=Path, required=True, help="PDF path")
    parser.add_argument("--domain", required=True, help="corpus domain, e.g. devops")
    parser.add_argument("--start-stage", type=int, default=1, choices=STAGE_NUMBERS)
    parser.add_argument("--stop-stage", type=int, default=8, choices=STAGE_NUMBERS)
    parser.add_argument("--dry-run", action="store_true",
                        help="skip load/verify — no ChromaDB/SQLite writes")
    parser.add_argument("--query", default=None,
                        help="verify-stage sample query — a question THIS book "
                             "should answer (required when stage 8 runs)")
    args = parser.parse_args()

    cfg = PipelineConfig(
        source=args.source,
        domain=args.domain,
        start_stage=args.start_stage,
        stop_stage=args.stop_stage,
        dry_run=args.dry_run,
        query=args.query or "",
    )
    if 8 in select_stages(cfg) and not args.query:
        parser.error("--query is required when the verify stage (8) runs: "
                     "pass a question this book should answer")

    run_pipeline(cfg)


if __name__ == "__main__":
    main()
