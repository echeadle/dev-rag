"""Stage 4 chunk tests — synthetic cleaned document, no real book."""
import json

from dev_rag.ingest.chunk import chunk_document, load_cleaned, save_chunks
from dev_rag.ingest.util import content_hash


def cleaned_doc(pages):
    return {
        "source_path": "data/books/tiny-book.pdf",
        "source_type": "pdf",
        "title": "Tiny Book",
        "total_pages": len(pages),
        "pages": pages,
    }


def page(num, text, removed=False):
    return {
        "page_number": num,
        "text": text,
        "was_removed": removed,
        "removal_reason": "noise" if removed else "",
    }


def make_text(n_words, word="docker"):
    # Varying word lengths — periodic (uniform-length) words can land the
    # overlap start on word boundaries by luck and mask mid-word splits
    return " ".join(f"{word}{'x' * (i % 7)}{i}" for i in range(n_words))


def test_short_document_is_one_chunk():
    doc = cleaned_doc([page(1, "Docker networking basics explained.")])
    chunks = chunk_document(doc, domain="devops")
    assert len(chunks) == 1
    c = chunks[0]
    assert c.chunk_id == "tiny-book_0001"
    assert c.source_id == "tiny-book"
    assert c.source == "tiny-book.pdf"
    assert c.domain == "devops"
    assert c.title == "Tiny Book"
    assert c.page_number == 1
    assert c.content_hash == content_hash(c.content)


def test_long_text_split_with_overlap():
    doc = cleaned_doc([page(1, make_text(700))])   # ~5600 chars
    chunks = chunk_document(doc, domain="devops", chunk_size=1500, overlap=200)
    assert len(chunks) > 1
    for c in chunks:
        assert len(c.content) <= 1500
    # consecutive chunks share overlapping words (all words unique here,
    # so any intersection proves genuine overlap)
    for a, b in zip(chunks, chunks[1:]):
        assert set(a.content.split()[-40:]) & set(b.content.split()[:20])


def test_never_splits_mid_word():
    doc = cleaned_doc([page(1, make_text(700))])
    chunks = chunk_document(doc, domain="devops")
    words = set(make_text(700).split())
    for c in chunks:
        for w in c.content.split():
            assert w in words, f"split word: {w!r}"


def test_removed_pages_excluded():
    doc = cleaned_doc([
        page(1, "Contents . . . . 5", removed=True),
        page(2, "Real content about Docker overlay networks."),
    ])
    chunks = chunk_document(doc, domain="devops")
    assert len(chunks) == 1
    assert "Contents" not in chunks[0].content
    assert chunks[0].page_number == 2


def test_chunks_span_page_breaks():
    # Two small pages must land in ONE chunk (window is document-wide)
    doc = cleaned_doc([
        page(1, "Step one: create the overlay network."),
        page(2, "Step two: attach the service to it."),
    ])
    chunks = chunk_document(doc, domain="devops")
    assert len(chunks) == 1
    assert "Step one" in chunks[0].content and "Step two" in chunks[0].content
    assert chunks[0].page_number == 1


def test_page_number_tracks_chunk_start():
    doc = cleaned_doc([
        page(1, make_text(300, "alpha")),    # ~2400 chars -> chunk 2 starts here
        page(2, make_text(300, "beta")),
    ])
    chunks = chunk_document(doc, domain="devops")
    assert chunks[0].page_number == 1
    assert chunks[-1].page_number == 2


def test_save_and_load_round_trip(tmp_path):
    doc = cleaned_doc([page(1, "Docker networking basics explained.")])
    cleaned_path = tmp_path / "tiny-book_cleaned.json"
    cleaned_path.write_text(json.dumps(doc))
    chunks = chunk_document(load_cleaned(cleaned_path), domain="devops")
    saved = save_chunks(chunks, tmp_path / "chunks")
    assert saved.name == "tiny-book_chunks.json"
    data = json.loads(saved.read_text())
    assert len(data) == 1
    assert data[0]["chunk_id"] == "tiny-book_0001"
    assert data[0]["content_hash"] == chunks[0].content_hash
