"""
Embedding providers for Aegis Memory local mode.

Supports three tiers:
1. OpenAI API embeddings (requires openai key, uses text-embedding-3-small)
2. Local sentence-transformers (pip install aegis-memory[local], fully offline)
3. Custom provider (user implements EmbeddingProvider protocol)
"""

from __future__ import annotations

from typing import List, Protocol, runtime_checkable

import numpy as np


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Protocol for embedding providers."""

    @property
    def dimensions(self) -> int:
        """Return the embedding dimensionality."""
        ...

    def embed(self, texts: List[str]) -> np.ndarray:
        """
        Embed a batch of texts.

        Args:
            texts: List of strings to embed.

        Returns:
            numpy array of shape (len(texts), dimensions).
        """
        ...

    def embed_single(self, text: str) -> np.ndarray:
        """
        Embed a single text.

        Returns:
            numpy array of shape (dimensions,).
        """
        ...


class OpenAIEmbeddingProvider:
    """
    Embedding provider using OpenAI's text-embedding-3-small model.

    Requires: openai package and OPENAI_API_KEY.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "text-embedding-3-small",
    ):
        try:
            import openai
        except ImportError:
            raise ImportError(
                "OpenAI embeddings require the 'openai' package. "
                "Install with: pip install openai"
            )

        self._model = model
        self._client = openai.OpenAI(api_key=api_key)

        self._dims = {
            "text-embedding-3-small": 1536,
            "text-embedding-3-large": 3072,
            "text-embedding-ada-002": 1536,
        }

    @property
    def dimensions(self) -> int:
        return self._dims.get(self._model, 1536)

    def embed(self, texts: List[str]) -> np.ndarray:
        resp = self._client.embeddings.create(input=texts, model=self._model)
        return np.array([d.embedding for d in resp.data], dtype=np.float32)

    def embed_single(self, text: str) -> np.ndarray:
        return self.embed([text])[0]


class LocalEmbeddingProvider:
    """
    Embedding provider using sentence-transformers (all-MiniLM-L6-v2).

    Fully offline after first model download (~80MB).
    384-dimensional embeddings, fast CPU inference.

    Requires: pip install aegis-memory[local]
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            raise ImportError(
                "Local embeddings require 'sentence-transformers'. "
                "Install with: pip install aegis-memory[local]"
            )

        self._model = SentenceTransformer(model_name)
        self._dimensions = self._model.get_sentence_embedding_dimension()

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed(self, texts: List[str]) -> np.ndarray:
        return self._model.encode(
            texts, convert_to_numpy=True, normalize_embeddings=True,
        ).astype(np.float32)

    def embed_single(self, text: str) -> np.ndarray:
        return self.embed([text])[0]


def get_provider(
    *,
    openai_api_key: str | None = None,
    embedding_model: str | None = None,
    provider: EmbeddingProvider | None = None,
) -> EmbeddingProvider:
    """
    Resolve an embedding provider from user preferences.

    Priority:
    1. Explicit provider instance (custom implementation)
    2. OpenAI if api_key provided
    3. Local sentence-transformers as fallback

    Returns:
        An EmbeddingProvider instance.
    """
    if provider is not None:
        return provider

    if openai_api_key:
        return OpenAIEmbeddingProvider(
            api_key=openai_api_key,
            model=embedding_model or "text-embedding-3-small",
        )

    return LocalEmbeddingProvider(
        model_name=embedding_model or "all-MiniLM-L6-v2",
    )
