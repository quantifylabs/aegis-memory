"""
Aegis Memory — Local/In-Process Mode.

SQLite + numpy cosine similarity. Zero server dependencies.

Usage:
    from aegis_memory import AegisClient

    # Local mode — zero config
    client = AegisClient(mode="local")
    client.add("User prefers dark mode", agent_id="ui-agent")
    memories = client.query("user preferences", agent_id="ui-agent")
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

import numpy as np

from ._embeddings import EmbeddingProvider, get_provider
from ._storage import LocalStorage

if TYPE_CHECKING:
    pass


def get_default_db_path() -> str:
    """Return default database path: ~/.aegis/memory.db"""
    aegis_dir = Path.home() / ".aegis"
    aegis_dir.mkdir(parents=True, exist_ok=True)
    return str(aegis_dir / "memory.db")


class LocalBackend:
    """
    In-process backend for AegisClient.

    Orchestrates LocalStorage (SQLite) and EmbeddingProvider (numpy).
    Drop-in replacement for HTTP calls to the Aegis server.
    """

    def __init__(
        self,
        db_path: Optional[str] = None,
        openai_api_key: Optional[str] = None,
        embedding_model: Optional[str] = None,
        embedding_provider: Optional[EmbeddingProvider] = None,
        signing_key: str = "aegis-local-default-key",
    ):
        self.db_path = db_path or get_default_db_path()

        self.embedder = get_provider(
            openai_api_key=openai_api_key or os.environ.get("OPENAI_API_KEY"),
            embedding_model=embedding_model,
            provider=embedding_provider,
        )

        self.storage = LocalStorage(
            db_path=self.db_path,
            signing_key=signing_key,
            embedding_dims=self.embedder.dimensions,
        )

    def close(self) -> None:
        self.storage.close()

    def _embed(self, text: str) -> np.ndarray:
        """Embed a single text with caching."""
        cached = self.storage.get_cached_embedding(text, self._model_name)
        if cached is not None:
            return cached
        emb = self.embedder.embed_single(text)
        self.storage.cache_embedding(text, emb, self._model_name)
        return emb

    def _embed_batch(self, texts: List[str]) -> List[np.ndarray]:
        """Embed a batch of texts with per-item caching."""
        results = [None] * len(texts)
        to_embed = []
        to_embed_idx = []

        for i, text in enumerate(texts):
            cached = self.storage.get_cached_embedding(text, self._model_name)
            if cached is not None:
                results[i] = cached
            else:
                to_embed.append(text)
                to_embed_idx.append(i)

        if to_embed:
            new_embs = self.embedder.embed(to_embed)
            for j, idx in enumerate(to_embed_idx):
                results[idx] = new_embs[j]
                self.storage.cache_embedding(to_embed[j], new_embs[j], self._model_name)

        return results

    @property
    def _model_name(self) -> str:
        return getattr(self.embedder, '_model', getattr(self.embedder, '_model_name', 'unknown'))

    # ========================================================================
    # Core Memory Operations
    # ========================================================================

    def add(self, content: str, **kwargs) -> Dict[str, Any]:
        emb = self._embed(content)
        return self.storage.add_memory(content, emb, **kwargs)

    def add_batch(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        texts = [item["content"] for item in items]
        embeddings = self._embed_batch(texts)
        return self.storage.add_batch(items, embeddings)

    def query(self, query: str, **kwargs) -> List[Dict[str, Any]]:
        emb = self._embed(query)
        return self.storage.semantic_search(emb, **kwargs)

    def query_cross_agent(
        self, query: str, requesting_agent_id: str, **kwargs
    ) -> List[Dict[str, Any]]:
        emb = self._embed(query)
        return self.storage.cross_agent_search(emb, requesting_agent_id, **kwargs)

    def get(self, memory_id: str) -> Optional[Dict[str, Any]]:
        return self.storage.get_memory(memory_id)

    def delete(self, memory_id: str) -> bool:
        return self.storage.delete_memory(memory_id)

    def handoff(
        self,
        source_agent_id: str,
        target_agent_id: str,
        *,
        task_context: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        query_emb = self._embed(task_context) if task_context else None
        return self.storage.handoff(
            source_agent_id, target_agent_id,
            task_context=task_context, query_embedding=query_emb, **kwargs,
        )

    # ========================================================================
    # ACE Operations
    # ========================================================================

    def vote(self, memory_id: str, vote: str, voter_agent_id: str, **kwargs) -> Dict[str, Any]:
        return self.storage.vote(memory_id, vote, voter_agent_id, **kwargs)

    def apply_delta(self, operations: List[Dict[str, Any]]) -> Dict[str, Any]:
        return self.storage.apply_delta(operations, embed_fn=self._embed)

    def add_reflection(self, content: str, agent_id: str, **kwargs) -> str:
        emb = self._embed(content)
        return self.storage.add_reflection(content, emb, agent_id, **kwargs)

    def query_playbook(self, query: str, agent_id: str, **kwargs) -> Dict[str, Any]:
        emb = self._embed(query)
        return self.storage.query_playbook(emb, agent_id, **kwargs)

    # ========================================================================
    # Session & Feature
    # ========================================================================

    def create_session(self, session_id: str, **kwargs) -> Dict[str, Any]:
        return self.storage.create_session(session_id, **kwargs)

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        return self.storage.get_session(session_id)

    def update_session(self, session_id: str, **kwargs) -> Dict[str, Any]:
        return self.storage.update_session(session_id, **kwargs)

    def create_feature(self, feature_id: str, description: str, **kwargs) -> Dict[str, Any]:
        return self.storage.create_feature(feature_id, description, **kwargs)

    def get_feature(self, feature_id: str, namespace: str = "default") -> Optional[Dict[str, Any]]:
        return self.storage.get_feature(feature_id, namespace)

    def update_feature(self, feature_id: str, **kwargs) -> Dict[str, Any]:
        return self.storage.update_feature(feature_id, **kwargs)

    def list_features(self, **kwargs) -> Dict[str, Any]:
        return self.storage.list_features(**kwargs)

    # ========================================================================
    # Run Tracking
    # ========================================================================

    def start_run(self, run_id: str, agent_id: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        return self.storage.start_run(run_id, agent_id, **kwargs)

    def complete_run(self, run_id: str, **kwargs) -> Dict[str, Any]:
        return self.storage.complete_run(run_id, embed_fn=self._embed, **kwargs)

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        return self.storage.get_run(run_id)

    # ========================================================================
    # Curation
    # ========================================================================

    def curate(self, **kwargs) -> Dict[str, Any]:
        return self.storage.curate(**kwargs)

    # ========================================================================
    # Interaction Events
    # ========================================================================

    def record_interaction(
        self, session_id: str, content: str, *, embed: bool = False, **kwargs
    ) -> Dict[str, Any]:
        embedding = self._embed(content) if embed else None
        return self.storage.record_interaction(
            session_id, content, embed=embed, embedding=embedding, **kwargs,
        )

    def get_session_interactions(self, session_id: str, **kwargs) -> Dict[str, Any]:
        return self.storage.get_session_interactions(session_id, **kwargs)

    def get_agent_interactions(self, agent_id: str, **kwargs) -> Dict[str, Any]:
        return self.storage.get_agent_interactions(agent_id, **kwargs)

    def search_interactions(self, query: str, **kwargs) -> Dict[str, Any]:
        emb = self._embed(query)
        return self.storage.search_interactions(emb, **kwargs)

    def get_interaction_chain(self, event_id: str) -> Dict[str, Any]:
        return self.storage.get_interaction_chain(event_id)

    # ========================================================================
    # Export
    # ========================================================================

    def export_json(self, **kwargs) -> Dict[str, Any]:
        return self.storage.export_json(**kwargs)

    # ========================================================================
    # Server-Only Operations (Not Available in Local Mode)
    # ========================================================================

    def scan_content(self, *args, **kwargs):
        raise NotImplementedError(
            "Content security scanning is only available in server mode. "
            "Use AegisClient(api_key='...', base_url='...') for full security features."
        )

    def verify_integrity(self, *args, **kwargs):
        raise NotImplementedError(
            "Server-side integrity verification is only available in server mode. "
            "Local mode signs memories with HMAC-SHA256 at write time."
        )

    def get_flagged_memories(self, *args, **kwargs):
        raise NotImplementedError(
            "Flagged memory review is only available in server mode."
        )

    def get_security_audit(self, *args, **kwargs):
        raise NotImplementedError(
            "Security audit trail is only available in server mode."
        )

    def get_security_config(self, *args, **kwargs):
        raise NotImplementedError(
            "Security configuration is only available in server mode."
        )
