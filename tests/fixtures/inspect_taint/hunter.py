"""Cross-file taint fixture — the untrusted source side (mirrors ``paper_hunter``).

Untrusted arXiv-style web content is fetched, formatted by a helper, and handed to
``MemoryClient.store_intelligence`` (which writes it durably in ``client.py``). This exercises
both interprocedural directions: the local ``store_intelligence`` sink resolves through the helper
call same-scope, and the cross-file ``client.add`` sink resolves by ascending into this caller.
"""

from __future__ import annotations

import httpx

from client import MemoryClient


class PaperHunter:
    def __init__(self, client) -> None:
        self.memory = MemoryClient(client)

    def hunt(self, url: str) -> None:
        raw = httpx.get(url)  # untrusted external web content (arXiv feed)
        content = self._format_for_storage(raw)
        self.memory.store_intelligence(content=content)  # sink #1 (local, via helper)

    def _format_for_storage(self, raw) -> str:
        return f"latest papers: {raw}"
