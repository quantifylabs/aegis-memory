"""A screened fixture: untrusted ticket text, but the value is scanned by a guard before
the write. The flow finding should be downgraded (screened) rather than critical.
"""

from __future__ import annotations


def summarize(store, ticket, scanner) -> None:
    summary = ticket["body"]
    verdict = scanner.scan(summary)
    if verdict.allowed:
        store.put(("agent", "summaries"), "s1", {"text": summary})
