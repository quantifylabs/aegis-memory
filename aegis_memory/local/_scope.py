"""
Scope inference for Aegis Memory local mode.

Port of server/scope_inference.py — same logic, no server imports.
"""

from __future__ import annotations

from enum import Enum


class MemoryScope(str, Enum):
    AGENT_PRIVATE = "agent-private"
    AGENT_SHARED = "agent-shared"
    GLOBAL = "global"


# Keywords suggesting global/team visibility
GLOBAL_KEYWORDS = frozenset([
    "project", "team", "deadline", "everyone", "all agents",
    "system", "company", "organization", "shared", "announcement",
    "policy", "guideline", "requirement", "standard",
])

# Keywords suggesting private/internal
PRIVATE_KEYWORDS = frozenset([
    "thinking", "internal", "considering", "my analysis",
    "draft", "scratch", "temporary", "private", "personal",
    "todo", "note to self", "reminder",
])


def infer_scope(
    content: str,
    explicit_scope: str | None = None,
    agent_id: str | None = None,
    metadata: dict | None = None,
) -> str:
    """
    Infer memory scope from content and context.

    Returns scope string value (e.g. "agent-private").
    """
    metadata = metadata or {}

    # 1. Explicit scope takes precedence
    if explicit_scope:
        try:
            return MemoryScope(explicit_scope).value
        except ValueError:
            pass

    # 2. Check metadata tags
    tags = metadata.get("tags", [])
    if isinstance(tags, str):
        tags = [tags]

    tag_set = frozenset(str(t).lower() for t in tags if t)

    if tag_set & {"global", "team", "shared", "public"}:
        return MemoryScope.GLOBAL.value

    if tag_set & {"private", "internal", "personal"}:
        return MemoryScope.AGENT_PRIVATE.value

    # 3. Content analysis
    content_lower = content.lower()

    global_score = sum(1 for kw in GLOBAL_KEYWORDS if kw in content_lower)
    private_score = sum(1 for kw in PRIVATE_KEYWORDS if kw in content_lower)

    if global_score >= 2 and global_score > private_score:
        return MemoryScope.GLOBAL.value

    if private_score > global_score:
        return MemoryScope.AGENT_PRIVATE.value

    # 4. Check for shared_with_agents in metadata
    shared_agents = metadata.get("shared_with_agents", [])
    if agent_id and shared_agents:
        return MemoryScope.AGENT_SHARED.value

    # 5. Safe default
    return MemoryScope.AGENT_PRIVATE.value
