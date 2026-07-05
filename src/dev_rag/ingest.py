"""
dev-rag ingest — SUPERSEDED STUB.

OBS-007 decision (2026-07-04): planning/ingest-pipeline-spec.md governs ingestion.
This single-module sliding-window stub is replaced by the staged pipeline package
src/dev_rag/ingest/ (Phase 1a thin vertical slice: extract -> clean -> chunk -> embed
-> load -> verify; LLM structure (Stage 3) and enrichment (Stage 5) deferred to 1b).

The old chunk_text docstring argued fixed-size chunking was out of scope to improve.
That instinct is kept but RELOCATED: it is NOT a reason to skip the pipeline — it is the
quality signal for Stage 4. Fixed-size boundaries are the Phase-1a starting point; eval
question devops-008 (chunk_boundary) is the trigger to make them structure-aware.

This file is replaced by the ingest/ package and will be deleted as that package is
scaffolded (its content_hash helper moves into the package). Do not build on it.
"""
import argparse
import hashlib
from pathlib import Path


def chunk_text(text: str, chunk_size: int = 1000, overlap: int = 100) -> list[str]:
    """Sliding window chunker. Returns list of text chunks.

    OBS-007 (Opus review): This is a fixed-size window with no awareness
    of code fences, procedure steps, or section boundaries. Eval question
    devops-008 (chunk_boundary category) is specifically designed to
    detect when a multi-step procedure gets split mid-sequence.

    Decision: structure-aware chunking is OUT OF SCOPE for the initial
    implementation. The chunk_boundary eval questions will surface
    failures predictably around the 25-question mark. When they do,
    the fix is to increase chunk_size/overlap first, then consider
    structure-aware chunking (e.g. split on markdown headers, code
    fences, or PyMuPDF block boundaries) as a follow-on improvement.

    If devops-008 passes with fixed-size chunking, structure-aware
    chunking is not needed and this decision stands.
    """
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start += chunk_size - overlap
    return chunks


def content_hash(text: str) -> str:
    """SHA-256 hash of chunk text for change detection."""
    return hashlib.sha256(text.encode()).hexdigest()


def ingest_pdf(source_path: Path, domain: str) -> None:
    """TODO: implement PDF ingest using PyMuPDF."""
    raise NotImplementedError("Implement in Phase 1 — see IMPLEMENTATION-ORDER.md")


def ingest_url(url: str, domain: str) -> None:
    """TODO: implement URL ingest using httpx."""
    raise NotImplementedError("Implement in Phase 1 — see IMPLEMENTATION-ORDER.md")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="dev-rag ingest pipeline")
    parser.add_argument("--source", required=True, help="PDF path or URL to ingest")
    parser.add_argument("--domain", required=True, choices=["devops", "travel", "python"])
    args = parser.parse_args()

    source = args.source
    if source.startswith("http"):
        ingest_url(source, args.domain)
    else:
        ingest_pdf(Path(source), args.domain)
