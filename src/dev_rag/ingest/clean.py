"""
Stage 2: Clean — remove noise that hurts retrieval quality.

Basic non-LLM cleaning only (Phase 1a): noise-page classification
(blank, TOC, index, copyright, too-short) plus within-page fixes
(page numbers, running headers/footers, whitespace, hyphenation).

Removed pages are kept in the output with was_removed=True so the
cleaning decisions can be inspected before Stage 4 chunks the text.

Spec: planning/ingest-pipeline-spec.md (Stage 2).
"""
import json
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CleanedPage:
    page_number: int
    text: str
    was_removed: bool     # True if page was identified as noise
    removal_reason: str   # why it was removed, for inspection


def clean_document(pages: list[dict]) -> list[CleanedPage]:
    """
    Clean extracted pages, removing noise that hurts retrieval.

    Returns all pages including removed ones (with was_removed=True)
    so the cleaning decisions can be inspected before committing.
    """
    cleaned = []
    for page in pages:
        text = page["text"]
        page_num = page["page_number"]

        # Detect and skip noise pages
        reason = _classify_noise(text, page_num)
        if reason:
            cleaned.append(CleanedPage(
                page_number=page_num,
                text=text,
                was_removed=True,
                removal_reason=reason,
            ))
            continue

        # Clean within-page noise
        text = _remove_page_numbers(text)
        text = _remove_running_headers(text)
        text = _remove_excessive_whitespace(text)
        text = _fix_hyphenation(text)   # re-join words split across lines

        cleaned.append(CleanedPage(
            page_number=page_num,
            text=text,
            was_removed=False,
            removal_reason="",
        ))

    return cleaned


def _classify_noise(text: str, page_num: int) -> str:
    """Return noise reason string or empty string if page is content."""
    stripped = text.strip()

    # Blank page
    if not stripped:
        return "blank_page"

    # Very short page — likely a section divider or copyright page
    if len(stripped) < 100:
        return "too_short"

    # Table of contents — lots of dots and page numbers
    dot_density = stripped.count(".") / max(len(stripped), 1)
    if dot_density > 0.15 and re.search(r'\d{1,3}\s*$', stripped, re.MULTILINE):
        return "table_of_contents"

    # Index page — alphabetical entries with page numbers
    lines = stripped.split("\n")
    if len(lines) > 10:
        lines_with_trailing_numbers = sum(
            1 for l in lines if re.search(r'\s+\d+$', l.strip())
        )
        if lines_with_trailing_numbers / len(lines) > 0.5:
            return "index_page"

    # Copyright page — common phrases
    copyright_phrases = [
        "all rights reserved", "isbn", "printed in",
        "no part of this publication", "library of congress",
    ]
    lower = stripped.lower()
    if sum(1 for p in copyright_phrases if p in lower) >= 2:
        return "copyright_page"

    return ""


def _remove_page_numbers(text: str) -> str:
    """Remove standalone page numbers (digits on their own line)."""
    return re.sub(r'^\s*\d{1,4}\s*$', '', text, flags=re.MULTILINE)


def _remove_running_headers(text: str) -> str:
    """
    Remove running headers and footers.
    These typically appear as short lines at the very top or bottom
    of a page that repeat across multiple pages.

    Note: this is heuristic — inspect output to verify it's not
    removing legitimate content.
    """
    lines = text.split('\n')
    if len(lines) < 4:
        return text
    # Remove first line if very short (likely header)
    if len(lines[0].strip()) < 60 and lines[0].strip():
        lines = lines[1:]
    # Remove last line if very short (likely footer/page number)
    if len(lines[-1].strip()) < 60 and lines[-1].strip():
        lines = lines[:-1]
    return '\n'.join(lines)


def _remove_excessive_whitespace(text: str) -> str:
    """Collapse multiple blank lines to a single blank line."""
    return re.sub(r'\n{3,}', '\n\n', text)


def _fix_hyphenation(text: str) -> str:
    """Re-join words split across lines by end-of-line hyphens."""
    return re.sub(r'(\w)-\n(\w)', r'\1\2', text)


def load_raw(path: Path) -> dict:
    """Load a Stage 1 raw extraction JSON."""
    return json.loads(path.read_text())


def save_cleaned(raw: dict, pages: list[CleanedPage], output_dir: Path) -> Path:
    """
    Save cleaned document as JSON for Stage 4 (and inspection).
    Carries forward the Stage 1 document metadata.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    slug = Path(raw["source_path"]).stem.lower().replace(" ", "-")
    path = output_dir / f"{slug}_cleaned.json"
    path.write_text(json.dumps({
        "source_path": raw["source_path"],
        "source_type": raw["source_type"],
        "title": raw["title"],
        "total_pages": raw["total_pages"],
        "pages": [
            {
                "page_number": p.page_number,
                "text": p.text,
                "was_removed": p.was_removed,
                "removal_reason": p.removal_reason,
            }
            for p in pages
        ]
    }, indent=2))
    return path
