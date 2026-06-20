"""Cross-file taint fixture — the durable, cross-agent memory writer.

Mirrors the real ``client.add(scope="agent-shared", shared_with_agents=[...])`` sink: the receiver
is named ``client`` (no memory-ish name hint), and the write is recognized purely by the call's
API signature (``scope=`` / ``shared_with_agents=``). The written ``content`` is a *parameter*, so
its trust can only be decided by following the caller across the file boundary (see ``hunter.py``).
"""

from __future__ import annotations


class MemoryClient:
    def __init__(self, client) -> None:
        self.client = client

    def store_intelligence(self, content) -> None:
        # Durable cross-agent write. ``content`` originates two hops up, in another file.
        self.client.add(
            content=content,
            scope="agent-shared",
            shared_with_agents=["peer-agent"],
        )
