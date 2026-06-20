"""Precision-first sink catalog. LangGraph is the v1 target; a general fallback
covers vector DBs and custom memory APIs at lower confidence.

A *sink* is a call site that writes durable memory/state. The analyzer (``analyzer.py``)
extracts, for every ``ast.Call``: the final attribute/function name, the receiver
("root object") name when present, the keyword-argument names, and a best-effort dotted
call string. This module maps that to a catalog entry, or returns ``None``.

Matching is on **call semantics — receiver + method (+ keyword signature)**, never on whether
a *variable name* contains a substring like "store"/"save". That older approach minted false
positives (a local ``stored.append(x)`` looked like a sink purely because the variable was
named ``stored``) and missed real sinks whose receivers happen to be named ``client``/``memory``.
The model here is three explicit tiers, strongest first:

1. **Distinctive memory-write methods** (``store_intelligence``, …) — the method name alone is
   enough; these are effectively never an innocent local call.
2. **API-signature writes** — a generic write verb (``add``/``save``/``put``/…) that carries a
   memory-API keyword (``scope=``/``shared_with_agents=``/``namespace=``/``trust_level=``). This is
   how ``self.client.add(scope="agent-shared", …)`` is caught despite the receiver named ``client``.
3. **Receiver-shape fallbacks** — generic write verbs on a receiver whose dotted name matches a
   known framework shape (LangGraph store/checkpointer, vector DB index/collection, or a custom
   memory object). Lower confidence, tagged accordingly. ``append``/bare ``set`` are deliberately
   **not** matchable here so a plain ``list.append`` / local container never registers as a sink.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .findings import Category


@dataclass(frozen=True)
class SinkMatch:
    framework: str  # "langgraph" | "vectordb" | "aegis" | "custom"
    call: str  # canonical call label, e.g. "store.put"
    category: str  # Category value (structural)
    base_confidence: str  # "EXTRACTED" baseline trust we can place in the *sink* match


# ---- Tier 1: distinctive memory-write methods (match on method name alone) ---------
# These verbs name a durable memory write so specifically that the receiver is irrelevant;
# they do not collide with ordinary local-object methods the way ``add``/``save`` do.
_DISTINCTIVE_WRITE_METHODS = (
    "store_intelligence",
    "store_memory",
    "add_memory",
    "add_reflection",
    "remember_fact",
    "save_memory",
)

# ---- Tier 2: generic write verbs that qualify when an API signature is present ------
_API_WRITE_VERBS = ("add", "save", "put", "aput", "set", "write", "insert", "store", "update", "upsert")
# Keyword arguments distinctive of agent-memory write APIs. Their presence promotes an
# otherwise-ambiguous verb to a confident sink regardless of the receiver's name.
_API_SIGNATURE_KWARGS = ("scope", "shared_with_agents", "namespace", "trust_level")


# ---- Tier 3a: LangGraph (primary, high precision) ----------------------------------

# Receiver-name shapes that mark a LangGraph store/checkpointer write.
_LANGGRAPH_STORE_HINTS = ("store", "memorystore", "in_memory_store", "basestore")
_LANGGRAPH_CKPT_HINTS = ("checkpointer", "saver", "memorysaver", "ckpt")

# Method names that constitute a write on those receivers.
_LANGGRAPH_WRITE_METHODS = ("put", "aput", "put_writes")

# Free-function state writers.
_LANGGRAPH_STATE_FUNCS = ("add_messages",)


# ---- Tier 3b: vector DBs (lower precision, tag accordingly) -------------------------

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


# ---- Tier 3c: custom memory-ish receivers (lowest confidence) ----------------------
# Receiver-shape hints for a custom memory object. NB: ``append`` and bare ``set`` are
# intentionally excluded from the matchable methods below — they collide with ordinary local
# containers (``list.append`` / ``set``-like state) and were the source of false positives.
_CUSTOM_NAME_HINTS = ("memory", "store", "save", "history", "context", "scratchpad", "knowledgebase")
_CUSTOM_WRITE_METHODS_STATIC = ("put", "add", "save", "write", "store", "remember", "insert")


# ---- Shared, reusable across the package ------------------------------------------
# ``guard.protect`` screens the call shapes this catalog flags, so detection and runtime
# enforcement key off the *same* method names and never drift. These frozensets are the
# runtime contract and are kept stable on purpose (they still include ``append``/``set`` so the
# runtime guard continues to wrap those calls); the *static* matcher above is deliberately more
# conservative to avoid local-container false positives.
_CUSTOM_WRITE_METHODS = ("put", "add", "save", "write", "append", "set", "store", "remember", "insert")

# ``put(namespace, key, value)`` style — the written value is the 3rd positional arg.
KEYED_WRITE_METHODS: frozenset[str] = frozenset(_LANGGRAPH_WRITE_METHODS)

# Every instance-method name that constitutes a durable memory write (runtime-guard contract).
WRITE_METHODS: frozenset[str] = frozenset(
    _LANGGRAPH_WRITE_METHODS + _VECTORDB_METHODS + _CUSTOM_WRITE_METHODS
)


def _norm(s: str | None) -> str:
    return (s or "").lower()


def classify_call(
    *,
    attr: str | None,
    func: str | None,
    receiver: str | None,
    keywords: Sequence[str] = (),
) -> SinkMatch | None:
    """Return a :class:`SinkMatch` if this call is a known memory-write sink, else None.

    ``attr`` is the method name for ``obj.method(...)`` calls; ``func`` is the function name for
    bare ``func(...)`` calls; ``receiver`` is the (possibly dotted) root-object name for method
    calls; ``keywords`` are the call's keyword-argument names (used by the API-signature tier).
    """
    a = _norm(attr)
    f = _norm(func)
    r = _norm(receiver)
    kw = {_norm(k) for k in keywords}

    # --- LangGraph free functions (add_messages into state) ---
    if f in _LANGGRAPH_STATE_FUNCS:
        return SinkMatch("langgraph", f, Category.MEMORY_WRITE.value, "EXTRACTED")

    # Bare function calls beyond the state funcs are never durable-memory sinks here.
    if not a:
        return None

    # --- Tier 1: distinctive memory-write methods (receiver-agnostic) ---
    if a in _DISTINCTIVE_WRITE_METHODS:
        return SinkMatch("aegis", f"{receiver}.{attr}" if receiver else attr,
                         Category.MEMORY_WRITE.value, "EXTRACTED")

    # --- Tier 2: generic write verb carrying a memory-API keyword signature ---
    if a in _API_WRITE_VERBS and (kw & set(_API_SIGNATURE_KWARGS)):
        return SinkMatch("aegis", f"{receiver}.{attr}" if receiver else attr,
                         Category.MEMORY_WRITE.value, "EXTRACTED")

    # --- Tier 3a: LangGraph store / checkpointer writes (receiver-shape) ---
    if a in _LANGGRAPH_WRITE_METHODS:
        if any(h in r for h in _LANGGRAPH_STORE_HINTS) or any(h in r for h in _LANGGRAPH_CKPT_HINTS):
            return SinkMatch("langgraph", f"{receiver}.{attr}", Category.MEMORY_WRITE.value, "EXTRACTED")

    # --- Tier 3b: vector DB writes (receiver-shape, lower confidence) ---
    if a in _VECTORDB_METHODS and any(h in r for h in _VECTORDB_RECEIVER_HINTS):
        return SinkMatch("vectordb", f"{receiver}.{attr}", Category.VECTOR_DB_WRITE.value, "INFERRED")

    # --- Tier 3c: custom memory-ish receivers (receiver-shape, lowest confidence) ---
    if a in _CUSTOM_WRITE_METHODS_STATIC and any(h in r for h in _CUSTOM_NAME_HINTS):
        return SinkMatch("custom", f"{receiver}.{attr}", Category.MEMORY_WRITE.value, "AMBIGUOUS")

    return None


__all__ = ["KEYED_WRITE_METHODS", "WRITE_METHODS", "SinkMatch", "classify_call"]
