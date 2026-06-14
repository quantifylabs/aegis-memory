"""Channel 1 — user / support ticket → LangGraph store (sink: ``store.put``).

The customer's ticket body is untrusted text. Here it flows straight into a shared-memory
note via a LangGraph ``store.put(namespace, key, value)`` write, with no screening.
"""

from __future__ import annotations

from typing import Any

from .memory import SHARED_NS, SUMMARY_KEY


def ingest_ticket(store: Any, ticket: dict) -> None:
    # Untrusted customer text → shared memory (one variable hop: INFERRED).
    summary = f"Ticket from {ticket.get('customer', 'unknown')}: {ticket['body']}"
    store.put(SHARED_NS, SUMMARY_KEY, {"text": summary})
