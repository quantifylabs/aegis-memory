"""
Aegis Scope Inference

Automatically determines memory visibility scope based on content patterns.
Kept simple and deterministic for v1.
"""


from scope_policy import content_may_enter_scope
from models import MemoryScope


class ScopeInference:
    """
    Pattern-based scope inference.

    Rules (in priority order):
    1. Explicit scope always wins
    2. Metadata tags (global, team, private, internal)
    3. Content keyword analysis
    4. Default to AGENT_PRIVATE (safest)

    Security note: inference reads the memory *content*, which is attacker-controlled. It must
    therefore never be able to *raise* privilege. Callers pass ``content_trust_level`` so an
    inferred ``global`` scope can be capped for untrusted content — otherwise text containing two
    keywords like "team" and "policy" would promote itself into the scope every agent reads.
    Explicit scopes are still checked, but by the authorization layer rather than here.
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
        content_trust_level: str | None = None,
    ) -> MemoryScope:
        """
        Infer memory scope from content and context.

        Args:
            content: The memory text
            explicit_scope: Optional explicit scope string
            agent_id: ID of the agent creating the memory
            metadata: Optional metadata dict with tags
            content_trust_level: Provenance of the content. When it is untrusted/un-vouched,
                an *inferred* (not explicit) global scope is capped to agent-private so
                attacker-controlled text cannot promote itself. Omitted means no capping,
                preserving behavior for callers that do not track provenance.

        Returns:
            Inferred MemoryScope enum value
        """
        metadata = metadata or {}
        inferred = cls._infer(content, explicit_scope, agent_id, metadata)

        # An explicit scope is the caller's request, not the content's influence — leave it for
        # the authorization layer to accept or reject. Only cap what the content itself inferred.
        if explicit_scope or content_trust_level is None:
            return inferred

        if inferred == MemoryScope.GLOBAL and not content_may_enter_scope(content_trust_level, "global"):
            return MemoryScope.AGENT_PRIVATE
        return inferred

    @classmethod
    def _infer(
        cls,
        content: str,
        explicit_scope: str | None,
        agent_id: str | None,
        metadata: dict,
    ) -> MemoryScope:
        """Original pattern-based inference, unchanged."""

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
