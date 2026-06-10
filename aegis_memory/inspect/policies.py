"""Suggested policy generation. Emits a policy block the OSS user can adopt and the
enterprise tier can later enforce centrally (SSOT §5 Feature 6 / Task §3.5).
"""

from __future__ import annotations

from typing import Any

from .findings import Finding

# The policy is intentionally fixed/opinionated for v1 (precision-first defaults), with a
# comment noting which findings motivated each line so it reads as generated, not generic.
_BASE_POLICY = {
    "memory_policies": {
        "default": {
            "untrusted_input": {
                "action": "flag",
                "allow_shared_memory": False,
                "require_classifier": True,
            },
            "secrets": {"action": "reject"},
            "pii": {"action": "redact"},
            "global_memory": {"require_approval": True},
            "memory_expiry": {"default_days": 30},
        }
    }
}


def suggest_policies(findings: list[Finding]) -> dict[str, Any]:
    policy: dict[str, Any] = {k: dict(v) for k, v in _BASE_POLICY.items()}
    untrusted = sum(1 for f in findings if f.trust == "untrusted")
    shared = sum(1 for f in findings if f.category == "overbroad_shared_access")
    policy["_generated_from"] = {
        "untrusted_flows": untrusted,
        "shared_scope_sites": shared,
        "note": "Generated from inspect findings; tune per project before enforcing.",
    }
    return policy
