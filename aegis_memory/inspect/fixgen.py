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


def build_flow_fix(
    call: ast.Call | None,
    write_value: ast.expr | None,
    *,
    scope: str = "agent-shared",
    trust: str = "untrusted",
) -> str:
    """Return a verdict-checked fix tailored to this sink, or a generic verdict-checked fallback."""
    try:
        if call is None or write_value is None:
            return _generic_fix(scope, trust)
        receiver, _method = _split_receiver_method(call)
        value_src = ast.unparse(write_value)
        rewritten = _rewrite_sink_call(call, write_value)
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


def _rewrite_sink_call(call: ast.Call, write_value: ast.expr) -> str | None:
    """The original sink call with the tainted argument replaced by ``verdict.content``.

    Identity-matches ``write_value`` against the original call's args/keywords to locate the
    tainted slot, then swaps it in a deep copy — preserving every other argument (``scope=``,
    ``shared_with_agents=``, the ``put(ns, key, value)`` positionals, …)."""
    placeholder = ast.parse("verdict.content", mode="eval").body
    new_call = copy.deepcopy(call)
    for orig_kw, new_kw in zip(call.keywords, new_call.keywords):
        if orig_kw.value is write_value:
            new_kw.value = placeholder
            return ast.unparse(new_call)
    for i, orig_arg in enumerate(call.args):
        if orig_arg is write_value:
            new_call.args[i] = placeholder
            return ast.unparse(new_call)
    return None


def _scope_from_call(call: ast.Call) -> str | None:
    """A literal ``scope="..."`` argument on the sink call, when present — so the fix mirrors the
    project's own scope rather than imposing a default."""
    for kw in call.keywords:
        if kw.arg == "scope" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
            return kw.value.value
    return None


__all__ = ["build_flow_fix"]
