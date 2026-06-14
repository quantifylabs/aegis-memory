"""Guard against drift between the two content-security copies.

The four-stage content-security pipeline exists in two places on purpose:

* ``server/content_security.py`` — self-contained (pure stdlib) so the production
  server image, built from ``context: ./server``, imports it locally with no
  ``aegis_memory`` package present.
* ``aegis_memory/security/content_security.py`` — the wheel's copy, so ``aegis
  inspect`` / ``aegis_memory.guard`` work after a plain ``pip install aegis-memory``
  with no server checkout.

Keeping two copies is only safe if they can never silently diverge. This test
fails the moment their source text differs — make every edit in both files (or
collapse to one source) and this stays green.
"""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_COPY = _REPO_ROOT / "server" / "content_security.py"
_PACKAGE_COPY = _REPO_ROOT / "aegis_memory" / "security" / "content_security.py"


def test_content_security_copies_are_byte_identical() -> None:
    server_src = _SERVER_COPY.read_bytes()
    package_src = _PACKAGE_COPY.read_bytes()
    assert server_src == package_src, (
        "server/content_security.py and aegis_memory/security/content_security.py have "
        "drifted. They must stay byte-identical: the server image ships the standalone "
        "server copy, the wheel ships the package copy. Apply your change to both."
    )
