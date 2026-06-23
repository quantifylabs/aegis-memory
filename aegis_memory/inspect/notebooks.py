"""Jupyter ``.ipynb`` ingestion for the static analyzer.

Notebook-based repos are a large slice of the agent-memory ecosystem, but the analyzer only
walks ``.py``. This module lifts a notebook's **code cells** into a single :class:`ast.Module`
the existing pipeline can scan unchanged — no detection logic lives here.

Two subtleties the cold test proved necessary:

* **Magics break the parse.** A leading ``%pip install ...`` (or any ``%``/``!`` line, or a
  ``%%`` cell-magic cell) is a :class:`SyntaxError` in plain Python, and an AST scanner then drops
  the *entire* file. We blank such lines (preserving line counts so line numbers stay stable) and
  blank whole ``%%`` cells.
* **Whole-file parse can still fail** on multi-line constructs split across cells. So we parse the
  whole cleaned source first and, on :class:`SyntaxError`, fall back to per-cell parsing — skipping
  only the offending cell and unioning the rest, instead of losing the whole notebook.

Reported line numbers point into the concatenated code-cell stream (matching an extracted-``.py``
of the same notebook), so findings anchor back to the notebook's code.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

# Lines that are Jupyter line-magics / shell escapes (``%pip``, ``!ls``); not valid Python.
_MAGIC_LINE = re.compile(r"^\s*[%!]")


def load_notebook(path: str | Path) -> ast.Module | None:
    """Parse a ``.ipynb`` into an :class:`ast.Module` of its code cells, or ``None`` if nothing
    parses. Line numbers are relative to the concatenated cleaned code-cell stream."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return None
    if not isinstance(data, dict):
        return None

    cleaned_cells: list[str] = []
    for cell in data.get("cells", []):
        if not isinstance(cell, dict) or cell.get("cell_type") != "code":
            continue
        cleaned_cells.append(_clean_cell(cell.get("source", "")))
    if not cleaned_cells:
        return None

    # Cell i starts at line ``offsets[i]`` (1-based) in the concatenation joined by a single "\n".
    offsets: list[int] = []
    line = 1
    for src in cleaned_cells:
        offsets.append(line)
        line += src.count("\n") + 1  # +1 for the join newline between cells

    full_src = "\n".join(cleaned_cells)
    try:
        return ast.parse(full_src)
    except SyntaxError:
        return _parse_per_cell(cleaned_cells, offsets)


def _clean_cell(source: object) -> str:
    """Cell source as a string with magics/shell escapes blanked out (line count preserved).

    A cell whose first non-blank line is a ``%%`` cell-magic is blanked entirely — its body is not
    Python. Per-line ``%``/``!`` magics are replaced with empty lines so downstream line numbers
    still line up with the original cell."""
    text = "".join(source) if isinstance(source, list) else str(source or "")
    lines = text.split("\n")
    first_nonblank = next((ln for ln in lines if ln.strip()), "")
    if first_nonblank.lstrip().startswith("%%"):
        return "\n".join("" for _ in lines)
    return "\n".join("" if _MAGIC_LINE.match(ln) else ln for ln in lines)


def _parse_per_cell(cleaned_cells: list[str], offsets: list[int]) -> ast.Module | None:
    """Per-cell fallback: parse each cell independently, shift its line numbers to the global
    offset, and union the bodies — skipping only cells that fail to parse."""
    body: list[ast.stmt] = []
    for src, offset in zip(cleaned_cells, offsets):
        if not src.strip():
            continue
        try:
            cell_tree = ast.parse(src)
        except SyntaxError:
            continue
        if offset > 1:
            ast.increment_lineno(cell_tree, offset - 1)
        body.extend(cell_tree.body)
    if not body:
        return None
    module = ast.Module(body=body, type_ignores=[])
    ast.fix_missing_locations(module)
    return module


__all__ = ["load_notebook"]
