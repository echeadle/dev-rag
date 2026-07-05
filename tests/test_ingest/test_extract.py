"""Stage 1 extract tests — use a tiny generated PDF, never the full book."""
import json

import fitz
import pytest

from dev_rag.ingest.extract import extract_pdf, extract_url, save_extracted


@pytest.fixture
def tiny_pdf(tmp_path):
    """Two-page PDF with known text on each page."""
    path = tmp_path / "tiny-book.pdf"
    doc = fitz.open()
    for text in ("Page one: Docker networking basics.",
                 "Page two: Docker secrets in production."):
        page = doc.new_page()
        page.insert_text((72, 72), text)
    doc.set_metadata({"title": "Tiny Book"})
    doc.save(str(path))
    doc.close()
    return path


def test_extract_pdf_preserves_page_boundaries(tiny_pdf):
    doc = extract_pdf(tiny_pdf)
    assert doc.source_type == "pdf"
    assert doc.total_pages == 2
    assert [p.page_number for p in doc.pages] == [1, 2]
    assert "networking basics" in doc.pages[0].text
    assert "secrets in production" in doc.pages[1].text


def test_extract_pdf_title_from_metadata(tiny_pdf):
    doc = extract_pdf(tiny_pdf)
    assert doc.title == "Tiny Book"


def test_extract_pdf_title_falls_back_to_filename(tmp_path):
    path = tmp_path / "no-title_book.pdf"
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), "text")
    doc.save(str(path))
    doc.close()
    assert extract_pdf(path).title == "no title book"


def test_save_extracted_round_trips(tiny_pdf, tmp_path):
    out_dir = tmp_path / "raw"
    saved = save_extracted(extract_pdf(tiny_pdf), out_dir)
    assert saved == out_dir / "tiny-book.json"
    data = json.loads(saved.read_text())
    assert data["title"] == "Tiny Book"
    assert data["total_pages"] == 2
    assert len(data["pages"]) == 2
    assert data["pages"][0]["page_number"] == 1
    assert "networking basics" in data["pages"][0]["text"]


async def test_extract_url_is_deferred():
    with pytest.raises(NotImplementedError):
        await extract_url("https://example.com")
