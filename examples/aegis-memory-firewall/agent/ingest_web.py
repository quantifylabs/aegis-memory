"""Channel 4 — web fetch → LangGraph store (sink: ``store.put``).

Content fetched from the open web is untrusted. ``requests`` is injected so the module never
touches the network at import/run time; ``aegis inspect`` reads the ``requests.get(url).text``
shape statically and flags the flow into ``store.put``.
"""

from __future__ import annotations

from typing import Any

from .memory import SHARED_NS, SUMMARY_KEY


def ingest_web_page(store: Any, requests: Any, url: str) -> None:
    # Web egress → shared memory (one hop through ``fetched``: INFERRED).
    fetched = requests.get(url).text
    store.put(SHARED_NS, SUMMARY_KEY, {"text": fetched})
