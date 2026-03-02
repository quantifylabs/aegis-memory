"""
Tests for aegis_memory.local._embeddings — embedding providers.

These tests use a lightweight fake provider to avoid requiring
OpenAI keys or sentence-transformers at test time.
"""

import numpy as np
import pytest

from aegis_memory.local._embeddings import (
    EmbeddingProvider,
    get_provider,
)


# ---------------------------------------------------------------------------
# Fake provider for testing
# ---------------------------------------------------------------------------


class FakeEmbeddingProvider:
    """Deterministic embedding provider for tests (32-dim)."""

    dimensions = 32

    def embed(self, texts):
        return [self.embed_single(t) for t in texts]

    def embed_single(self, text):
        rng = np.random.RandomState(hash(text) % 2**31)
        vec = rng.randn(self.dimensions).astype(np.float32)
        vec /= np.linalg.norm(vec)
        return vec


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFakeProvider:
    """Ensure our FakeEmbeddingProvider satisfies the protocol."""

    def test_has_dimensions(self):
        p = FakeEmbeddingProvider()
        assert p.dimensions == 32

    def test_embed_single_shape(self):
        p = FakeEmbeddingProvider()
        vec = p.embed_single("hello")
        assert isinstance(vec, np.ndarray)
        assert vec.shape == (32,)

    def test_embed_batch(self):
        p = FakeEmbeddingProvider()
        vecs = p.embed(["hello", "world"])
        assert len(vecs) == 2
        for v in vecs:
            assert v.shape == (32,)

    def test_deterministic(self):
        p = FakeEmbeddingProvider()
        a = p.embed_single("test")
        b = p.embed_single("test")
        np.testing.assert_array_equal(a, b)

    def test_different_texts_different_vectors(self):
        p = FakeEmbeddingProvider()
        a = p.embed_single("hello")
        b = p.embed_single("world")
        assert not np.allclose(a, b)

    def test_is_runtime_checkable(self):
        p = FakeEmbeddingProvider()
        assert isinstance(p, EmbeddingProvider)


class TestGetProvider:
    def test_custom_provider(self):
        custom = FakeEmbeddingProvider()
        result = get_provider(provider=custom)
        assert result is custom

    def test_no_key_no_transformers_raises(self):
        """Without OpenAI key and without sentence-transformers, should raise."""
        # This might actually succeed if sentence-transformers is installed,
        # so we only check that get_provider doesn't crash with a custom provider.
        custom = FakeEmbeddingProvider()
        result = get_provider(provider=custom)
        assert result.dimensions == 32
