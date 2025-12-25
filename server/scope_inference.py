"""
Aegis Scope Inference

Automatically determines memory visibility scope based on content patterns.
Kept simple and deterministic for v1.
"""


from models import MemoryScope


class ScopeInference:
    """
    Pattern-based scope inference.

    Rules (in priority order):
    1. Explicit scope always wins
    2. Metadata tags (global, team, private, internal)
    3. Content keyword analysis
    4. Default to AGENT_PRIVATE (safest)
    """

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

    @classmethod
    def infer_scope(
        cls,
        content: str,
        explicit_scope: str | None = None,
        agent_id: str | None = None,
        metadata: dict | None = None,
    ) -> MemoryScope:
        """
        Infer memory scope from content and context.

        Args:
            content: The memory text
            explicit_scope: Optional explicit scope string
            agent_id: ID of the agent creating the memory
            metadata: Optional metadata dict with tags

        Returns:
            Inferred MemoryScope enum value
        """
        metadata = metadata or {}

        # 1. Explicit scope takes precedence
        if explicit_scope:
            try:
                return MemoryScope(explicit_scope)
            except ValueError:
                pass  # Invalid scope string, fall through to heuristics

        # 2. Check metadata tags
        tags = metadata.get("tags", [])
        if isinstance(tags, str):
            tags = [tags]

        tag_set = frozenset(str(t).lower() for t in tags if t)

        if tag_set & {"global", "team", "shared", "public"}:
            return MemoryScope.GLOBAL

        if tag_set & {"private", "internal", "personal"}:
            return MemoryScope.AGENT_PRIVATE

        # 3. Content analysis
        content_lower = content.lower()

        global_score = sum(1 for kw in cls.GLOBAL_KEYWORDS if kw in content_lower)
        private_score = sum(1 for kw in cls.PRIVATE_KEYWORDS if kw in content_lower)

        # Need clear signal for global (threshold of 2)
        if global_score >= 2 and global_score > private_score:
            return MemoryScope.GLOBAL

        if private_score > global_score:
            return MemoryScope.AGENT_PRIVATE

        # 4. Check for shared_with_agents in metadata
        shared_agents = metadata.get("shared_with_agents", [])
        if agent_id and shared_agents:
            return MemoryScope.AGENT_SHARED

        # 5. Safe default
        return MemoryScope.AGENT_PRIVATE
