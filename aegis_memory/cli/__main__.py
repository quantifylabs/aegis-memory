"""``python -m aegis_memory.cli`` entry point.

Mirrors the ``aegis`` console script (``[project.scripts]`` -> ``aegis_memory.cli.main:main``)
so the CLI is reachable even when the script isn't on ``PATH`` — e.g. a fresh
``pip install aegis-memory`` whose ``Scripts``/``bin`` dir isn't exported. The Claude Code
``/aegis:inspect`` command falls back to ``python -m aegis_memory.cli inspect .`` for exactly
this case.
"""

from aegis_memory.cli.main import main

if __name__ == "__main__":
    main()
