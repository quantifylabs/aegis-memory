"""Shared scope policy for content provenance.

This is the single definition of the rule *"untrusted content may not become globally
readable"*, imported by both enforcement paths so they cannot drift:

- ``aegis_memory.guard`` — the offline write gate wrapped around any store.
- ``server/`` — the Aegis API, via ``server/memory_authz.py``.

**This file exists in two places on purpose**, following the same arrangement as
``content_security.py``:

* ``aegis_memory/scope_policy.py`` — the wheel's copy, so ``guard`` works after a plain
  ``pip install aegis-memory`` with no server checkout.
* ``server/scope_policy.py`` — self-contained (pure stdlib, no package imports) so the
  production server image, built from ``context: ./server``, imports it locally with no
  ``aegis_memory`` package present. Importing across that boundary would raise
  ModuleNotFoundError at API startup, before a single route is served.

Two copies of a security rule are only safe if they cannot silently diverge:
``tests/test_scope_policy_no_drift.py`` fails the moment the source text differs. Apply every
edit to both files.

Before this module existed the two had divergent semantics: ``guard.write()`` blocked
``untrusted``/``unknown`` content from ``global`` scope while the server did not, because
``TrustPolicy.can_write`` was never called from the memory routes.

Two different notions of "trust" meet at a memory write, and conflating them is the bug this
module exists to prevent:

``trust_level`` here labels the **content's provenance** — where the data came from. That is what
this module governs. Whether a given *principal* (API key) may write to a scope at all is a
separate question answered by ``server/trust_levels.py::TrustPolicy.can_write``, which takes the
principal's trust level, not the content's.

Both checks apply on a server write. Content provenance is the ceiling; principal trust is the
floor.
"""

from __future__ import annotations

# Content provenance levels that must never be written straight to global scope.
# "unknown" is the conservative un-vouched default, not a long-term tier — it is included
# here because un-vouched content reaching every agent is the case this rule protects.
UNTRUSTED_CONTENT_LEVELS: tuple[str, ...] = ("untrusted", "unknown")

# The scope every agent in a project/namespace can read.
GLOBAL_SCOPE = "global"


def content_may_enter_scope(trust_level: str | None, scope: str | None) -> bool:
    """Return whether content of this provenance may be stored at this scope.

    Promoting untrusted or un-vouched content to ``global`` means every agent in the project
    reads it, which turns one poisoned write into every agent's instruction. That promotion
    requires a privileged path, never a raw write.

    Unrecognised values are treated conservatively: a missing/None trust level is assumed
    untrusted, and a missing scope is assumed non-global (the safe default is agent-private).
    """
    tl = (trust_level or "untrusted").lower()
    sc = (scope or "agent-private").lower()
    return not (sc == GLOBAL_SCOPE and tl in UNTRUSTED_CONTENT_LEVELS)


def scope_denial_reason(trust_level: str | None, scope: str | None) -> str:
    """Human-readable explanation for a scope denial. Used in guard verdicts and API errors."""
    tl = (trust_level or "untrusted").lower()
    sc = (scope or "agent-private").lower()
    return f"{tl} content may not be written to '{sc}' scope (requires a privileged promotion)"


__all__ = [
    "UNTRUSTED_CONTENT_LEVELS",
    "GLOBAL_SCOPE",
    "content_may_enter_scope",
    "scope_denial_reason",
]
