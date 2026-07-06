"""
dev-rag settings — loaded from environment / .env file.
All settings have sensible defaults for local development.

OBS-012 fix: uses Pydantic v2 model_config = SettingsConfigDict(...)
instead of the deprecated v1-era inner class Config.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path


class Settings(BaseSettings):
    # OBS-012: Pydantic v2 style config — replaces inner class Config
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Anthropic
    anthropic_api_key: str = ""

    # Paths
    chroma_db_path: str = "./chroma_db"
    sqlite_db_path: Path = Path("./data/dev_rag.db")
    graph_db_path: Path = Path("./graph_db/knowledge_graph.json")

    # Postgres (pgvector migration — Phase 7)
    database_url: str = "postgresql://devrag:devrag@localhost:5432/devrag"

    # Embedding model
    embedding_model: str = "BAAI/bge-m3"

    # Search
    search_mode: str = "hybrid"           # dense | sparse | hybrid
    rrf_k: int = 60
    dense_candidates: int = 20
    sparse_candidates: int = 20

    # Reranker (Phase 3 — implemented, OFF by default): bge-reranker-v2-m3
    # costs ~1.5-2 s/pair on CPU — measured 2026-07-06: ~15 s/query at 10
    # candidates, ~112 s at 50, vs ~0.15 s RRF-only. Enable per-run with
    # RERANKER_ENABLED=true (+ RERANKER_CANDIDATES=10) for eval/quality A-B;
    # revisit the default when Phase 4 eval quantifies the accuracy delta.
    reranker_enabled: bool = False
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    reranker_top_n: int = 10
    reranker_candidates: int = 50
    reranker_batch_size: int = 32

    # Domains
    valid_domains: list[str] = ["devops", "travel", "python", "ai"]


settings = Settings()
