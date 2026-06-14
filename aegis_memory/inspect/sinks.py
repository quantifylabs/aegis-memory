"""Precision-first sink catalog. LangGraph is the v1 target; a general fallback
covers vector DBs and custom memory-ish names at lower confidence.

A *sink* is a call site that writes durable memory/state. The analyzer (``analyzer.py``)
extracts, for every ``ast.Call``: the final attribute/function name, the receiver
("root object") name when present, and a best-effort dotted call string. This module
maps that to a catalog entry, or returns ``None``. No rule keys off demo filenames or
strings — matching is purely on the documented sink shapes (SSOT §7 / Task §3.4).
"""

from __future__ import annotations

from dataclasses import dataclass

from .findings import Category


@dataclass(frozen=True)
class SinkMatch:
    framework: str  # "langgraph" | "vectordb" | "custom"
    call: str  # canonical call label, e.g. "store.put"
    category: str  # Category value (structural)
    base_confidence: str  # "EXTRACTED" baseline trust we can place in the *sink* match


# ---- LangGraph (primary, high precision) -----------------------------------------

# Receiver-name hints that mark a LangGraph store/checkpointer write.
_LANGGRAPH_STORE_HINTS = ("store", "memorystore", "in_memory_store", "basestore")
_LANGGRAPH_CKPT_HINTS = ("checkpointer", "saver", "memorysaver", "ckpt")

# Method names that constitute a write on those receivers.
_LANGGRAPH_WRITE_METHODS = ("put", "aput", "put_writes")

# Free-function state writers.
_LANGGRAPH_STATE_FUNCS = ("add_messages",)


# ---- General fallback (lower precision, tag accordingly) --------------------------

_VECTORDB_METHODS = ("add", "upsert", "add_texts", "add_documents", "aadd_texts", "aadd_documents")
_VECTORDB_RECEIVER_HINTS = (
    "chroma",
    "pinecone",
    "qdrant",
    "weaviate",
    "pgvector",
    "faiss",
    "index",
    "collection",
    "vectorstore",
    "vector_store",
    "vectordb",
)

# Custom: receivers/functions named like memory.
_CUSTOM_NAME_HINTS = ("memory", "store", "save", "history", "context", "scratchpad")
_CUSTOM_WRITE_METHODS = ("put", "add", "save", "write", "append", "set", "store", "remember", "insert")


# ---- Shared, reusable across the package ------------------------------------------
# ``guard.protect`` screens exactly the call shapes this catalog flags, so detection and
# runtime enforcement key off the *same* method names and never drift.

# ``put(namespace, key, value)`` style — the written value is the 3rd positional arg.
KEYED_WRITE_METHODS: frozenset[str] = frozenset(_LANGGRAPH_WRITE_METHODS)

# Every instance-method name that constitutes a durable memory write.
WRITE_METHODS: frozenset[str] = frozenset(
    _LANGGRAPH_WRITE_METHODS + _VECTORDB_METHODS + _CUSTOM_WRITE_METHODS
)


def _norm(s: str | None) -> str:
    return (s or "").lower()


def classify_call(*, attr: str | None, func: str | None, receiver: str | None) -> SinkMatch | None:
    """Return a :class:`SinkMatch` if this call is a known memory-write sink, else None.

    ``attr`` is the method name for ``obj.method(...)`` calls; ``func`` is the function
    name for bare ``func(...)`` calls; ``receiver`` is the root object name for method
    calls (best effort, may be None).
    """
    a = _norm(attr)
    f = _norm(func)
    r = _norm(receiver)

    # --- LangGraph free functions (add_messages into state) ---
    if f in _LANGGRAPH_STATE_FUNCS:
        return SinkMatch("langgraph", f, Category.MEMORY_WRITE.value, "EXTRACTED")

    # --- LangGraph store / checkpointer writes ---
    if a in _LANGGRAPH_WRITE_METHODS:
        if any(h in r for h in _LANGGRAPH_STORE_HINTS):
            return SinkMatch("langgraph", f"{receiver}.{attr}", Category.MEMORY_WRITE.value, "EXTRACTED")
        if any(h in r for h in _LANGGRAPH_CKPT_HINTS):
            return SinkMatch("langgraph", f"{receiver}.{attr}", Category.MEMORY_WRITE.value, "EXTRACTED")

    # --- Vector DB writes (general fallback, lower confidence) ---
    if a in _VECTORDB_METHODS and any(h in r for h in _VECTORDB_RECEIVER_HINTS):
        return SinkMatch("vectordb", f"{receiver}.{attr}", Category.VECTOR_DB_WRITE.value, "INFERRED")

    # --- Custom memory-ish sinks (general fallback, lowest confidence) ---
    if a in _CUSTOM_WRITE_METHODS and any(h in r for h in _CUSTOM_NAME_HINTS):
        return SinkMatch("custom", f"{receiver}.{attr}", Category.MEMORY_WRITE.value, "AMBIGUOUS")

    return None


__all__ = ["KEYED_WRITE_METHODS", "WRITE_METHODS", "SinkMatch", "classify_call"]
