"""
Stage 1: Extract — convert a source document to raw text, preserving
page boundaries.

Page boundaries are kept so Stage 2 can use page position as a noise
signal (page numbers, headers, and footers appear at predictable
positions on every page).

Spec: planning/ingest-pipeline-spec.md (Stage 1).
"""
import json
from dataclasses import dataclass
from pathlib import Path

import fitz  # PyMuPDF


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
    Extract text from a PDF using PyMuPDF.

    Preserves page boundaries so Stage 2 can use page number
    as a signal for noise (e.g. page numbers appear at predictable
    positions on every page).
    """
    doc = fitz.open(str(path))
    pages = []

    for page_num, page in enumerate(doc, start=1):
        text = page.get_text("text")
        has_images = len(page.get_images()) > 0
        pages.append(ExtractedPage(
            page_number=page_num,
            text=text,
            has_images=has_images,
        ))

    metadata = doc.metadata
    title = metadata.get("title") or path.stem.replace("-", " ").replace("_", " ")

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
