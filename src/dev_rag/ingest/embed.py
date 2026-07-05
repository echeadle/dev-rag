"""
Stage 6: Embed — dense BGE-M3 vectors for each chunk.

Dense only: the sparse channel is FTS5/BM25 per
planning/hybrid-search-spec.md, so no FlagEmbedding here. In Phase 1a
the embedding text is the raw chunk content; the spec's combined text
(section header + summary + keywords) needs Stage 5 enrichment (1b).

Embeddings are L2-normalized so the Chroma collection can use cosine
distance. Saved as compact JSON (~6MB for a book) so Stage 7 reads a
data/ artifact like every other stage.

Spec: planning/ingest-pipeline-spec.md (Stage 6).
"""
import json
import math
from pathlib import Path

EXPECTED_DIM = 1024   # BGE-M3 dense dimension


def get_embedder(model_name: str | None = None):
    """
    Load the real SentenceTransformer model (device auto-detect).

    Slow on first call ever: downloads ~2GB from HuggingFace, then
    cached. Never call this in tests — inject a mock into embed_chunks.
    """
    import torch
    from sentence_transformers import SentenceTransformer

    from dev_rag.settings import settings

    device = "cuda" if torch.cuda.is_available() else "cpu"
    return SentenceTransformer(model_name or settings.embedding_model, device=device)


def embed_chunks(
    chunks: list[dict],
    model,
    batch_size: int = 32,
) -> list[list[float]]:
    """
    Embed chunk contents, preserving order.

    Asserts dim 1024 and no NaNs — a wrong model or a poisoned input
    should fail here, not surface as garbage retrieval later.
    """
    texts = [c["content"] for c in chunks]
    vectors = model.encode(
        texts,
        batch_size=batch_size,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=True,
    )

    embeddings = [list(map(float, v)) for v in vectors]
    for i, v in enumerate(embeddings):
        if len(v) != EXPECTED_DIM:
            raise ValueError(
                f"chunk {chunks[i]['chunk_id']}: dim {len(v)} != {EXPECTED_DIM}"
            )
        if any(math.isnan(x) for x in v):
            raise ValueError(f"chunk {chunks[i]['chunk_id']}: NaN in embedding")

    return embeddings


def load_chunks(path: Path) -> list[dict]:
    """Load a Stage 4 chunks JSON."""
    return json.loads(path.read_text())


def save_embeddings(
    chunks: list[dict],
    embeddings: list[list[float]],
    output_dir: Path,
) -> Path:
    """Save chunk_id → embedding pairs for Stage 7 (compact JSON)."""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{chunks[0]['source_id']}_embeddings.json"
    path.write_text(json.dumps([
        {"chunk_id": c["chunk_id"], "embedding": e}
        for c, e in zip(chunks, embeddings, strict=True)
    ]))
    return path
