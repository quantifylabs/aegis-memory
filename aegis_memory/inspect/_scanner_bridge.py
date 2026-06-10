"""Bridge to the real ``ContentSecurityScanner`` — never reimplement detection.

``aegis inspect`` and the demo reuse the exact scanner that the benchmark validates
(``server/content_security.py``). The detection logic lives there and nowhere else.

Import strategy (in priority order):

1. ``from aegis_memory.security.content_security import ...`` — the relocated home the
   wheel ships (added in the skill-packaging task). Works after ``pip install``.
2. A ``benchmarks/injection/_paths.py``-style ``sys.path`` shim that adds the repo's
   ``server/`` dir, then ``from content_security import ...`` — works inside a repo clone
   even before the relocation lands. This is the bridge-only path for Task 1.

Either way the *same* scanner class is returned; this module adds no detection rules.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

# Public re-exports resolved at import time.
ContentSecurityScanner: Any
ContentAction: Any
ContentSecurityVerdict: Any


def _import_scanner() -> tuple[Any, Any, Any]:
    # 1. Relocated home (post skill-packaging task / installed wheel).
    try:
        from aegis_memory.security.content_security import (  # type: ignore
            ContentAction as _Action,
        )
        from aegis_memory.security.content_security import (
            ContentSecurityScanner as _Scanner,
        )
        from aegis_memory.security.content_security import (
            ContentSecurityVerdict as _Verdict,
        )

        return _Scanner, _Action, _Verdict
    except Exception:
        pass

    # 2. In-repo shim: add <repo>/server to sys.path and import bare module.
    server_dir = _find_server_dir()
    if server_dir is not None and str(server_dir) not in sys.path:
        sys.path.insert(0, str(server_dir))
    from content_security import (  # type: ignore
        ContentAction as _Action,
    )
    from content_security import (
        ContentSecurityScanner as _Scanner,
    )
    from content_security import (
        ContentSecurityVerdict as _Verdict,
    )

    return _Scanner, _Action, _Verdict


def _find_server_dir() -> Path | None:
    """Locate ``server/content_security.py`` by walking up from this file."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "server" / "content_security.py"
        if candidate.exists():
            return parent / "server"
    return None


ContentSecurityScanner, ContentAction, ContentSecurityVerdict = _import_scanner()


# Default content-security policy used by ``aegis inspect`` and the demo guard.
# Injection is set to ``reject`` so a memory-write guard blocks a detected injection
# deterministically and offline (no Stage-4 classifier required). Detection itself is
# unchanged — it is the same benchmark-validated pipeline; only the *action* policy is
# strict here, which is the honest posture for a memory firewall.
def default_scanner_settings() -> SimpleNamespace:
    return SimpleNamespace(
        content_max_length=50_000,
        metadata_max_depth=5,
        metadata_max_keys=50,
        content_policy_pii="flag",
        content_policy_secrets="reject",
        content_policy_injection="reject",
    )


def get_scanner(settings: Any | None = None) -> Any:
    """Instantiate the real scanner offline (Stages 1-3, no model, no network)."""
    return ContentSecurityScanner(settings or default_scanner_settings())


def scan_text(text: str, metadata: dict | None = None, settings: Any | None = None) -> Any:
    """Convenience: run the deterministic scan and return the real verdict."""
    return get_scanner(settings).scan(text, metadata)


__all__ = [
    "ContentAction",
    "ContentSecurityScanner",
    "ContentSecurityVerdict",
    "default_scanner_settings",
    "get_scanner",
    "scan_text",
]
