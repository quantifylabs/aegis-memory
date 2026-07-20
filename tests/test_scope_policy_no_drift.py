"""Guard against drift between the two scope-policy copies.

The scope policy — *"untrusted content may not become globally readable"* — exists in two
places on purpose, the same arrangement as ``content_security.py``:

* ``server/scope_policy.py`` — self-contained (pure stdlib) so the production server image,
  built from ``context: ./server``, imports it locally with no ``aegis_memory`` package
  present.
* ``aegis_memory/scope_policy.py`` — the wheel's copy, so ``aegis_memory.guard`` works after a
  plain ``pip install aegis-memory`` with no server checkout.

This matters more here than it does for the content-security pipeline. The whole point of
extracting this module was that ``guard.write()`` and ``POST /memories`` had *divergent*
semantics: the guard blocked ``untrusted``→``global`` and the server did not. Two copies that
drift would silently recreate exactly that bug.

This test fails the moment their source text differs — make every edit in both files (or
collapse to one source) and this stays green.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_COPY = _REPO_ROOT / "server" / "scope_policy.py"
_PACKAGE_COPY = _REPO_ROOT / "aegis_memory" / "scope_policy.py"


def test_scope_policy_copies_are_byte_identical() -> None:
    server_src = _SERVER_COPY.read_bytes()
    package_src = _PACKAGE_COPY.read_bytes()
    assert server_src == package_src, (
        "server/scope_policy.py and aegis_memory/scope_policy.py have drifted. They must stay "
        "byte-identical: the server image ships the standalone server copy, the wheel ships "
        "the package copy. A divergence here recreates the guard-vs-server split this module "
        "was extracted to eliminate. Apply your change to both."
    )


def test_server_copy_has_no_package_imports() -> None:
    """The server copy must not reach back into ``aegis_memory``.

    That is the failure this split exists to prevent: the server image has no ``aegis_memory``
    package, so any such import raises ModuleNotFoundError at API startup, before a single
    route is served.
    """
    src = _SERVER_COPY.read_text(encoding="utf-8")
    assert "import aegis_memory" not in src
    assert "from aegis_memory" not in src
    assert "from ." not in src, "relative import will not resolve outside the package"


def test_server_app_imports_with_aegis_memory_absent() -> None:
    """The real guarantee: the uvicorn entrypoint starts in an image with no ``aegis_memory``.

    The grep above only covers one file. This blocks the package outright -- the way the
    production image does by simply not containing it -- and imports what uvicorn imports, so
    *any* server module reaching into the wheel fails here rather than at container startup.

    Runs in a subprocess: the blocker manipulates ``sys.meta_path`` and importing the whole app
    would otherwise leak both into the rest of the suite.
    """
    program = textwrap.dedent(
        """
        import sys

        class Blocker:
            def find_spec(self, name, path=None, target=None):
                if name == "aegis_memory" or name.startswith("aegis_memory."):
                    raise ModuleNotFoundError(f"No module named '{name}'")
                return None

        sys.meta_path.insert(0, Blocker())
        sys.path.insert(0, sys.argv[1])

        import api.app  # noqa: F401  -- the uvicorn entrypoint (api.app:modular_app)
        import memory_authz

        assert memory_authz.content_may_enter_scope("untrusted", "global") is False
        print("OK")
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", program, str(_REPO_ROOT / "server")],
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT / "server"),
    )
    assert result.returncode == 0 and "OK" in result.stdout, (
        "the server failed to import without the aegis_memory package present, which is how "
        "the production image is built (context: ./server). It would raise ModuleNotFoundError "
        f"at startup before serving a route.\n\nstderr:\n{result.stderr[-2000:]}"
    )
