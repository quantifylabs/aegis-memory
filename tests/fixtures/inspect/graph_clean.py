"""A clean fixture: a memory write whose value is an internal constant, not untrusted
input. Should produce a structural memory-write finding but NO critical untrusted flow.
"""

from __future__ import annotations


def record_status(store) -> None:
    status = {"text": "system initialized"}
    store.put(("agent", "status"), "boot", status)
