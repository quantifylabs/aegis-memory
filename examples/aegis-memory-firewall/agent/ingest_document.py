"""Channel 2 — retrieved document → vector store (sink: ``vectorstore.add_documents``).

A document pulled from a knowledge base is untrusted: its ``.text`` lands verbatim in the
vector index. ``Document`` and ``vectorstore`` are injected so this module stays import-light
and offline; the call *shape* is what ``aegis inspect`` matches.
"""

from __future__ import annotations

from typing import Any


def ingest_document(vectorstore: Any, Document: Any, doc: Any) -> None:
    # The retrieved document body is untrusted (direct ``.text``: EXTRACTED).
    vectorstore.add_documents([Document(page_content=doc.text, metadata={"src": "kb"})])
