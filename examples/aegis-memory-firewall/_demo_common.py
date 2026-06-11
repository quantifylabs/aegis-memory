"""Shared runtime helpers for the staged-attack demo.

The "with Aegis" guard calls the *real* ``ContentSecurityScanner`` (the benchmark-validated
pipeline) — no hardcoded verdicts, no server, no network. Everything here is offline and
deterministic.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from langgraph.store.memory import InMemoryStore

# Reuse the real scanner via the inspect bridge (Stages 1-3, deterministic, offline).
from aegis_memory.inspect._scanner_bridge import ContentAction, get_scanner

from agent.memory import SHARED_NS, SUMMARY_KEY, new_store  # noqa: F401  (re-exported)

HERE = Path(__file__).resolve().parent


def load_text(rel: str) -> str:
    return (HERE / rel).read_text(encoding="utf-8")


def load_json(rel: str) -> dict[str, Any]:
    return json.loads((HERE / rel).read_text(encoding="utf-8"))


def detection_types(verdict: Any) -> list[str]:
    """Concrete detection types the scanner fired on (precise, not just flags)."""
    seen: list[str] = []
    for det in verdict.detections:
        name = det.detection_type.value
        if name not in seen:
            seen.append(name)
    return seen


class AegisGuardedStore:
    """Wraps a store; screens every ``put`` value through the real Aegis scanner.

    A write whose content is REJECT-ed never reaches memory. This is the runtime "write gate"
    the inspector's findings point at (SSOT §4.3).
    """

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self._scanner = get_scanner()
        self.blocked: list[dict[str, Any]] = []

    def put(self, namespace, key, value, *args, **kwargs):
        text = value.get("text", "") if isinstance(value, dict) else str(value)
        verdict = self._scanner.scan(text)
        if not verdict.allowed or verdict.action == ContentAction.REJECT:
            detected = detection_types(verdict)
            self.blocked.append({"key": key, "detections": detected, "action": verdict.action.value})
            print(
                f"  [AEGIS] write to '{key}' REJECTED by ContentSecurityScanner "
                f"(action={verdict.action.value}, detected={detected or 'none'})"
            )
            return None
        return self._inner.put(namespace, key, value, *args, **kwargs)

    def get(self, *args, **kwargs):
        return self._inner.get(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._inner, name)


def plant_via_channel(store: Any, channel: str, content: str) -> None:
    """Plant untrusted channel content into shared memory (the malicious *write*).

    This mirrors what ``agent/ingest_web.py`` / ``ingest_email.py`` do at the sink: an
    untrusted body written straight into the shared note. The user never typed this.
    """
    print(f"[plant] ingesting untrusted {channel} content into shared memory...")
    store.put(SHARED_NS, SUMMARY_KEY, {"text": content})


def print_decision(result: dict[str, Any], amount: float) -> None:
    decision = result.get("decision", "?")
    print(f"\n  Refund request: ${amount:,.2f}")
    print(f"  Decision: {decision}")
    print(f"  Reason:   {result.get('reason', '')}")
