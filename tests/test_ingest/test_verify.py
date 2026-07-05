"""Stage 8 verify tests — temp stores via load_to_stores, mocked model."""
import sqlite3
from pathlib import Path

import numpy as np
import pytest

from dev_rag.ingest.load import load_to_stores
from dev_rag.ingest.util import content_hash
from dev_rag.ingest.verify import VerificationError, verify_ingest

MIGRATIONS = Path(__file__).resolve().parents[2] / "migrations"
DIM = 8


class FakeQueryModel:
    """Returns a vector near chunk 1's embedding."""

    def encode(self, text, **kwargs):
        v = np.zeros(DIM, dtype=np.float32)
        v[1] = 1.0
        return v


def make_chunk(i):
    content = f"Chunk {i} covers docker restart policies and self-healing."
    return {
        "chunk_id": f"tiny_{i:04d}",
        "source_id": "tiny",
        "source": "tiny.pdf",
        "domain": "devops",
        "title": "Tiny Book",
        "page_number": i + 1,
        "content": content,
        "content_hash": content_hash(content),
    }


def one_hot(i):
    v = [0.0] * DIM
    v[i] = 1.0
    return v


@pytest.fixture
def loaded_stores(tmp_path):
    stores = {
        "chroma_path": str(tmp_path / "chroma"),
        "sqlite_path": tmp_path / "dev_rag.db",
    }
    load_to_stores(
        [make_chunk(i) for i in range(3)],
        [one_hot(i) for i in range(3)],
        migrations_dir=MIGRATIONS,
        **stores,
    )
    return stores


def test_verify_passes_on_healthy_store(loaded_stores):
    report = verify_ingest(
        domain="devops",
        expected_source="tiny.pdf",
        query="how do restart policies work",
        model=FakeQueryModel(),
        **loaded_stores,
    )
    assert report.parity_ok
    assert report.chroma_count == 3
    # nearest neighbour of the one-hot query is chunk 1
    assert report.top_results[0]["chunk_id"] == "tiny_0001"
    assert report.top_results[0]["source"] == "tiny.pdf"


def test_verify_fails_on_wrong_source(loaded_stores):
    with pytest.raises(VerificationError, match="no chunk from"):
        verify_ingest(
            domain="devops",
            expected_source="other-book.pdf",
            query="anything",
            model=FakeQueryModel(),
            **loaded_stores,
        )


def test_verify_fails_on_store_drift(loaded_stores):
    # Simulate a partial-write failure: SQLite loses a row, Chroma keeps it
    conn = sqlite3.connect(loaded_stores["sqlite_path"])
    conn.execute("DELETE FROM chunks WHERE chunk_id = 'tiny_0002'")
    conn.commit()
    conn.close()
    with pytest.raises(VerificationError, match="parity failed"):
        verify_ingest(
            domain="devops",
            expected_source="tiny.pdf",
            query="anything",
            model=FakeQueryModel(),
            **loaded_stores,
        )
