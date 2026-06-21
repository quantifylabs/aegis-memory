"""Name-collision fixture — agent ALPHA.

Has its *own* ``_format_for_storage`` helper, fed by its *own* untrusted source (an HTTP fetch),
and writes via ``store_intelligence``. ``beta_agent.py`` defines a same-named helper. The taint
resolver must attribute this sink's source to *this* file — never borrow beta's line numbers.
"""

from __future__ import annotations

import httpx


class AlphaAgent:
    def __init__(self, memory) -> None:
        self.memory = memory

    def hunt(self, url: str) -> None:
        self.memory.store_intelligence(content=self._format_for_storage(url))

    @staticmethod
    def _format_for_storage(url: str) -> str:
        raw = httpx.get(url)  # untrusted alpha source
        return f"alpha intel: {raw}"
