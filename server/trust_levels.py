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
