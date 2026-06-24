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
    framework: str  # "langgraph" | "vectordb" | "aegis" | "custom" | "mem0" | "embedchain"
    call: str  # canonical call label, e.g. "store.put"
    category: str  # Category value (structural)
    base_confidence: str  # "EXTRACTED" baseline trust we can place in the *sink* match


@dataclass(frozen=True)
class BindingInfo:
    """A receiver resolved to a memory library via its **constructor** (Batch B, ``bindings.py``).

    This is the precision-first alternative to receiver-name guessing: ``methods`` are the write-method
    names authorized on this *bound* receiver, and ``category``/``confidence`` shape the resulting
    :class:`SinkMatch`. A ``BindingInfo`` only ever comes from resolving ``m = Memory()`` /
    ``self.warm = WarmTier()`` to a known/heuristic memory constructor — never from a substring on the
    receiver variable's name (that was the old false-positive source)."""

    library: str  # "mem0" | "embedchain" | "custom"
    methods: frozenset[str]  # write methods authorized on this bound receiver
    category: str  # Category value for the emitted sink
    confidence: str  # base_confidence for the emitted SinkMatch


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
# conservative to avoid local-container false positives. ``update`` is in the runtime contract
# because Batch B emits ``update`` sinks on constructor-bound receivers and recommends
# ``guard.protect`` for them — so ``GuardedStore`` must actually intercept ``.update(...)`` at
# runtime, or the secondary fix would screen nothing.
_CUSTOM_WRITE_METHODS = (
    "put", "add", "save", "write", "append", "set", "store", "remember", "insert", "update",
)

# ``put(namespace, key, value)`` style — the written value is the 3rd positional arg.
KEYED_WRITE_METHODS: frozenset[str] = frozenset(_LANGGRAPH_WRITE_METHODS)

# Every instance-method name that constitutes a durable memory write (runtime-guard contract).
WRITE_METHODS: frozenset[str] = frozenset(
    _LANGGRAPH_WRITE_METHODS + _VECTORDB_METHODS + _CUSTOM_WRITE_METHODS
)


def _norm(s: str | None) -> str:
    return (s or "").lower()


def _bound_label(default: str, binding: BindingInfo | None) -> str:
    """Label upgrade (Batch B Fix 3): when a generic-tier sink's receiver also binds to a library,
    attribute it to that library (``custom``/``vectordb`` -> ``mem0``/``embedchain``). The precise
    ``aegis``/``langgraph`` tiers are never relabeled."""
    return binding.library if binding is not None else default


def classify_call(
    *,
    attr: str | None,
    func: str | None,
    receiver: str | None,
    keywords: Sequence[str] = (),
    binding: BindingInfo | None = None,
) -> SinkMatch | None:
    """Return a :class:`SinkMatch` if this call is a known memory-write sink, else None.

    ``attr`` is the method name for ``obj.method(...)`` calls; ``func`` is the function name for
    bare ``func(...)`` calls; ``receiver`` is the (possibly dotted) root-object name for method
    calls; ``keywords`` are the call's keyword-argument names (used by the API-signature tier).
    ``binding`` (Batch B) is a constructor-resolved receiver->library binding: it adds a final tier
    that recovers aliased receivers (``m.add``/``self.warm.put``) the name-hint tiers miss, and
    upgrades the label on the generic tiers. It is supplied only when the receiver provably resolves
    to a memory constructor — never from a receiver-name guess.
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

    # The aegis guard screening calls themselves — ``guard.write(...)`` / ``guard.protect(...)`` —
    # are the *fix* inspect recommends, not a durable write: ``guard.write`` returns a verdict and
    # persists nothing; ``guard.protect`` wraps a store. Excluding the ``guard`` receiver keeps a
    # rescan of fixed code from minting a bogus screened sink (and, with ``scope=``, an overbroad
    # shared-access finding) for the very call that fixed it. The wrapped ``store.put(...)`` writes
    # are still matched and screened sink-tied (see taint.protected_receivers).
    if a in ("write", "protect") and "guard" in r.split("."):
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
        return SinkMatch(_bound_label("vectordb", binding), f"{receiver}.{attr}",
                         Category.VECTOR_DB_WRITE.value, "INFERRED")

    # --- Tier 3c: custom memory-ish receivers (receiver-shape, lowest confidence) ---
    if a in _CUSTOM_WRITE_METHODS_STATIC and any(h in r for h in _CUSTOM_NAME_HINTS):
        return SinkMatch(_bound_label("custom", binding), f"{receiver}.{attr}",
                         Category.MEMORY_WRITE.value, "AMBIGUOUS")

    # --- Tier 3d (Batch B): constructor-bound receiver — resolved to a memory handle ---
    # Recovers aliased receivers the name-hint tiers miss (``m.add``/``app.add``/``manager.store``/
    # ``self.warm.put``/``router.write``/``self.backend.save``) and the bound-only ``store.update``.
    # Fires ONLY when ``binding`` resolved the receiver to a memory constructor — never on a name.
    if binding is not None and a in binding.methods:
        return SinkMatch(binding.library, f"{receiver}.{attr}", binding.category, binding.confidence)

    return None


__all__ = ["KEYED_WRITE_METHODS", "WRITE_METHODS", "BindingInfo", "SinkMatch", "classify_call"]
