"""Embedding service re-export for the new package structure."""
from embedding_service import (
    EmbeddingService,
    content_hash,
    get_embedding_service,
)

__all__ = ["EmbeddingService", "content_hash", "get_embedding_service"]
