"""
Aegis Memory LangGraph Integration

A dependency-light helper that gives LangGraph graphs long-term, semantic memory
backed by Aegis Memory. It exposes two primitives every stateful graph needs:

- **retrieve** relevant memories for the current state (call before a node runs), and
- **remember** new memory produced by a node/run (call after a node runs).

Because LangGraph state is just a ``dict`` / ``TypedDict``, this adapter does **not**
import ``langgraph`` at all — it operates on plain state dicts, so it works with any
graph shape and adds no hard dependency.

Scope note (honesty): this is a retrieve/persist helper, **not** a LangGraph
checkpointer. It does not implement ``BaseCheckpointSaver`` and does not persist or
restore graph execution state / thread history. Use LangGraph's own checkpointer for
that; use this for durable, security-scanned semantic memory.

Usage:
    from aegis_memory import local_client  # or AegisClient(api_key=..., base_url=...)
    from aegis_memory.integrations.langgraph import AegisLangGraphMemory

    memory = AegisLangGraphMemory(client=local_client(), namespace="support-graph")

    def agent_node(state: dict) -> dict:
        # 1. Pull relevant prior memory into state before reasoning.
        state = memory.load_into_state(state, state["question"], agent_id="assistant")
        context = state["aegis_memories"]  # list[dict]
        ...  # call the model using `context`
        # 2. Persist what was learned after reasoning.
        memory.remember(answer, agent_id="assistant",
                        metadata={"question": state["question"]})
        return state
"""

from typing import Any

from aegis_memory.client import AegisClient


class AegisLangGraphMemory:
    """
    LangGraph-friendly memory backed by Aegis Memory.

    Wraps a single :class:`~aegis_memory.client.AegisClient` and exposes
    retrieve/persist helpers plus small utilities for reading and writing a
    LangGraph state dict. It is intentionally framework-agnostic (no ``langgraph``
    import) and returns plain dicts rather than SDK model objects.

    Args:
        client: An existing ``AegisClient`` (server or local mode). If omitted, an
            ``AegisClient`` is constructed from ``api_key`` / ``base_url``.
        api_key: Aegis Memory API key (used only when ``client`` is not supplied).
        base_url: Aegis Memory server URL (used only when ``client`` is not supplied).
        namespace: Memory namespace for this graph.
        default_scope: Default scope for stored memories.
        state_key: State dict key under which retrieved memories are placed by
            :meth:`load_into_state`.
    """

    def __init__(
        self,
        client: AegisClient | None = None,
        *,
        api_key: str | None = None,
        base_url: str = "http://localhost:8000",
        namespace: str = "langgraph",
        default_scope: str = "agent-shared",
        state_key: str = "aegis_memories",
    ):
        if client is None:
            if api_key is None:
                raise ValueError(
                    "AegisLangGraphMemory requires either a `client` or an `api_key`."
                )
            client = AegisClient(api_key=api_key, base_url=base_url)
        self.client = client
        self.namespace = namespace
        self.default_scope = default_scope
        self.state_key = state_key

    # ---------- Core primitives ----------

    def retrieve(
        self,
        query: str,
        *,
        agent_id: str | None = None,
        top_k: int = 10,
        min_score: float = 0.0,
    ) -> list[dict[str, Any]]:
        """
        Retrieve memories relevant to ``query`` (call before a node runs).

        If ``agent_id`` is given, cross-agent access control is applied via
        ``query_cross_agent``; otherwise a plain namespace query is used.

        Returns:
            List of memory dicts with ``content``, ``metadata``, ``score`` and
            ``agent_id`` — safe to drop straight into a prompt or graph state.
        """
        if agent_id:
            memories = self.client.query_cross_agent(
                query=query,
                requesting_agent_id=agent_id,
                namespace=self.namespace,
                top_k=top_k,
                min_score=min_score,
            )
        else:
            memories = self.client.query(
                query=query,
                namespace=self.namespace,
                top_k=top_k,
                min_score=min_score,
            )

        return [
            {
                "content": mem.content,
                "metadata": mem.metadata,
                "score": mem.score,
                "agent_id": mem.agent_id,
            }
            for mem in memories
        ]

    def remember(
        self,
        content: str,
        *,
        agent_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        scope: str | None = None,
    ) -> str:
        """
        Persist a new memory produced by a node/run (call after a node runs).

        Content is security-scanned, embedded and (optionally) integrity-hashed by
        the Aegis server before storage — nothing here bypasses those checks.

        Returns:
            The stored memory ID (or the ID of an existing duplicate).
        """
        result = self.client.add(
            content=content,
            agent_id=agent_id,
            namespace=self.namespace,
            scope=scope or self.default_scope,
            metadata={
                "source": "langgraph",
                **(metadata or {}),
            },
        )
        return result.id

    # ---------- State helpers (LangGraph state is a plain dict) ----------

    def load_into_state(
        self,
        state: dict[str, Any],
        query: str,
        *,
        agent_id: str | None = None,
        top_k: int = 10,
        key: str | None = None,
    ) -> dict[str, Any]:
        """
        Retrieve memories for ``query`` and write them into ``state`` under
        ``key`` (defaults to ``self.state_key``), returning the mutated state.

        Designed to be the first line of a node:
            ``state = memory.load_into_state(state, state["question"])``
        """
        target_key = key or self.state_key
        state[target_key] = self.retrieve(query, agent_id=agent_id, top_k=top_k)
        return state

    def persist_from_state(
        self,
        state: dict[str, Any],
        content_key: str,
        *,
        agent_id: str | None = None,
        metadata_key: str | None = None,
        scope: str | None = None,
    ) -> str | None:
        """
        Persist a value already present in ``state`` (e.g. a node's output) as a
        memory. No-ops (returns ``None``) if ``content_key`` is missing/empty.

        Args:
            content_key: State key holding the content to store.
            metadata_key: Optional state key holding a metadata dict to attach.
        """
        content = state.get(content_key)
        if not content:
            return None
        metadata = state.get(metadata_key) if metadata_key else None
        return self.remember(
            str(content),
            agent_id=agent_id,
            metadata=metadata if isinstance(metadata, dict) else None,
            scope=scope,
        )
