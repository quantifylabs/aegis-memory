"""Per-finding fix generator — the *correct*, verdict-checked guard API, tailored to each sink.

The earlier fix string called ``guard.write(content, ...)`` and **discarded the verdict**, so it
never gated the write — wrong against our own API (see ``aegis_memory.guard``). This module emits,
from a finding's *own* parsed call site, the two real options:

* **Screen the value** (surgical, primary): ``verdict = guard.write(<value>, ...); if
  verdict.allowed: <the original sink call, with the tainted arg replaced by verdict.content>``.
* **Wrap the store** (secondary): ``<receiver> = guard.protect(<receiver>, scope=...)`` — screens
  every write through that receiver.

Everything is derived from the call AST (``ast.unparse``), never a hardcoded structure, so it is
correct for any inspected project. If the call shape can't be parsed cleanly, we fall back to a
clearly-labeled generic snippet that **still uses the verdict-checked API**.
"""

from __future__ import annotations

import ast
import copy

_GUARD_IMPORT = "from aegis_memory import guard"


# Structured containers whose schema a whole-value swap would corrupt (dict -> string, etc.).
# An f-string / concatenation is NOT here: it evaluates to a string, so a whole swap preserves shape.
_STRUCTURED_CONTAINERS = (ast.Dict, ast.List, ast.Tuple, ast.Set)


def build_flow_fix(
    call: ast.Call | None,
    write_value: ast.expr | None,
    *,
    screen_value: ast.expr | None = None,
    scope: str = "agent-shared",
    trust: str = "untrusted",
) -> str:
    """Return a verdict-checked fix tailored to this sink, or a generic verdict-checked fallback.

    ``screen_value`` is the untrusted *leaf* to screen (e.g. ``state['x']`` inside a written
    ``{'text': state['x']}``); when given, the fix screens that leaf and swaps it in place, so the
    written container keeps its shape. When omitted it defaults to ``write_value``. If the value to
    screen is a structured container (dict/list/tuple/set), a whole-value swap would change the
    stored schema, so we emit the safe generic snippet instead of a corrupting surgical fix."""
    try:
        if call is None or write_value is None:
            return _generic_fix(scope, trust)
        target = screen_value if screen_value is not None else write_value
        if isinstance(target, _STRUCTURED_CONTAINERS):
            # No scalar leaf was resolved; screening the whole container would corrupt its schema.
            return _generic_fix(scope, trust)
        receiver, _method = _split_receiver_method(call)
        value_src = ast.unparse(target)
        rewritten = _rewrite_sink_call(call, target)
        resolved_scope = _scope_from_call(call) or scope
        if value_src and rewritten:
            return _tailored_fix(value_src, rewritten, receiver, resolved_scope, trust)
    except Exception:  # noqa: BLE001 — any AST surprise falls back to the safe generic snippet
        pass
    return _generic_fix(scope, trust)


# --- builders ----------------------------------------------------------------------


def _tailored_fix(
    value_src: str, rewritten_call: str, receiver: str | None, scope: str, trust: str
) -> str:
    body = "\n    ".join(rewritten_call.splitlines())
    lines = [
        _GUARD_IMPORT,
        "",
        "# Screen the value before it persists (surgical - recommended):",
        f'verdict = guard.write({value_src}, trust_level="{trust}", scope="{scope}", on_reject="return")',
        "if verdict.allowed:",
        f"    {body}",
    ]
    if receiver:
        lines += [
            "",
            "# Or wrap the store so every write through it is screened:",
            f'{receiver} = guard.protect({receiver}, scope="{scope}")',
        ]
    return "\n".join(lines)


def _generic_fix(scope: str, trust: str) -> str:
    return "\n".join(
        [
            _GUARD_IMPORT,
            "",
            "# Screen the written value before it persists (write verdict.content, not the raw value):",
            f'verdict = guard.write(content, trust_level="{trust}", scope="{scope}", on_reject="return")',
            "if verdict.allowed:",
            "    ...  # perform the original write using verdict.content",
            "",
            "# Or wrap the store so every write through it is screened:",
            f'store = guard.protect(store, scope="{scope}")',
        ]
    )


# --- AST helpers -------------------------------------------------------------------


def _split_receiver_method(call: ast.Call) -> tuple[str | None, str | None]:
    """(receiver_src, method) for ``obj.method(...)``; (None, func) for a bare ``func(...)``."""
    fn = call.func
    if isinstance(fn, ast.Attribute):
        return ast.unparse(fn.value), fn.attr
    if isinstance(fn, ast.Name):
        return None, fn.id
    return None, None


def _rewrite_sink_call(call: ast.Call, target: ast.expr) -> str | None:
    """The original sink call with the tainted node replaced by ``verdict.content``.

    Locates ``target`` *anywhere* in the call by object identity — a top-level argument
    (``add(value)``), a keyword (``add(messages=value)``), a ``put(ns, key, value)`` positional, or a
    node nested inside a container (the ``state['x']`` inside ``{'text': state['x']}``) — and swaps
    only that node in a deep copy, preserving every other argument and the container's shape."""
    path = _path_to(call, target)
    if path is None:
        return None
    placeholder = ast.parse("verdict.content", mode="eval").body
    new_call = copy.deepcopy(call)
    if not _set_at_path(new_call, path, placeholder):
        return None
    return ast.unparse(new_call)


def _path_to(node: ast.AST, target: ast.AST, path: tuple = ()) -> tuple | None:
    """Field/index path from ``node`` to ``target`` (matched by identity), or None. Empty path
    (``node is target``) is treated as no path — the swap target must be inside the call."""
    if node is target:
        return path or None
    for field, value in ast.iter_fields(node):
        if isinstance(value, list):
            for i, item in enumerate(value):
                if isinstance(item, ast.AST):
                    found = _path_to(item, target, path + ((field, i),))
                    if found is not None:
                        return found
        elif isinstance(value, ast.AST):
            found = _path_to(value, target, path + ((field, None),))
            if found is not None:
                return found
    return None


def _set_at_path(root: ast.AST, path: tuple, new_node: ast.AST) -> bool:
    cur: object = root
    for field, idx in path[:-1]:
        cur = getattr(cur, field) if idx is None else getattr(cur, field)[idx]
    field, idx = path[-1]
    if idx is None:
        setattr(cur, field, new_node)
    else:
        getattr(cur, field)[idx] = new_node
    return True


def _scope_from_call(call: ast.Call) -> str | None:
    """A literal ``scope="..."`` argument on the sink call, when present — so the fix mirrors the
    project's own scope rather than imposing a default."""
    for kw in call.keywords:
        if kw.arg == "scope" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
            return kw.value.value
    return None


__all__ = ["build_flow_fix"]
