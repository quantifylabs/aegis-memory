"""Bounded interprocedural / cross-file taint — best-effort, NOT a general solver.

The same-scope check in :mod:`taint` proves a sink's written value is untrusted only when the
source sits in the *same function*. Real agent-memory poisoning usually crosses a boundary: an
untrusted fetch in one method is formatted by a helper and written by a *different* method, often
in a *different file* (the canonical case: ``paper_hunter.hunt`` → ``MemoryClient.store_intelligence``
→ ``client.add``, fed by arXiv web content). This module connects those, within a deliberate bound.

What it does (and only this):
  * **Parameter ascent** — if a sink writes a value that is a *parameter* of its enclosing function,
    follow each call site of that function (across files, name-matched) and resolve the corresponding
    argument in the caller's scope.
  * **Return descent** — if a sink writes a value assigned from a call to a *locally defined* function,
    follow that function's ``return`` expressions.
  * At every function boundary, the in-function resolution reuses :func:`taint.analyze` unchanged — so
    same-scope precision and the sanitizer/screening logic are shared, never reimplemented.

The honest limits (documented on purpose; the analyzer surfaces a "best-effort, bounded-depth" note):
  * **Name-based dispatch.** Functions and call sites are matched by simple name. No type/alias
    resolution, no MRO; a name collision can match the wrong definition.
  * **Depth/breadth bound.** Search stops at ``MAX_HOPS`` boundary crossings or after touching
    ``MAX_FUNCS`` functions. Past the bound the sink is *not* dropped — the analyzer emits it as a
    memory write whose source could not be confirmed.
  * No container-aliasing, no global/attribute state tracking beyond what ``taint`` already does in a
    single scope. This is a pragmatic wedge for the agent-memory sink pattern, not a dataflow engine.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import cast

from . import taint

# Bounds — small on purpose. The canonical cross-file chain resolves in 1–2 boundary hops.
MAX_HOPS = 6
MAX_FUNCS = 40

# Module-scope sentinel, mirroring analyzer's (calls with no enclosing def).
_EMPTY_FUNC = cast(ast.FunctionDef, ast.parse("def _aegis_module_scope():\n    pass").body[0])

_FuncDef = ast.FunctionDef | ast.AsyncFunctionDef


@dataclass
class FuncRecord:
    name: str
    file: str
    node: _FuncDef
    params: list[str]
    returns: list[ast.expr]


@dataclass
class CallRecord:
    callee: str  # simple (last) name
    file: str
    node: ast.Call
    line: int
    enclosing: _FuncDef | None
    args: list[ast.expr]
    keywords: dict[str, ast.expr]


@dataclass
class ResolveResult:
    taint: taint.TaintResult
    flow_path: list[dict]


class ProjectIndex:
    """Name-keyed index of function definitions and call sites across the whole project."""

    def __init__(self) -> None:
        self.functions: dict[str, list[FuncRecord]] = {}
        self.calls: dict[str, list[CallRecord]] = {}
        self._scopes: dict[int, taint.FunctionScope] = {}

    @classmethod
    def build(cls, modules: list[tuple[str, ast.Module]]) -> ProjectIndex:
        idx = cls()
        for rel, tree in modules:
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    params = [a.arg for a in taint._all_args(node)]
                    returns = [
                        r.value
                        for r in ast.walk(node)
                        if isinstance(r, ast.Return)
                        and r.value is not None
                        and _enclosing_function(r) is node
                    ]
                    idx.functions.setdefault(node.name, []).append(
                        FuncRecord(node.name, rel, node, params, returns)
                    )
                elif isinstance(node, ast.Call):
                    callee = _callee_name(node)
                    if callee is None:
                        continue
                    kw = {k.arg: k.value for k in node.keywords if k.arg}
                    idx.calls.setdefault(callee, []).append(
                        CallRecord(
                            callee, rel, node, getattr(node, "lineno", 0),
                            _enclosing_function(node), list(node.args), kw,
                        )
                    )
        return idx

    def scope_for(self, func: _FuncDef | None) -> taint.FunctionScope:
        if func is None:
            return taint.FunctionScope(func=_EMPTY_FUNC)
        s = self._scopes.get(id(func))
        if s is None:
            s = taint.build_scope(func)
            self._scopes[id(func)] = s
        return s


def resolve_sink(
    write_value: ast.expr | None,
    func: _FuncDef | None,
    file: str,
    index: ProjectIndex,
    *,
    screened: bool,
) -> ResolveResult | None:
    """Resolve a sink's written value to an untrusted source, same-scope or interprocedurally.

    Returns a :class:`ResolveResult` (untrusted taint + a source→sink ``flow_path``) when an
    untrusted origin is found within the bound, else ``None`` (the caller keeps the sink as a
    structural finding — it is never dropped)."""
    if write_value is None:
        return None
    res = _resolve(write_value, func, file, index, depth=0, visited=frozenset())
    if res is None:
        return None
    source, confidence, path = res
    note = (
        "untrusted source reaches this sink (same-scope)"
        if len(path) <= 1
        else f"untrusted source reaches this sink across {len(path)} step(s); best-effort, bounded-depth"
    )
    tr = taint.TaintResult(source, "untrusted", confidence, screened, notes=[note])
    return ResolveResult(tr, path)


def _resolve(
    expr: ast.expr | None,
    func: _FuncDef | None,
    file: str,
    index: ProjectIndex,
    depth: int,
    visited: frozenset[tuple[str, str]],
) -> tuple[str, str, list[dict]] | None:
    """Backward search. Returns (source, confidence, flow_path[source-first]) or None."""
    if expr is None or depth > MAX_HOPS or len(visited) > MAX_FUNCS:
        return None
    scope = index.scope_for(func)

    # Leaf: the same-scope engine proves taint here (also applies the sanitizer logic).
    tr = taint.analyze(expr, scope)
    if tr.trust == "untrusted":
        conf = tr.confidence if depth == 0 else "INFERRED"
        why = tr.notes[0] if tr.notes else "untrusted value"
        return (tr.source, conf, [_step(file, _line(expr), f"untrusted source: {why}")])

    if func is None:
        return None
    fkey = (file, func.name)
    if fkey in visited:
        return None
    nvisited = visited | {fkey}

    # (a) Parameter ascent — value is a parameter; follow each caller's argument.
    if isinstance(expr, ast.Name) and expr.id in scope.param_names:
        for cr in index.calls.get(func.name, []):
            arg = _arg_for_param(cr, expr.id, func)
            if arg is None:
                continue
            sub = _resolve(arg, cr.enclosing, cr.file, index, depth + 1, nvisited)
            if sub is not None:
                src, _conf, path = sub
                step = _step(cr.file, cr.line, f"caller passes untrusted value as '{expr.id}=' into {func.name}()")
                return (src, "INFERRED", path + [step])

    # (b) Return descent — value assigned from (or is) a call to a locally-defined function.
    call_expr: ast.expr | None = None
    if isinstance(expr, ast.Name):
        call_expr = scope.assignments.get(expr.id)
    elif isinstance(expr, ast.Call):
        call_expr = expr
    callee = _callee_name(call_expr) if isinstance(call_expr, ast.Call) else None
    if callee:
        for fr in index.functions.get(callee, []):
            for ret in fr.returns:
                sub = _resolve(ret, fr.node, fr.file, index, depth + 1, nvisited)
                if sub is not None:
                    src, _conf, path = sub
                    step = _step(fr.file, getattr(fr.node, "lineno", 0), f"value returned by {callee}()")
                    return (src, "INFERRED", path + [step])

    return None


# --- helpers -----------------------------------------------------------------------


def _arg_for_param(cr: CallRecord, param: str, func: _FuncDef) -> ast.expr | None:
    """The caller argument bound to ``param`` — keyword first, then positional (self-aware)."""
    if param in cr.keywords:
        return cr.keywords[param]
    params = [a.arg for a in taint._all_args(func)]
    # Drop the implicit receiver for bound-method calls (obj.method(...)).
    if isinstance(cr.node.func, ast.Attribute) and params and params[0] in ("self", "cls"):
        params = params[1:]
    if param in params:
        i = params.index(param)
        if i < len(cr.args):
            return cr.args[i]
    return None


def _callee_name(call: ast.Call) -> str | None:
    fn = call.func
    if isinstance(fn, ast.Attribute):
        return fn.attr
    if isinstance(fn, ast.Name):
        return fn.id
    return None


def _enclosing_function(node: ast.AST) -> _FuncDef | None:
    cur = getattr(node, "parent", None)
    while cur is not None:
        if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return cur
        cur = getattr(cur, "parent", None)
    return None


def _line(expr: ast.expr) -> int:
    return getattr(expr, "lineno", 0)


def _step(file: str, line: int, note: str) -> dict:
    return {"file": file, "line": line, "note": note}


__all__ = ["ProjectIndex", "ResolveResult", "resolve_sink", "MAX_HOPS", "MAX_FUNCS"]
