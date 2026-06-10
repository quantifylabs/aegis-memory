"""
Aegis Agent Trust Hierarchy (v2.0.0)

Implements OWASP-recommended 4-tier trust model:
  - UNTRUSTED: External/unknown agents. Read-only global scope.
  - INTERNAL:  Default for authenticated agents. Full CRUD within project.
  - PRIVILEGED: Can access other agents' private memories, admin operations.
  - SYSTEM:    Reserved for Aegis internal operations (auto-vote, auto-reflect).

Trust level is determined by:
  1. API key metadata (trust_level field on ApiKey table)
  2. Agent binding (bound_agent_id on ApiKey)
  3. Default: INTERNAL
"""

from __future__ import annotations

# The accepted trust levels on a write. "unknown" is the conservative, un-vouched value
# that forces Stage-4 screening; it is not a long-term tier like the four OWASP levels.
VALID_TRUST_LEVELS = frozenset({"untrusted", "unknown", "internal", "privileged", "system"})

# Privilege ordering: lower rank == less trusted == MORE screening.
_TRUST_RANK = {"untrusted": 0, "unknown": 1, "internal": 2, "privileged": 3, "system": 4}


def resolve_trust_level(
    body_trust: str | None,
    principal_trust: str | None,
    *,
    enable_trust_levels: bool,
) -> str:
    """Resolve the effective trust level for a memory write.

    Precedence: declared ``body_trust`` -> ``principal_trust`` (from the API key) ->
    conservative default. Security invariant: this only ever makes screening *more*
    likely. A caller may voluntarily declare a lower (less-trusted) level to force more
    screening, but can never claim a higher level than its principal grants — that would
    weaken screening, which this function refuses to do.
    """
    principal = principal_trust or "internal"

    if body_trust:
        # Cap the declared level so it cannot exceed the principal's trust.
        if _TRUST_RANK.get(body_trust, 1) > _TRUST_RANK.get(principal, 2):
            return principal
        return body_trust

    if not enable_trust_levels:
        # Back-compat: preserve today's behavior when the feature is off.
        return principal

    # Feature on, nothing declared: an explicitly non-default principal level wins;
    # otherwise un-vouched content gets "unknown" so Stage 4 fires.
    if principal != "internal":
        return principal
    return "unknown"


class TrustPolicy:
    """Evaluate what operations an agent at a given trust level can perform."""

    @staticmethod
    def can_write(trust_level: str, scope: str) -> bool:
        """Check if trust level allows writing to given scope."""
        if trust_level == "untrusted":
            return False  # untrusted agents cannot write anything
        if trust_level == "internal":
            return scope in ("agent-private", "agent-shared")  # cannot write GLOBAL
        if trust_level in ("privileged", "system"):
            return True  # can write any scope
        return False

    @staticmethod
    def can_read_scope(trust_level: str, scope: str, is_owner: bool) -> bool:
        """Check if trust level allows reading given scope."""
        if trust_level == "untrusted":
            return scope == "global"  # read-only global
        if trust_level == "internal":
            return scope == "global" or is_owner  # global + own memories
        return True  # privileged and system can read everything

    @staticmethod
    def can_delete(trust_level: str, is_owner: bool) -> bool:
        """Only owners or privileged+ can delete memories."""
        return is_owner or trust_level in ("privileged", "system")

    @staticmethod
    def can_admin(trust_level: str) -> bool:
        """Only privileged/system trust levels can access /security/* endpoints."""
        return trust_level in ("privileged", "system")
