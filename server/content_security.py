"""Re-export shim — the single source of truth moved into the installable package.

The four-stage content-security pipeline now lives in
``aegis_memory.security.content_security`` so the wheel ships it and ``aegis inspect``
works after a plain ``pip install``. Server modules, the benchmark, and the tests keep
using ``from content_security import ...`` (with ``server/`` on ``sys.path``) unchanged —
this module just re-exports the relocated definitions. Do not add logic here.
"""

from __future__ import annotations

from aegis_memory.security.content_security import *  # noqa: F401,F403
from aegis_memory.security.content_security import (  # noqa: F401
    _CLASSIFIER_SYSTEM_PROMPT,
    ContentAction,
    ContentSecurityScanner,
    ContentSecurityVerdict,
    Detection,
    DetectionType,
    InjectionClassifier,
    _luhn_check,
    _parse_classifier_json,
)
