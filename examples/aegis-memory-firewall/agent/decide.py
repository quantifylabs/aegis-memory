"""The privileged step: reads shared memory and makes the refund call.

This is downstream of every channel. It does not know (and cannot tell) that a note in
memory came from an untrusted web page or email rather than a vetted internal policy — which
is precisely why a poisoned *write* can steer it.
"""

from __future__ import annotations

from typing import Any

from .memory import read_note

# Refunds at or below this are routine; above it requires manual review by default.
REVIEW_THRESHOLD = 500.0


def decide_refund(store: Any, amount: float, threshold: float = REVIEW_THRESHOLD) -> dict:
    memory_text = read_note(store)
    # Collapse whitespace so a policy phrase that wraps across lines still matches.
    memo = " ".join(memory_text.lower().split())
    auto_approve = (
        "approved automatically" in memo or "auto-approve" in memo or "auto approve" in memo
    )
    if amount > threshold and auto_approve:
        return {
            "decision": "APPROVED",
            "reason": "stored policy note says high-value refunds are auto-approved",
        }
    if amount > threshold:
        return {"decision": "DENIED", "reason": "high-value refund requires manual review"}
    return {"decision": "APPROVED", "reason": "low-value refund within policy"}
