"""
Stage 4: Chunk — fixed-size sliding window over cleaned text.

Fixed-size chunking is INTENTIONAL for Phase 1a (OBS-007): eval question
devops-008 (chunk_boundary category) is the signal that decides whether
structure-aware semantic chunking (spec Stage 3+4, Phase 1b) is needed.
Its failures are expected and useful — tune size/overlap first, go
structure-aware only if failures persist.

The window runs over the whole document (kept pages concatenated), not
page-by-page, so multi-step procedures spanning a page break stay in one
chunk. Each chunk's page_number is the page where the chunk starts.

Spec: planning/ingest-pipeline-spec.md (Stage 4, adapted per
docs/plans/dev-rag-phase1a-plan.md — no section structure yet).
"""
import json
from dataclasses import dataclass
from pathlib import Path

from .util import content_hash

CHUNK_SIZE = 1500     # chars (~375 tokens)
CHUNK_OVERLAP = 200   # chars


@dataclass
class Chunk:
    chunk_id: str
    source_id: str        # stable slug, e.g. "dockerdeepdive"
    source: str           # filename, e.g. "dockerdeepdive.pdf"
    domain: str
    title: str
    page_number: int      # page where the chunk starts
    content: str
    content_hash: str


def chunk_document(
    cleaned: dict,
    domain: str,
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> list[Chunk]:
    """
    Window the cleaned document (Stage 2 output dict) into chunks.

    Splits at whitespace, never mid-word. Removed pages are excluded.
    """
    kept = [p for p in cleaned["pages"] if not p["was_removed"]]

    # Concatenate kept pages, recording each page's start offset so a
    # chunk offset can be mapped back to its starting page.
    parts: list[str] = []
    page_starts: list[tuple[int, int]] = []   # (offset, page_number)
    offset = 0
    for p in kept:
        text = p["text"].strip()
        if not text:
            continue
        page_starts.append((offset, p["page_number"]))
        parts.append(text)
        offset += len(text) + 2   # joined with "\n\n"
    full_text = "\n\n".join(parts)

    source_path = Path(cleaned["source_path"])
    source_id = source_path.stem.lower().replace(" ", "-")

    chunks = []
    start = 0
    counter = 0
    while start < len(full_text):
        end = min(start + chunk_size, len(full_text))
        # Snap end back to the last whitespace so words stay intact
        if end < len(full_text):
            ws = full_text.rfind(" ", start, end)
            nl = full_text.rfind("\n", start, end)
            snap = max(ws, nl)
            if snap > start:
                end = snap
        content = full_text[start:end].strip()
        if content:
            counter += 1
            chunks.append(Chunk(
                chunk_id=f"{source_id}_{counter:04d}",
                source_id=source_id,
                source=source_path.name,
                domain=domain,
                title=cleaned["title"],
                page_number=_page_at(page_starts, start),
                content=content,
                content_hash=content_hash(content),
            ))
        if end >= len(full_text):
            break
        start = max(end - overlap, start + 1)
        # Snap the overlap start forward to a word boundary so no chunk
        # begins mid-word
        while start < len(full_text) and not full_text[start - 1].isspace():
            start += 1

    return chunks


def _page_at(page_starts: list[tuple[int, int]], offset: int) -> int:
    """Page number of the page containing this character offset."""
    page = page_starts[0][1] if page_starts else 0
    for page_offset, page_number in page_starts:
        if page_offset > offset:
            break
        page = page_number
    return page


def load_cleaned(path: Path) -> dict:
    """Load a Stage 2 cleaned document JSON."""
    return json.loads(path.read_text())


def save_chunks(chunks: list[Chunk], output_dir: Path) -> Path:
    """Save chunks as JSON for Stage 6 (and inspection)."""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{chunks[0].source_id}_chunks.json"
    path.write_text(json.dumps([
        {
            "chunk_id": c.chunk_id,
            "source_id": c.source_id,
            "source": c.source,
            "domain": c.domain,
            "title": c.title,
            "page_number": c.page_number,
            "content": c.content,
            "content_hash": c.content_hash,
        }
        for c in chunks
    ], indent=2))
    return path
