"""
HMAC-SHA256 Memory Integrity (v2.0.0)

Signs memory content at storage time and verifies on retrieval/audit.
Provides tamper detection for stored memories.
"""

from __future__ import annotations

import hashlib
import hmac


def compute_integrity_hash(
    content: str,
    agent_id: str | None,
    project_id: str,
    signing_key: str,
) -> str:
    """
    HMAC-SHA256 over canonical representation of memory content.

    Canonical message format: "{project_id}:{agent_id or ''}:{content}"
    This ensures the hash is tied to the project and agent, preventing
    cross-project or cross-agent hash reuse.
    """
    message = f"{project_id}:{agent_id or ''}:{content}"
    return hmac.new(
        signing_key.encode(), message.encode(), hashlib.sha256
    ).hexdigest()


def verify_integrity(
    memory,
    signing_key: str,
) -> bool:
    """
    Verify stored integrity_hash matches recomputed hash.
    Returns False if memory has been tampered with or has no hash (legacy row).
    Uses hmac.compare_digest for timing-safe comparison.
    """
    if not memory.integrity_hash:
        return False  # legacy row without hash
    expected = compute_integrity_hash(
        memory.content, memory.agent_id, memory.project_id, signing_key
    )
    return hmac.compare_digest(memory.integrity_hash, expected)
