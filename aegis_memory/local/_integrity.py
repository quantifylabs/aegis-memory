"""
HMAC-SHA256 memory integrity for Aegis Memory local mode.

Port of server/integrity.py — same logic, no server imports.
Uses a local signing key instead of project_id-scoped keys.
"""

from __future__ import annotations

import hashlib
import hmac


def compute_integrity_hash(
    content: str,
    agent_id: str | None,
    signing_key: str,
) -> str:
    """
    HMAC-SHA256 over canonical representation.

    Canonical: "local:{agent_id or ''}:{content}"
    """
    message = f"local:{agent_id or ''}:{content}"
    return hmac.new(
        signing_key.encode(), message.encode(), hashlib.sha256
    ).hexdigest()


def verify_integrity(
    content: str,
    agent_id: str | None,
    integrity_hash: str | None,
    signing_key: str,
) -> bool:
    """
    Verify stored integrity_hash matches recomputed hash.

    Returns False if no hash (legacy) or tampered.
    """
    if not integrity_hash:
        return False
    expected = compute_integrity_hash(content, agent_id, signing_key)
    return hmac.compare_digest(integrity_hash, expected)
