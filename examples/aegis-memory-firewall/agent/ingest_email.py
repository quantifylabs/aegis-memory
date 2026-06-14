"""Channel 5 — email body → LangGraph checkpointer (sink: ``checkpointer.put``).

An inbound email body is untrusted. It is persisted through a LangGraph checkpointer
``put(config, key, value)`` write — a different sink family from the store writes above.
"""

from __future__ import annotations

from typing import Any


def ingest_email(checkpointer: Any, cfg: dict, email: Any) -> None:
    # Email body → checkpointer state (direct ``.body``: EXTRACTED).
    note = {"note": email.body}
    checkpointer.put(cfg, "email_note", note)
