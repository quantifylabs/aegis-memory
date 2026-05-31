"""Import-path bootstrap for the injection benchmark.

The Aegis server modules use *bare* imports (``from content_security import
...``) and expect ``<repo>/server`` on ``sys.path`` (see ``tests/conftest.py``).
The ``aegis_memory`` package lives at the repo root. Importing this module
makes both importable without installing the server, so the benchmark can call
the real ``ContentSecurityScanner`` rather than reimplementing detection logic.
"""

from __future__ import annotations

import sys
from pathlib import Path

# benchmarks/injection/_paths.py -> repo root is two parents up.
REPO_ROOT = Path(__file__).resolve().parents[2]
SERVER_DIR = REPO_ROOT / "server"


def ensure_paths() -> None:
    """Prepend repo root and server/ to sys.path (idempotent)."""
    for p in (str(SERVER_DIR), str(REPO_ROOT)):
        if p not in sys.path:
            sys.path.insert(0, p)


ensure_paths()
