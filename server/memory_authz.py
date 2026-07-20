"""Authorization for memory operations.

One place where every memory route decides who may read, write, and delete what. Before this
module the security primitives existed but were never called: ``enforce_agent_binding`` had zero
router call sites, and ``TrustPolicy.can_write`` / ``can_read_scope`` / ``can_delete`` had zero
production call sites at all. The routes derived the requesting agent from the request body, so
any holder of a project API key could read any agent's ``agent-private`` memories.

Two distinct notions of trust meet here and must not be conflated:

- **Principal trust** (``AuthContext.trust_level``) — how much we trust the *caller*. Governs
  whether this API key may write to a scope at all. Evaluated by ``TrustPolicy``.
- **Content provenance** (the memory's resolved ``trust_level``) — where the *data* came from.
  Governs whether the content may become globally readable. Evaluated by
  ``aegis_memory.scope_policy``, shared with the offline ``aegis_memory.guard`` so the two
  enforcement paths cannot drift.

Both apply on a write. Content provenance is the ceiling, principal trust is the floor.

**Agent identity and unbound keys.** An API key may carry a ``bound_agent_id``. When it does, that
identity is authoritative and a request cannot claim to be a different agent. When it does not,
the key represents the whole application: it may act as any agent in its project, which is the
documented posture for a project-scoped key. Agent-level isolation is therefore available to
callers who opt into bound keys; it is not something an unbound key can express, because an
unbound key has no agent identity to check against.
"""

from __future__ import annotations

from aegis_memory.scope_policy import content_may_enter_scope, scope_denial_reason
from api.dependencies.auth import AuthContext, enforce_agent_binding
from fastapi import HTTPException, status
from trust_levels import TrustPolicy


def effective_agent_id(auth: AuthContext, requested_agent_id: str | None) -> str | None:
    """Resolve the agent identity a request acts as, rejecting spoofed claims.

    A bound key pins the identity: a request may restate its own bound agent id or omit it, but
    naming a different agent is a spoofing attempt and raises 403. An unbound key may act as any
    agent, so the requested value passes through unchanged.
    """
    enforce_agent_binding(auth, requested_agent_id)
    if auth.bound_agent_id:
        return auth.bound_agent_id
    return requested_agent_id


def authorize_write(
    auth: AuthContext,
    *,
    agent_id: str | None,
    scope: str,
    content_trust_level: str,
    enforce_principal_trust: bool,
) -> None:
    """Authorize a memory write. Raises 403 when policy forbids it.

    The content-provenance ceiling is always enforced — it is the rule that stops one poisoned
    write from becoming every agent's instruction, and it matches ``guard.write()`` exactly.

    The principal-trust check is gated on ``enforce_principal_trust`` (the ``ENABLE_TRUST_LEVELS``
    setting) because it is a genuine behavior change: under ``TrustPolicy`` an ``internal``
    principal may not write ``global`` at all, so enabling it requires a privileged key for
    legitimate global writes.
    """
    enforce_agent_binding(auth, agent_id)

    if not content_may_enter_scope(content_trust_level, scope):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=scope_denial_reason(content_trust_level, scope),
        )

    if enforce_principal_trust and not TrustPolicy.can_write(auth.trust_level, scope):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Trust level '{auth.trust_level}' may not write to '{scope}' scope. "
                f"Writing to 'global' requires a privileged or system key."
            ),
        )


def authorize_read(auth: AuthContext, memory, *, enforce_principal_trust: bool) -> None:
    """Authorize reading a specific memory. Raises 403 when policy forbids it.

    Only meaningful for bound keys; an unbound key represents the whole application and may read
    anything in its project (project scoping is enforced separately by the route's ``project_id``).
    """
    if not auth.bound_agent_id:
        return

    is_owner = memory.agent_id == auth.bound_agent_id
    scope = memory.scope or "agent-private"

    if scope == "agent-shared" and not is_owner:
        shared = memory.shared_with_agents or []
        if auth.bound_agent_id in shared:
            return

    if enforce_principal_trust:
        if not TrustPolicy.can_read_scope(auth.trust_level, scope, is_owner):
            raise _read_denied(scope)
        return

    # Trust levels off: still enforce the scope ACL for bound keys, which is the boundary
    # agent-private is documented to provide.
    if scope == "global" or is_owner:
        return
    raise _read_denied(scope)


def authorize_delete(auth: AuthContext, memory, *, enforce_principal_trust: bool) -> None:
    """Authorize deleting or mutating a specific memory. Raises 403 when policy forbids it."""
    if not auth.bound_agent_id:
        return

    is_owner = memory.agent_id == auth.bound_agent_id

    if enforce_principal_trust:
        if not TrustPolicy.can_delete(auth.trust_level, is_owner):
            raise _delete_denied()
        return

    if not is_owner:
        raise _delete_denied()


def _read_denied(scope: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=f"Agent is not authorized to read this memory (scope='{scope}').",
    )


def _delete_denied() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Agent is not authorized to modify or delete this memory.",
    )


__all__ = [
    "effective_agent_id",
    "authorize_write",
    "authorize_read",
    "authorize_delete",
]
