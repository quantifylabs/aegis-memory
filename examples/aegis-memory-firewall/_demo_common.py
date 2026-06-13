"""Shared runtime helpers for the staged-attack demo.

The "with Aegis" guard calls the *real* ``ContentSecurityScanner`` (the benchmark-validated
pipeline) — no hardcoded verdicts, no server, no network. Everything here is offline and
deterministic.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from langgraph.store.memory import InMemoryStore

# The shipped runtime write-gate — the same API `aegis inspect` tells you to paste.
from aegis_memory import guard
from aegis_memory.inspect.sinks import KEYED_WRITE_METHODS

from agent.memory import SHARED_NS, SUMMARY_KEY, new_store  # noqa: F401  (re-exported)

HERE = Path(__file__).resolve().parent


def load_text(rel: str) -> str:
    return (HERE / rel).read_text(encoding="utf-8")


def load_json(rel: str) -> dict[str, Any]:
    return json.loads((HERE / rel).read_text(encoding="utf-8"))


class AegisGuardedStore(guard.GuardedStore):
    """The runtime write gate the inspector's findings point at — now the **shipped** API.

    This is a thin shim over ``aegis_memory.guard.protect``: it screens every catalogued write
    through the real ``ContentSecurityScanner`` (a REJECT never reaches memory) and adds the
    demo's friendly ``[AEGIS]`` line. Same screening as production, no bespoke code.
    """

    def __init__(self, inner: Any) -> None:
        super().__init__(inner, scope="agent-shared", on_reject="drop")

    def _screen(self, name, args, kwargs):
        ok = super()._screen(name, args, kwargs)
        if not ok:
            rec = self.__dict__["blocked"][-1]
            key = args[1] if (name in KEYED_WRITE_METHODS and len(args) >= 2) else name
            print(
                f"  [AEGIS] write to '{key}' REJECTED by ContentSecurityScanner "
                f"(action={rec['action']}, detected={rec['detections'] or 'none'})"
            )
        return ok


def plant_via_channel(store: Any, channel: str, content: str) -> None:
    """Plant untrusted channel content into shared memory (the malicious *write*).

    This mirrors what ``agent/ingest_web.py`` / ``ingest_email.py`` do at the sink: an
    untrusted body written straight into the shared note. The user never typed this.
    """
    print(f"[plant] ingesting untrusted {channel} content into shared memory...")
    store.put(SHARED_NS, SUMMARY_KEY, {"text": content})


def print_decision(result: dict[str, Any], amount: float) -> None:
    decision = result.get("decision", "?")
    print(f"\n  Refund request: ${amount:,.2f}")
    print(f"  Decision: {decision}")
    print(f"  Reason:   {result.get('reason', '')}")
