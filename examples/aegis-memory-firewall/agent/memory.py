"""The shared store the agent's channels write to and the decision step reads from.

A single LangGraph ``InMemoryStore`` stands in for the production memory layer. Every channel
writes into the same shared namespace, which is exactly what lets a poisoned write from one
channel steer a decision driven by another.
"""

from __future__ import annotations

from typing import Any

from langgraph.store.memory import InMemoryStore

# One shared namespace every channel writes into (the cross-channel blast radius).
SHARED_NS = ("shared", "knowledge")
SUMMARY_KEY = "latest_note"


def new_store() -> InMemoryStore:
    return InMemoryStore()


def read_note(store: Any) -> str:
    """Best-effort read of the latest shared note as text."""
    item = store.get(SHARED_NS, SUMMARY_KEY)
    if item is None:
        return ""
    value = getattr(item, "value", item)
    return (value or {}).get("text", "") if isinstance(value, dict) else str(value)
