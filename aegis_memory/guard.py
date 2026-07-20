"""``aegis_memory.guard`` — the runtime memory write-gate.

`aegis inspect` finds the call sites where untrusted content flows into durable memory and tells
you to screen the write. This module is the screen. It is the one place every multi-agent topology
funnels through: whatever the agents' behaviour or organisation (reactive, cooperative,
hierarchical, swarm, competitive, …), the invariant is the same — *something becomes durable
memory and a later/other step reads it back and acts*. Gate the write and the topology stops
mattering.

It adds **no detection logic of its own**. It composes the one benchmark-validated
``ContentSecurityScanner`` (via ``aegis_memory.inspect._scanner_bridge.get_scanner`` — the same
engine the server runs, pre-policied to reject injection/secrets and flag PII) with a small,
scope-aware policy.

Two entry points::

    from aegis_memory import guard

    # 1. screen a single value before you persist it
    verdict = guard.write(content, trust_level="untrusted", scope="agent-shared", on_reject="return")
    if verdict.allowed:
        store.put(ns, key, {"text": verdict.content})

    # 2. wrap any store so every write is screened automatically
    store = guard.protect(my_store, scope="agent-shared")
    store.put(ns, key, {"text": content})   # poisoned writes never reach memory

Trust semantics (read this — it differs from the server's ``TrustPolicy``):
``trust_level`` here labels the **content's provenance** (where the data came from), not the
*agent's* identity. The server's ``server/trust_levels.py::TrustPolicy.can_write`` governs which
*agent* may call the API; this gate governs whether a piece of *content* may become memory. So the
policy is: always scan; block injection/secrets; and additionally refuse to let
``untrusted``/``unknown`` content land in ``global`` scope (every agent reads global — promoting
untrusted data there needs a privileged path, not a raw write). Screened-clean content is allowed
into ``agent-private`` / ``agent-shared`` — screening *before* sharing is the entire point.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from .inspect._scanner_bridge import ContentAction, get_scanner
from .inspect.sinks import KEYED_WRITE_METHODS, WRITE_METHODS
from .scope_policy import UNTRUSTED_CONTENT_LEVELS, content_may_enter_scope

# Keyword arg names that commonly carry the written value (mirrors analyzer._VALUE_KWARGS).
_VALUE_KWARGS = ("value", "content", "data", "text", "texts", "documents", "memory", "messages", "item")

# Content provenance levels that must never be written straight to global scope.
# Re-exported from scope_policy so the server and the guard share one definition.
_UNTRUSTED_LEVELS = UNTRUSTED_CONTENT_LEVELS


@dataclass
class WriteVerdict:
    """The result of screening one write. ``content`` is the (possibly redacted) text to persist."""

    allowed: bool
    action: str  # "allow" | "flag" | "redact" | "reject"
    content: str
    trust_level: str
    scope: str
    reason: str
    detections: list[dict] = field(default_factory=list)  # [{"type","confidence"}]
    flags: list[str] = field(default_factory=list)


class WriteBlocked(Exception):
    """Raised by ``guard.write`` / a ``raise``-mode guarded store when a write is rejected."""

    def __init__(self, verdict: WriteVerdict) -> None:
        super().__init__(verdict.reason)
        self.verdict = verdict


def write(
    content: str,
    *,
    trust_level: str = "untrusted",
    scope: str = "agent-private",
    require_classifier: bool = False,
    metadata: dict | None = None,
    on_reject: str = "raise",
) -> WriteVerdict:
    """Screen ``content`` against the real scanner + the scope policy and return a verdict.

    ``on_reject="raise"`` (default, fail-closed) raises :class:`WriteBlocked` when the write is
    not allowed; ``on_reject="return"`` always returns the verdict (``allowed=False`` on a block).

    ``require_classifier`` is accepted for parity with the inspect fix-string; the offline scanner
    runs Stages 1-3 deterministically (no model), so it is a documented no-op unless a Stage-4
    classifier has been configured on the shared scanner.
    """
    tl = (trust_level or "untrusted").lower()
    sc = (scope or "agent-private").lower()

    sv = get_scanner().scan(content, metadata)
    scan_blocked = (not sv.allowed) or sv.action == ContentAction.REJECT
    # untrusted/unknown content may never be written straight to global scope.
    # Shared with the server via aegis_memory.scope_policy so the two cannot drift.
    scope_blocked = not content_may_enter_scope(tl, sc)
    allowed = not (scan_blocked or scope_blocked)

    dets = [
        {"type": d.detection_type.value, "confidence": round(float(d.confidence), 2)}
        for d in sv.detections
    ]
    flags = list(sv.flags) + (["scope_denied"] if scope_blocked else [])
    action = "reject" if (scan_blocked or scope_blocked) else sv.action.value

    verdict = WriteVerdict(
        allowed=allowed,
        action=action,
        content=sv.content,
        trust_level=tl,
        scope=sc,
        reason=_reason(dets, scan_blocked, scope_blocked, tl, sc),
        detections=dets,
        flags=flags,
    )
    if not allowed and on_reject == "raise":
        raise WriteBlocked(verdict)
    return verdict


def protect(
    store: Any,
    *,
    value_key: str = "text",
    trust_level: str = "untrusted",
    scope: str = "agent-shared",
    on_reject: str = "drop",
) -> GuardedStore:
    """Wrap any store so every write method is screened through :func:`write` first.

    Framework-agnostic: it intercepts the same write idioms ``aegis inspect`` catalogs
    (``put``/``add``/``save``/``add_texts`` … see ``inspect.sinks.WRITE_METHODS``), sync or async.
    ``on_reject="drop"`` (default) silently drops a rejected write and records it on ``.blocked``;
    ``on_reject="raise"`` raises :class:`WriteBlocked`.
    """
    return GuardedStore(
        store, value_key=value_key, trust_level=trust_level, scope=scope, on_reject=on_reject
    )


class GuardedStore:
    """Transparent proxy that screens every catalogued write before it reaches the inner store."""

    def __init__(
        self,
        inner: Any,
        *,
        value_key: str = "text",
        trust_level: str = "untrusted",
        scope: str = "agent-shared",
        on_reject: str = "drop",
    ) -> None:
        # Set via __dict__ so attribute access never round-trips through __getattr__ during init.
        self.__dict__["_inner"] = inner
        self.__dict__["_value_key"] = value_key
        self.__dict__["_trust_level"] = trust_level
        self.__dict__["_scope"] = scope
        self.__dict__["_on_reject"] = on_reject
        self.__dict__["blocked"] = []

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self.__dict__["_inner"], name)
        if name in WRITE_METHODS and callable(attr):
            return self._wrap(name, attr)
        return attr

    def _wrap(self, name: str, method: Any) -> Any:
        if asyncio.iscoroutinefunction(method):
            async def awrapped(*args: Any, **kwargs: Any) -> Any:
                if not self._screen(name, args, kwargs):
                    return None
                return await method(*args, **kwargs)

            return awrapped

        def wrapped(*args: Any, **kwargs: Any) -> Any:
            if not self._screen(name, args, kwargs):
                return None
            return method(*args, **kwargs)

        return wrapped

    def _screen(self, name: str, args: tuple, kwargs: dict) -> bool:
        """Return True if the write may proceed; record + drop/raise otherwise."""
        text = _to_text(_candidate_value(name, args, kwargs), self.__dict__["_value_key"])
        verdict = write(
            text,
            trust_level=self.__dict__["_trust_level"],
            scope=self.__dict__["_scope"],
            on_reject="return",
        )
        if verdict.allowed:
            return True
        self.__dict__["blocked"].append(
            {
                "method": name,
                "action": verdict.action,
                "detections": [d["type"] for d in verdict.detections],
                "flags": verdict.flags,
                "reason": verdict.reason,
            }
        )
        if self.__dict__["_on_reject"] == "raise":
            raise WriteBlocked(verdict)
        return False


# --- helpers -----------------------------------------------------------------------


def _candidate_value(method: str, args: tuple, kwargs: dict) -> Any:
    """Best-effort extraction of the written value from a wrapped call's arguments."""
    for k in _VALUE_KWARGS:
        if k in kwargs:
            return kwargs[k]
    if method in KEYED_WRITE_METHODS and len(args) >= 3:  # put(namespace, key, value)
        return args[2]
    if args:
        return args[0]
    return None


def _to_text(value: Any, value_key: str) -> str:
    """Coerce a written value into the text to scan (dict value_key, list join, or str)."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        if value_key in value:
            return str(value[value_key])
        return " ".join(str(v) for v in value.values() if isinstance(v, (str, int, float)))
    if isinstance(value, (list, tuple)):
        return "\n".join(_to_text(v, value_key) for v in value)
    return str(value)


def _reason(dets: list[dict], scan_blocked: bool, scope_blocked: bool, tl: str, sc: str) -> str:
    if scan_blocked:
        types = ", ".join(dict.fromkeys(d["type"] for d in dets)) or "policy violation"
        return f"content rejected by scanner ({types})"
    if scope_blocked:
        return f"{tl} content may not be written to '{sc}' scope (requires a privileged promotion)"
    return "allowed"


__all__ = ["GuardedStore", "WriteBlocked", "WriteVerdict", "protect", "write"]
