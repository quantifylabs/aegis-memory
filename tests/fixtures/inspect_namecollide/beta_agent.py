"""Name-collision fixture — agent BETA.

Mirror of ``alpha_agent.py`` with the *same* helper name ``_format_for_storage`` but its *own*
untrusted source. The resolver must cite this file for this sink, proving no cross-file contamination.
"""

from __future__ import annotations

import httpx


class BetaAgent:
    def __init__(self, memory) -> None:
        self.memory = memory

    def hunt(self, url: str) -> None:
        self.memory.store_intelligence(content=self._format_for_storage(url))

    @staticmethod
    def _format_for_storage(url: str) -> str:
        raw = httpx.get(url)  # untrusted beta source
        return f"beta intel: {raw}"
