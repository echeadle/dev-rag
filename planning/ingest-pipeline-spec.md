# dev-rag Book Ingest Pipeline — Implementation Spec

**Version:** 1.0  
**Date:** June 2026  
**Status:** Ready to implement — replaces ingest.py stub  
**Supersedes:** The basic sliding-window chunker in `src/dev_rag/ingest.py`

> **OBS-007 (2026-07-04) — ADOPTED.** Decision ratified: this spec governs ingestion.
> Phase 1a implements a THIN VERTICAL SLICE (extract -> clean -> chunk -> embed -> load
> -> verify); Stage 3 (structure) and Stage 5 (enrich) are deferred to Phase 1b.

---

## Why This Matters

Retrieval quality is determined more by document preparation than by
the vector database or embedding model. A well-prepared corpus with
clean text, semantic chunks, and enriched metadata will outperform
a poorly-prepared corpus even with a superior retrieval algorithm.

The current `ingest.py` stub uses a fixed 1000-character sliding window
with no structure awareness and no noise removal. This means:

- Table of contents entries get embedded as if they were content
- Page numbers, headers, and footers pollute chunks
- A Docker secrets explanation split mid-sentence across two chunks
  retrieves poorly for both
- Code blocks are embedded as prose, losing their exact-match value
- The embedder gets noisy, low-signal text instead of clean explanations

This pipeline fixes all of those problems.

---

## Pipeline Overview

```
Source (PDF / EPUB / URL)
        │
        ▼
Stage 1: Extract      → data/raw/book.txt
        │
        ▼
Stage 2: Clean        → data/cleaned/book_cleaned.txt
        │
        ▼
Stage 3: Structure    → data/structured/book_structure.json
        │
        ▼
Stage 4: Chunk        → data/chunks/chunks.json
        │
        ▼
Stage 5: Enrich       → data/enriched/book_enriched.json
   ├── Summaries
   ├── Keywords
   ├── Synthetic questions
   └── Code extraction
        │
        ▼
Stage 6: Embed        → BGE-M3 vectors
        │
        ▼
Stage 7: Load         → ChromaDB (vectors) + SQLite (metadata)
        │
        ▼
Stage 8: Verify       → Parity check + smoke query
```

**Key principle: inspect output at every stage before moving to the next.**
Do not run the full pipeline end-to-end until each stage is verified
independently. This makes debugging significantly easier and catches
quality problems before they reach the embedder.

---

## File Layout

```
dev-rag/
├── src/dev_rag/
│   └── ingest/
│       ├── __init__.py
│       ├── extract.py        # Stage 1 — PDF/EPUB/URL → raw text
│       ├── clean.py          # Stage 2 — noise removal
│       ├── structure.py      # Stage 3 — LLM chapter/section detection
│       ├── chunk.py          # Stage 4 — semantic chunking
│       ├── enrich.py         # Stage 5 — summaries, keywords, questions, code
│       ├── embed.py          # Stage 6 — BGE-M3 embedding
│       ├── load.py           # Stage 7 — ChromaDB + SQLite write
│       └── pipeline.py       # Orchestrator — runs all stages in sequence
├── data/
│   ├── books/                # Source PDFs (gitignored)
│   ├── raw/                  # Stage 1 output
│   ├── cleaned/              # Stage 2 output
│   ├── structured/           # Stage 3 output
│   ├── chunks/               # Stage 4 output
│   └── enriched/             # Stage 5 output
└── tests/
    └── test_ingest/
        ├── test_extract.py
        ├── test_clean.py
        ├── test_structure.py
        ├── test_chunk.py
        ├── test_enrich.py
        └── test_pipeline.py
```

---

## Stage 1: Extract

**Goal:** Convert source document to raw text, preserving page boundaries.

**Input:** PDF file path or URL  
**Output:** `data/raw/{book_slug}.txt`

```python
# src/dev_rag/ingest/extract.py

import fitz   # PyMuPDF
import httpx
from pathlib import Path
from dataclasses import dataclass


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

    # Attempt to extract title from PDF metadata
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
    """
    Extract text from a URL using httpx.
    Uses html2text for clean markdown-like output.
    """
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(url)
        r.raise_for_status()

    # TODO: html2text conversion for URL sources
    # pip install html2text
    import html2text
    h = html2text.HTML2Text()
    h.ignore_links = False
    text = h.handle(r.text)

    return ExtractedDocument(
        source_path=url,
        source_type="url",
        title=url,
        pages=[ExtractedPage(page_number=1, text=text, has_images=False)],
        total_pages=1,
    )


def save_extracted(doc: ExtractedDocument, output_dir: Path) -> Path:
    """Save extracted document as JSON for Stage 2 inspection."""
    import json
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
```

**Inspect before proceeding:**
```bash
# Check raw extraction quality
cat data/raw/docker-deep-dive.json | python -m json.tool | head -100
# Look for: garbled text, missing sections, encoding issues
```

---

## Stage 2: Clean

**Goal:** Remove noise that hurts retrieval quality.

**Input:** `data/raw/{book_slug}.json`  
**Output:** `data/cleaned/{book_slug}_cleaned.json`

### What to Remove

| Noise Type | Why It Hurts Retrieval |
|------------|----------------------|
| Page numbers | Embed as if content — waste vector space |
| Running headers/footers | Repeated text inflates term frequency |
| Table of contents | TOC entries retrieve instead of actual content |
| Index pages | Index terms match queries but have no useful content |
| Copyright pages | Legal boilerplate matches nothing useful |
| Blank pages | Empty chunks waste collection space |
| Repeated chapter titles | Duplicate content confuses ranking |

```python
# src/dev_rag/ingest/clean.py

import re
from dataclasses import dataclass


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
```

**Inspect before proceeding:**
```bash
# Check what was removed and why
python -c "
import json
data = json.load(open('data/cleaned/docker-deep-dive_cleaned.json'))
removed = [p for p in data['pages'] if p['was_removed']]
for p in removed[:10]:
    print(f\"Page {p['page_number']}: {p['removal_reason']}\")
    print(p['text'][:100])
    print('---')
"
# Verify: are the right pages being removed?
# If legitimate content is being removed, adjust _classify_noise thresholds
```

---

## Stage 3: Detect Structure

**Goal:** Identify chapters and sections before chunking, so chunks
follow the book's logical structure rather than arbitrary character counts.

**Input:** `data/cleaned/{book_slug}_cleaned.json`  
**Output:** `data/structured/{book_slug}_structure.json`

```python
# src/dev_rag/ingest/structure.py

import json
import anthropic
from dataclasses import dataclass


@dataclass
class Section:
    chapter_number: int
    chapter_title: str
    section_title: str
    start_page: int
    end_page: int
    content: str


@dataclass
class BookStructure:
    title: str
    chapters: list[dict]    # chapter → sections mapping
    sections: list[Section]


def detect_structure(
    cleaned_pages: list[dict],
    book_title: str,
    domain: str,
) -> BookStructure:
    """
    Use Claude to detect the chapter and section structure of the book.

    Runs on a sample of the text (first 20% to find chapter headings)
    rather than the full document to keep token usage manageable.

    Then uses regex pattern matching confirmed by the LLM output to
    identify section boundaries throughout the full text.
    """
    client = anthropic.Anthropic()

    # Sample the first portion of the book to identify heading patterns
    sample_text = "\n".join(
        p["text"] for p in cleaned_pages[:len(cleaned_pages)//5]
        if not p.get("was_removed")
    )[:8000]   # cap at 8K tokens

    prompt = f"""You are analyzing a technical book to identify its structure.

Book title: {book_title}
Domain: {domain}

Here is a sample from the beginning of the book:

{sample_text}

Identify:
1. The heading patterns used for chapters (e.g. "Chapter 1:", "CHAPTER ONE", "1.")
2. The heading patterns used for sections (e.g. "1.1", "## Section", bold short lines)
3. The first 5 chapter titles you can identify

Return ONLY valid JSON in this exact format:
{{
  "chapter_pattern": "description of how chapters are marked",
  "section_pattern": "description of how sections are marked",
  "chapters_found": [
    {{"number": 1, "title": "Chapter Title"}},
    {{"number": 2, "title": "Chapter Title"}}
  ]
}}"""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}]
    )

    structure_info = json.loads(message.content[0].text)

    # Use detected patterns to split full text into sections
    sections = _split_into_sections(cleaned_pages, structure_info)

    return BookStructure(
        title=book_title,
        chapters=structure_info.get("chapters_found", []),
        sections=sections,
    )


def _split_into_sections(
    pages: list[dict],
    structure_info: dict,
) -> list[Section]:
    """
    Split cleaned pages into sections using detected heading patterns.
    This is a simplified implementation — expand with regex matching
    based on the patterns returned by the LLM.
    """
    # TODO: implement regex-based section splitting using structure_info patterns
    # For now, treat each page as a section (upgrade in Phase 4b)
    sections = []
    for i, page in enumerate(pages):
        if page.get("was_removed"):
            continue
        sections.append(Section(
            chapter_number=0,
            chapter_title="Unknown",
            section_title=f"Page {page['page_number']}",
            start_page=page["page_number"],
            end_page=page["page_number"],
            content=page["text"],
        ))
    return sections
```

**Inspect before proceeding:**
```bash
# Review detected structure
cat data/structured/docker-deep-dive_structure.json | python -m json.tool | head -50
# Verify: are chapter and section boundaries correct?
# Check a few sections to confirm content is coherent
```

---

## Stage 4: Semantic Chunking

**Goal:** Create chunks that follow section boundaries rather than
arbitrary character counts. Only split sections that are too large.

**Input:** `data/structured/{book_slug}_structure.json`  
**Output:** `data/chunks/{book_slug}_chunks.json`

### Chunking Rules

| Situation | Action |
|-----------|--------|
| Section ≤ 1500 tokens | One chunk = one section |
| Section > 1500 tokens | Split at paragraph boundaries |
| Code block | Extract separately (Stage 5) |
| Table | Keep intact as one chunk |

```python
# src/dev_rag/ingest/chunk.py

import hashlib
import re
from dataclasses import dataclass, field


MAX_CHUNK_TOKENS = 1500    # approximate — 1 token ≈ 4 chars
MAX_CHUNK_CHARS  = 6000    # 1500 * 4


@dataclass
class Chunk:
    chunk_id: str
    source_path: str
    domain: str
    book_title: str
    chapter_number: int
    chapter_title: str
    section_title: str
    start_page: int
    end_page: int
    content: str
    content_hash: str
    chunk_type: str = "text"    # text | code | table
    word_count: int = 0


def create_chunks(
    sections: list,     # list of Section objects
    source_path: str,
    domain: str,
    book_title: str,
) -> list[Chunk]:
    """
    Convert detected sections into chunks.

    Sections within the token limit become single chunks.
    Oversized sections are split at paragraph boundaries to
    preserve semantic coherence.
    """
    chunks = []
    chunk_counter = 0

    for section in sections:
        content = section.content.strip()
        if not content:
            continue

        if len(content) <= MAX_CHUNK_CHARS:
            # Section fits in one chunk
            chunk_counter += 1
            chunks.append(_make_chunk(
                content=content,
                section=section,
                source_path=source_path,
                domain=domain,
                book_title=book_title,
                chunk_id=f"{book_title[:8]}_{chunk_counter:04d}",
            ))
        else:
            # Split oversized section at paragraph boundaries
            paragraphs = _split_at_paragraphs(content, MAX_CHUNK_CHARS)
            for para in paragraphs:
                chunk_counter += 1
                chunks.append(_make_chunk(
                    content=para,
                    section=section,
                    source_path=source_path,
                    domain=domain,
                    book_title=book_title,
                    chunk_id=f"{book_title[:8]}_{chunk_counter:04d}",
                ))

    return chunks


def _make_chunk(
    content: str,
    section,
    source_path: str,
    domain: str,
    book_title: str,
    chunk_id: str,
) -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        source_path=source_path,
        domain=domain,
        book_title=book_title,
        chapter_number=section.chapter_number,
        chapter_title=section.chapter_title,
        section_title=section.section_title,
        start_page=section.start_page,
        end_page=section.end_page,
        content=content,
        content_hash=hashlib.sha256(content.encode()).hexdigest(),
        word_count=len(content.split()),
    )


def _split_at_paragraphs(text: str, max_chars: int) -> list[str]:
    """
    Split text at paragraph boundaries to stay under max_chars.
    Never splits mid-sentence.
    """
    paragraphs = re.split(r'\n\n+', text)
    chunks = []
    current = []
    current_len = 0

    for para in paragraphs:
        if current_len + len(para) > max_chars and current:
            chunks.append("\n\n".join(current))
            current = [para]
            current_len = len(para)
        else:
            current.append(para)
            current_len += len(para)

    if current:
        chunks.append("\n\n".join(current))

    return chunks
```

**Inspect before proceeding:**
```bash
# Check chunk sizes and content quality
python -c "
import json
chunks = json.load(open('data/chunks/docker-deep-dive_chunks.json'))
print(f'Total chunks: {len(chunks)}')
sizes = [c[\"word_count\"] for c in chunks]
print(f'Avg words: {sum(sizes)//len(sizes)}')
print(f'Max words: {max(sizes)}')
print(f'Min words: {min(sizes)}')
# Print a sample chunk to verify quality
print(json.dumps(chunks[10], indent=2))
"
# Verify: do chunks feel complete and coherent?
# Are section titles meaningful?
# Are any chunks suspiciously short or long?
```

---

## Stage 5: Enrich

**Goal:** Add summaries, keywords, synthetic questions, and extracted
code blocks to each chunk. These enrich the metadata and significantly
improve retrieval quality.

**Input:** `data/chunks/{book_slug}_chunks.json`  
**Output:** `data/enriched/{book_slug}_enriched.json`

### Why Each Enrichment Matters for dev-rag

| Enrichment | Retrieval benefit |
|------------|------------------|
| Summary | Cleaner embedding signal — distilled meaning vs raw prose |
| Keywords | Improves BM25 sparse matching in hybrid search |
| Synthetic questions | Match real user queries better than source text |
| Code extraction | Enables exact code retrieval as a separate search type |

```python
# src/dev_rag/ingest/enrich.py

import json
import asyncio
import anthropic
from dataclasses import dataclass, field


@dataclass
class EnrichedChunk:
    # All original chunk fields preserved
    chunk_id: str
    source_path: str
    domain: str
    book_title: str
    chapter_title: str
    section_title: str
    start_page: int
    content: str
    content_hash: str
    chunk_type: str
    word_count: int

    # New enrichment fields
    summary: str = ""
    keywords: list[str] = field(default_factory=list)
    synthetic_questions: list[str] = field(default_factory=list)
    code_blocks: list[dict] = field(default_factory=list)


ENRICH_PROMPT = """You are enriching a chunk from a technical {domain} book
for use in a RAG retrieval system.

Book: {book_title}
Chapter: {chapter_title}
Section: {section_title}

Content:
{content}

Return ONLY valid JSON with no preamble or markdown:
{{
  "summary": "Two or three sentences summarising the key points of this section.",
  "keywords": ["keyword1", "keyword2", "keyword3", "keyword4", "keyword5"],
  "synthetic_questions": [
    "Question that this section directly answers?",
    "Another question this section answers?",
    "A third question this section answers?"
  ],
  "code_blocks": [
    {{
      "language": "python",
      "description": "what this code does",
      "content": "the code itself"
    }}
  ]
}}

Guidelines:
- Summary: distil the key production-grade insight, not a description of what the section covers
- Keywords: include exact technical terms, command names, flag names, and tool names
- Synthetic questions: phrase as a user would ask them, not as a quiz question
- Code blocks: extract ALL code examples, including shell commands and config files
- If no code blocks exist, return an empty array for code_blocks"""


async def enrich_chunk(
    chunk: dict,
    client: anthropic.AsyncAnthropic,
    domain: str,
) -> EnrichedChunk:
    """Enrich a single chunk with LLM-generated metadata."""
    prompt = ENRICH_PROMPT.format(
        domain=domain,
        book_title=chunk["book_title"],
        chapter_title=chunk["chapter_title"],
        section_title=chunk["section_title"],
        content=chunk["content"][:3000],   # cap to avoid token limits
    )

    try:
        message = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )
        enrichment = json.loads(message.content[0].text)
    except Exception as e:
        # Enrichment failure should not block ingest — use empty values
        enrichment = {
            "summary": "",
            "keywords": [],
            "synthetic_questions": [],
            "code_blocks": [],
        }

    return EnrichedChunk(
        chunk_id=chunk["chunk_id"],
        source_path=chunk["source_path"],
        domain=domain,
        book_title=chunk["book_title"],
        chapter_title=chunk["chapter_title"],
        section_title=chunk["section_title"],
        start_page=chunk["start_page"],
        content=chunk["content"],
        content_hash=chunk["content_hash"],
        chunk_type=chunk.get("chunk_type", "text"),
        word_count=chunk["word_count"],
        summary=enrichment.get("summary", ""),
        keywords=enrichment.get("keywords", []),
        synthetic_questions=enrichment.get("synthetic_questions", []),
        code_blocks=enrichment.get("code_blocks", []),
    )


async def enrich_all_chunks(
    chunks: list[dict],
    domain: str,
    concurrency: int = 5,    # parallel API calls — adjust for rate limits
) -> list[EnrichedChunk]:
    """
    Enrich all chunks concurrently with rate limiting.

    concurrency=5 means 5 Claude API calls in flight simultaneously.
    Reduce if you hit rate limit errors.
    """
    client = anthropic.AsyncAnthropic()
    semaphore = asyncio.Semaphore(concurrency)

    async def enrich_with_limit(chunk):
        async with semaphore:
            return await enrich_chunk(chunk, client, domain)

    tasks = [enrich_with_limit(c) for c in chunks]
    return await asyncio.gather(*tasks)
```

**Inspect before proceeding:**
```bash
# Review enrichment quality on a sample
python -c "
import json
enriched = json.load(open('data/enriched/docker-deep-dive_enriched.json'))
# Find a chunk about Docker secrets
for c in enriched:
    if 'secret' in c['content'].lower():
        print('CONTENT:', c['content'][:200])
        print('SUMMARY:', c['summary'])
        print('KEYWORDS:', c['keywords'])
        print('QUESTIONS:', c['synthetic_questions'])
        print('CODE BLOCKS:', len(c['code_blocks']))
        break
"
# Verify:
# - Is the summary a genuine distillation or just a restatement?
# - Do keywords include exact flag names and tool names?
# - Do synthetic questions sound like real user queries?
# - Are code blocks extracted correctly?
```

---

## Stage 6: Embed

**Goal:** Generate BGE-M3 embeddings for each enriched chunk.

**Input:** `data/enriched/{book_slug}_enriched.json`  
**Output:** Embeddings ready for ChromaDB insertion

### What to Embed

The key decision: embed the raw content, the summary, or both?

**Recommendation: embed a combined text** that gives BGE-M3 the richest signal:

```python
def build_embedding_text(chunk: EnrichedChunk) -> str:
    """
    Build the text to embed for a chunk.

    Combines section context, summary, content, and keywords
    into a single string that gives the embedding model the
    richest possible signal for retrieval.
    """
    parts = []

    # Section context as a header
    if chunk.chapter_title and chunk.section_title:
        parts.append(f"{chunk.chapter_title}: {chunk.section_title}")

    # Summary first — distilled meaning improves embedding quality
    if chunk.summary:
        parts.append(chunk.summary)

    # Raw content
    parts.append(chunk.content)

    # Keywords appended — improves BM25 sparse matching too
    if chunk.keywords:
        parts.append("Keywords: " + ", ".join(chunk.keywords))

    return "\n\n".join(parts)
```

### Also embed synthetic questions separately

```python
async def embed_synthetic_questions(
    chunk: EnrichedChunk,
    embedder,
) -> list[dict]:
    """
    Embed each synthetic question as a separate vector pointing
    back to the parent chunk.

    When a user asks "What is the production-safe way to store
    secrets?", the synthetic question embedding often retrieves
    the right chunk more reliably than the raw content embedding.
    """
    question_embeddings = []
    for q in chunk.synthetic_questions:
        embedding = embedder.encode(q).tolist()
        question_embeddings.append({
            "question": q,
            "parent_chunk_id": chunk.chunk_id,
            "embedding": embedding,
        })
    return question_embeddings
```

---

## Stage 7: Load

**Goal:** Write enriched chunks and embeddings to ChromaDB and SQLite.

**Input:** Enriched chunks + embeddings  
**Output:** ChromaDB collection + SQLite chunks table populated

### Schema additions for enriched metadata

```sql
-- Add to migrations/001_initial_schema.sql or new migration

ALTER TABLE chunks ADD COLUMN summary TEXT DEFAULT '';
ALTER TABLE chunks ADD COLUMN keywords JSON DEFAULT '[]';
ALTER TABLE chunks ADD COLUMN synthetic_questions JSON DEFAULT '[]';
ALTER TABLE chunks ADD COLUMN chapter_title TEXT DEFAULT '';
ALTER TABLE chunks ADD COLUMN section_title TEXT DEFAULT '';
ALTER TABLE chunks ADD COLUMN book_title TEXT DEFAULT '';
ALTER TABLE chunks ADD COLUMN chapter_number INTEGER DEFAULT 0;

-- Separate table for code blocks
CREATE TABLE IF NOT EXISTS code_blocks (
    code_id       TEXT PRIMARY KEY,
    chunk_id      TEXT NOT NULL REFERENCES chunks(chunk_id),
    domain        TEXT NOT NULL,
    language      TEXT NOT NULL,
    description   TEXT,
    content       TEXT NOT NULL,
    content_hash  TEXT NOT NULL
);

-- Separate table for synthetic question embeddings
CREATE TABLE IF NOT EXISTS synthetic_questions (
    question_id    TEXT PRIMARY KEY,
    chunk_id       TEXT NOT NULL REFERENCES chunks(chunk_id),
    question       TEXT NOT NULL,
    -- embedding stored in ChromaDB synthetic_questions collection
    embedding_ref  TEXT   -- ChromaDB document ID
);
```

### ChromaDB collections after enrichment

```
devops_content          # main content embeddings
devops_questions        # synthetic question embeddings (new)
python_content
python_questions
ai_content
ai_questions
```

The synthetic question collections enable a two-pass retrieval:
query both collections and merge results before reranking.

---

## Stage 8: Verify

**Goal:** Confirm the pipeline produced a working, queryable corpus.

```python
# Run after every book ingest

async def verify_ingest(
    book_title: str,
    domain: str,
    rag_base_url: str = "http://localhost:8000",
) -> None:
    """
    Smoke-test a freshly ingested book with three queries:
    1. A factual question the book should answer
    2. A source-specific question naming the book
    3. A negative question the book should NOT answer
    """
    import httpx

    async with httpx.AsyncClient() as client:

        # 1. Factual question
        r = await client.post(f"{rag_base_url}/search", json={
            "query": f"What does {book_title} say about security?",
            "domain": domain,
            "n_results": 3,
        })
        results = r.json()["results"]
        assert len(results) > 0, "No results for factual query"
        assert any(book_title.lower() in r["source"].lower()
                   for r in results), "Expected source not in results"

        # 2. Parity check
        r = await client.get(f"{rag_base_url}/health")
        health = r.json()
        parity = health["store_parity"][domain]
        assert parity["in_sync"], (
            f"Store drift detected after ingest: "
            f"ChromaDB={parity['chroma_chunks']}, "
            f"SQLite={parity['sqlite_chunks']}"
        )

    print(f"✓ {book_title} ingested successfully into {domain} domain")
```

---

## Pipeline Orchestrator

```python
# src/dev_rag/ingest/pipeline.py

"""
dev-rag book ingest pipeline orchestrator.

Usage:
    uv run python -m dev_rag.ingest.pipeline \
        --source data/books/docker-deep-dive.pdf \
        --domain devops \
        --title "Docker Deep Dive"

Flags:
    --start-stage  Resume from a specific stage (1-8) after inspection
    --stop-stage   Stop after a specific stage for inspection
    --dry-run      Run pipeline without writing to ChromaDB/SQLite
"""
import argparse
import asyncio
import json
from pathlib import Path

from .extract  import extract_pdf, extract_url, save_extracted
from .clean    import clean_document
from .structure import detect_structure
from .chunk    import create_chunks
from .enrich   import enrich_all_chunks
from .load     import load_to_stores
from .verify   import verify_ingest


async def run_pipeline(
    source: str,
    domain: str,
    title: str,
    start_stage: int = 1,
    stop_stage: int = 8,
    dry_run: bool = False,
) -> None:

    slug = Path(source).stem.lower().replace(" ", "-")
    data_dir = Path("data")

    print(f"\ndev-rag ingest pipeline: {title} → {domain}")
    print("=" * 60)

    if start_stage <= 1 <= stop_stage:
        print("\n[Stage 1] Extracting...")
        if source.startswith("http"):
            doc = await extract_url(source)
        else:
            doc = extract_pdf(Path(source))
        save_extracted(doc, data_dir / "raw")
        print(f"  ✓ {doc.total_pages} pages extracted → data/raw/{slug}.json")
        if stop_stage == 1:
            print("\n  Stopped after Stage 1. Inspect data/raw/ before continuing.")
            return

    if start_stage <= 2 <= stop_stage:
        print("\n[Stage 2] Cleaning...")
        raw = json.loads((data_dir / "raw" / f"{slug}.json").read_text())
        cleaned = clean_document(raw["pages"])
        removed = sum(1 for p in cleaned if p.was_removed)
        (data_dir / "cleaned").mkdir(exist_ok=True)
        (data_dir / "cleaned" / f"{slug}_cleaned.json").write_text(
            json.dumps([vars(p) for p in cleaned], indent=2)
        )
        print(f"  ✓ {len(cleaned)-removed} pages kept, {removed} removed → data/cleaned/")
        if stop_stage == 2:
            print("\n  Stopped after Stage 2. Inspect data/cleaned/ before continuing.")
            return

    if start_stage <= 3 <= stop_stage:
        print("\n[Stage 3] Detecting structure...")
        cleaned_data = json.loads(
            (data_dir / "cleaned" / f"{slug}_cleaned.json").read_text()
        )
        structure = detect_structure(cleaned_data, title, domain)
        (data_dir / "structured").mkdir(exist_ok=True)
        (data_dir / "structured" / f"{slug}_structure.json").write_text(
            json.dumps({"chapters": structure.chapters,
                        "sections": [vars(s) for s in structure.sections]},
                       indent=2)
        )
        print(f"  ✓ {len(structure.sections)} sections detected → data/structured/")
        if stop_stage == 3:
            print("\n  Stopped after Stage 3. Inspect data/structured/ before continuing.")
            return

    if start_stage <= 4 <= stop_stage:
        print("\n[Stage 4] Chunking...")
        structure_data = json.loads(
            (data_dir / "structured" / f"{slug}_structure.json").read_text()
        )
        chunks = create_chunks(
            structure_data["sections"], source, domain, title
        )
        (data_dir / "chunks").mkdir(exist_ok=True)
        (data_dir / "chunks" / f"{slug}_chunks.json").write_text(
            json.dumps([vars(c) for c in chunks], indent=2)
        )
        print(f"  ✓ {len(chunks)} chunks created → data/chunks/")
        if stop_stage == 4:
            print("\n  Stopped after Stage 4. Inspect data/chunks/ before continuing.")
            return

    if start_stage <= 5 <= stop_stage:
        print("\n[Stage 5] Enriching (summaries, keywords, questions, code)...")
        chunks_data = json.loads(
            (data_dir / "chunks" / f"{slug}_chunks.json").read_text()
        )
        enriched = await enrich_all_chunks(chunks_data, domain)
        (data_dir / "enriched").mkdir(exist_ok=True)
        (data_dir / "enriched" / f"{slug}_enriched.json").write_text(
            json.dumps([vars(c) for c in enriched], indent=2)
        )
        print(f"  ✓ {len(enriched)} chunks enriched → data/enriched/")
        if stop_stage == 5:
            print("\n  Stopped after Stage 5. Inspect data/enriched/ before continuing.")
            return

    if start_stage <= 6 <= stop_stage and start_stage <= 7 <= stop_stage:
        if not dry_run:
            print("\n[Stage 6+7] Embedding and loading...")
            enriched_data = json.loads(
                (data_dir / "enriched" / f"{slug}_enriched.json").read_text()
            )
            await load_to_stores(enriched_data, domain)
            print(f"  ✓ Loaded into ChromaDB and SQLite")
        else:
            print("\n[Stage 6+7] Skipped (dry-run mode)")

    if start_stage <= 8 <= stop_stage and not dry_run:
        print("\n[Stage 8] Verifying...")
        await verify_ingest(title, domain)

    print("\n" + "=" * 60)
    print(f"✓ Pipeline complete: {title}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="dev-rag ingest pipeline")
    parser.add_argument("--source",      required=True)
    parser.add_argument("--domain",      required=True, choices=["devops", "python", "ai"])
    parser.add_argument("--title",       required=True)
    parser.add_argument("--start-stage", type=int, default=1)
    parser.add_argument("--stop-stage",  type=int, default=8)
    parser.add_argument("--dry-run",     action="store_true")
    args = parser.parse_args()

    asyncio.run(run_pipeline(
        source=args.source,
        domain=args.domain,
        title=args.title,
        start_stage=args.start_stage,
        stop_stage=args.stop_stage,
        dry_run=args.dry_run,
    ))
