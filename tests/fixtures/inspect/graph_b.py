"""A SECOND, differently-written LangGraph agent — the anti-demo-tuning fixture.

Deliberately unlike the demo: class-based, a ``MemorySaver`` checkpointer plus a store
held on ``self.memory_store``, a different untrusted source (``request["payload"]``),
string concatenation instead of an f-string, and a ``global`` namespace. The general
LangGraph sink catalog must still find the ``.put`` write and its untrusted flow.
"""

from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph


class IngestionPipeline:
    def __init__(self, store) -> None:
        self.memory_store = store
        self.checkpointer = MemorySaver()

    def ingest(self, request: dict) -> None:
        payload = request["payload"]
        note = "customer said: " + payload
        # Different shape, same sink family: a store write of untrusted text.
        self.memory_store.put(("global", "notes"), "note-1", {"note": note})

    def checkpoint(self, config: dict, data: dict) -> None:
        # A checkpointer write — also a known LangGraph memory sink.
        self.checkpointer.put(config, data, {}, {})
