"""
Stage 6 embed tests — the model is ALWAYS mocked.

Never load real BGE-M3 here: first load downloads ~2GB and this is a
CPU-only machine; the suite would become unusable.
"""
import json

import numpy as np
import pytest

from dev_rag.ingest.embed import embed_chunks, load_chunks, save_embeddings


class FakeModel:
    def __init__(self, dim=1024, nan_at=None):
        self.dim = dim
        self.nan_at = nan_at
        self.encode_calls = []

    def encode(self, texts, **kwargs):
        self.encode_calls.append((len(texts), kwargs))
        rng = np.random.default_rng(seed=0)
        out = rng.normal(size=(len(texts), self.dim)).astype(np.float32)
        if self.nan_at is not None:
            out[self.nan_at, 0] = np.nan
        return out


def make_chunks(n):
    return [
        {"chunk_id": f"tiny_{i:04d}", "source_id": "tiny", "content": f"chunk {i}"}
        for i in range(n)
    ]


def test_embed_chunks_shape_and_order():
    chunks = make_chunks(3)
    model = FakeModel()
    embeddings = embed_chunks(chunks, model)
    assert len(embeddings) == 3
    assert all(len(e) == 1024 for e in embeddings)
    assert all(isinstance(x, float) for x in embeddings[0])
    # one encode call carrying all texts, batch size passed through
    assert model.encode_calls[0][0] == 3
    assert model.encode_calls[0][1]["batch_size"] == 32
    assert model.encode_calls[0][1]["normalize_embeddings"] is True


def test_wrong_dimension_rejected():
    model = FakeModel(dim=768)
    with pytest.raises(ValueError, match="dim 768 != 1024"):
        embed_chunks(make_chunks(2), model)


def test_nan_rejected():
    model = FakeModel(nan_at=1)
    with pytest.raises(ValueError, match="NaN"):
        embed_chunks(make_chunks(2), model)


def test_save_and_load_round_trip(tmp_path):
    chunks = make_chunks(2)
    chunks_path = tmp_path / "tiny_chunks.json"
    chunks_path.write_text(json.dumps(chunks))
    loaded = load_chunks(chunks_path)
    embeddings = embed_chunks(loaded, FakeModel())
    saved = save_embeddings(loaded, embeddings, tmp_path / "embeddings")
    assert saved.name == "tiny_embeddings.json"
    data = json.loads(saved.read_text())
    assert [d["chunk_id"] for d in data] == ["tiny_0000", "tiny_0001"]
    assert data[0]["embedding"] == embeddings[0]


def test_save_embeddings_requires_matching_lengths(tmp_path):
    chunks = make_chunks(2)
    with pytest.raises(ValueError):
        save_embeddings(chunks, [[0.0] * 1024], tmp_path)
