"""
Stage 1: Extract — convert a source document to markdown text,
preserving page boundaries.

Uses pymupdf4llm (PyMuPDF + layout analysis) rather than plain
page.get_text(): borderless tables come out as markdown tables instead
of shredded column fragments, and section headings come out as markdown
headings — which later stages can use for structure detection without
LLM calls.

Page boundaries are kept so Stage 2 can use page position as a noise
signal (page numbers, headers, and footers appear at predictable
positions on every page).

Spec: planning/ingest-pipeline-spec.md (Stage 1, extraction engine
upgraded per docs/reviews/FABLE-REVIEW discussion 2026-07-05).
"""
import json
from dataclasses import dataclass
from pathlib import Path

import fitz  # PyMuPDF
import pymupdf4llm


@dataclass
class ExtractedPage:
    page_number: int
    text: str
    has_images: bool


@dataclass
class ExtractedDocument:
    source_path: str
    source_type: str          # pdf | url | epub
    title: str
    pages: list[ExtractedPage]
    total_pages: int


def extract_pdf(path: Path) -> ExtractedDocument:
    """
    Extract markdown text from a PDF using pymupdf4llm.

    Preserves page boundaries so Stage 2 can use page number
    as a signal for noise (e.g. page numbers appear at predictable
    positions on every page).
    """
    doc = fitz.open(str(path))
    title = doc.metadata.get("title") or path.stem.replace("-", " ").replace("_", " ")
    doc.close()

    page_data = pymupdf4llm.to_markdown(str(path), page_chunks=True)
    pages = [
        ExtractedPage(
            page_number=num,
            text=d["text"],
            has_images=bool(d.get("images")),
        )
        for num, d in enumerate(page_data, start=1)
    ]

    return ExtractedDocument(
        source_path=str(path),
        source_type="pdf",
        title=title,
        pages=pages,
        total_pages=len(pages),
    )


async def extract_url(url: str) -> ExtractedDocument:
    """URL extraction is deferred to Phase 1b (needs httpx + html2text)."""
    raise NotImplementedError("URL extraction is deferred to Phase 1b")


def save_extracted(doc: ExtractedDocument, output_dir: Path) -> Path:
    """Save extracted document as JSON for Stage 2 inspection."""
    output_dir.mkdir(parents=True, exist_ok=True)
    slug = Path(doc.source_path).stem.lower().replace(" ", "-")
    path = output_dir / f"{slug}.json"
    path.write_text(json.dumps({
        "source_path": doc.source_path,
        "source_type": doc.source_type,
        "title": doc.title,
        "total_pages": doc.total_pages,
        "pages": [
            {
                "page_number": p.page_number,
                "text": p.text,
                "has_images": p.has_images,
            }
            for p in doc.pages
        ]
    }, indent=2))
    return path
