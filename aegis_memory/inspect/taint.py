"""Precision-first taint check. Honest by construction.

Flag a memory write as ``untrusted`` only when the written value traces — *within the
same function scope* — to a known untrusted source (request/ticket input, tool result,
web fetch, external file read) with **no sanitizer between**. We never claim cross-
function taint we did not prove.

Confidence:
  * same-scope direct (sink arg is the source, or a var assigned straight from it) -> EXTRACTED
  * one variable hop / heuristic receiver name                                      -> INFERRED
  * source cannot be resolved                                                       -> AMBIGUOUS
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field

# Parameter / variable names that denote externally-controlled (untrusted) input.
_UNTRUSTED_NAME_HINTS = (
    "ticket",
    "request",
    "req",
    "body",
    "payload",
    "event",
    "user_input",
    "userinput",
    "incoming",
    "raw",
    "external",
    "untrusted",
    "tool_result",
    "tool_output",
    "observation",
    "fetched",
    "webpage",
    "web_content",
)

# Attribute names that read untrusted data off an object (e.g. resp.text, req.json).
_UNTRUSTED_ATTR_HINTS = ("text", "json", "content", "body", "data", "read")

# Callables whose return value is untrusted (network / file / tool egress).
_UNTRUSTED_CALL_HINTS = (
    "get",
    "post",
    "fetch",
    "read",
    "read_text",
    "load",
    "invoke",
    "run",
    "call",
    "complete",
)
_UNTRUSTED_CALL_RECEIVERS = (
    "requests",
    "httpx",
    "urllib",
    "session",
    "client",
    "tool",
    "open",
)

# Tokens that mark a value as sanitized/screened by a content-security guard.
_SANITIZER_TOKENS = (
    "scan",
    "scan_async",
    "scan_text",
    "guard",
    "sanitize",
    "redact",
    "screen",
    "content_security",
    "contentsecurityscanner",
    "validate_content",
    "classify",
)


@dataclass
class FunctionScope:
    """Per-function context the analyzer hands to the taint check."""

    func: ast.FunctionDef | ast.AsyncFunctionDef
    param_names: set[str] = field(default_factory=set)
    # name -> the value expression last assigned to it (best effort, top-level body)
    assignments: dict[str, ast.expr] = field(default_factory=dict)
    # variable names that flowed through a sanitizer call somewhere in the scope
    sanitized_names: set[str] = field(default_factory=set)
    # True if a guard/scan call appears anywhere in this scope (screening present)
    has_sanitizer_call: bool = False


@dataclass
class TaintResult:
    source: str  # "untrusted_input" | "tool_output" | "unknown"
    trust: str  # "untrusted" | "unknown" | "internal"
    confidence: str  # EXTRACTED | INFERRED | AMBIGUOUS
    screened: bool
    notes: list[str] = field(default_factory=list)


def build_scope(func: ast.FunctionDef | ast.AsyncFunctionDef) -> FunctionScope:
    scope = FunctionScope(func=func)
    scope.param_names = {a.arg for a in _all_args(func)}
    for node in ast.walk(func):
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name):
                    scope.assignments[tgt.id] = node.value
            # var assigned from a sanitizer call -> mark sanitized
            if _is_sanitizer_call(node.value):
                for tgt in node.targets:
                    if isinstance(tgt, ast.Name):
                        scope.sanitized_names.add(tgt.id)
        elif isinstance(node, ast.Call) and _is_sanitizer_call(node):
            scope.has_sanitizer_call = True
    return scope


_CONF_RANK = {"EXTRACTED": 3, "INFERRED": 2, "AMBIGUOUS": 1}


def analyze(write_value: ast.expr | None, scope: FunctionScope) -> TaintResult:
    """Classify the trust of the value being written by a sink call.

    Recurses through containers (dict/list/tuple/f-string/concat) that wrap the value, and
    follows a single variable hop into its in-scope assignment. The strongest evidence wins.
    """
    if write_value is None:
        return TaintResult("unknown", "unknown", "AMBIGUOUS", scope.has_sanitizer_call)

    screened = scope.has_sanitizer_call or bool(_expr_names(write_value) & scope.sanitized_names)
    best = _classify(write_value, scope, depth=0)
    if best is None:
        return TaintResult("unknown", "unknown", "AMBIGUOUS", screened)
    src, conf, note = best
    return TaintResult(src, "untrusted", conf, screened, [note])


def _classify(node: ast.expr, scope: FunctionScope, depth: int) -> tuple[str, str, str] | None:
    """Return (source, confidence, note) if the expression carries untrusted data."""
    if depth > 4:
        return None

    # Direct untrusted source -> EXTRACTED (same-scope, proven).
    label = _untrusted_label(node, scope)
    if label is not None:
        src, kind = label
        return (src, "EXTRACTED", kind)

    # One variable hop into its assignment -> INFERRED.
    if isinstance(node, ast.Name):
        assigned = scope.assignments.get(node.id)
        if assigned is not None and depth < 4:
            sub = _classify(assigned, scope, depth + 1)
            if sub is not None:
                src, _conf, kind = sub
                return (src, "INFERRED", f"via {node.id}: {kind}")
        if any(h in node.id.lower() for h in _UNTRUSTED_NAME_HINTS):
            kind = "tool_output" if ("tool" in node.id.lower()) else "untrusted_input"
            return (kind, "INFERRED", f"param {node.id}")
        return None

    # Containers: recurse into children, keep the strongest result.
    children = _child_exprs(node)
    best: tuple[str, str, str] | None = None
    for child in children:
        sub = _classify(child, scope, depth + 1)
        if sub is None:
            continue
        if best is None or _CONF_RANK[sub[1]] > _CONF_RANK[best[1]]:
            best = sub
    return best


def _child_exprs(node: ast.expr) -> list[ast.expr]:
    if isinstance(node, ast.Dict):
        return [v for v in node.values if v is not None]
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return list(node.elts)
    if isinstance(node, ast.JoinedStr):
        return [v.value for v in node.values if isinstance(v, ast.FormattedValue)]
    if isinstance(node, ast.BinOp):
        return [node.left, node.right]
    if isinstance(node, ast.Call):
        return list(node.args) + [kw.value for kw in node.keywords]
    return []


# --- helpers ----------------------------------------------------------------------


def _all_args(func: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.arg]:
    a = func.args
    return [*a.posonlyargs, *a.args, *([a.vararg] if a.vararg else []), *a.kwonlyargs]


def _untrusted_label(node: ast.expr, scope: FunctionScope) -> tuple[str, str] | None:
    """Return (source, human-note) if node reads an untrusted source, else None."""
    # Name matching an untrusted hint (param or var).
    if isinstance(node, ast.Name):
        n = node.id.lower()
        if any(h in n for h in _UNTRUSTED_NAME_HINTS):
            kind = "tool_output" if ("tool" in n or "observation" in n) else "untrusted_input"
            return (kind, f"name '{node.id}'")
        return None
    # Subscript like ticket["text"] / request["body"] / state["input"].
    if isinstance(node, ast.Subscript):
        return _untrusted_label(node.value, scope)
    # Attribute like resp.text / req.json / ticket.body.
    if isinstance(node, ast.Attribute):
        if node.attr.lower() in _UNTRUSTED_ATTR_HINTS:
            base = _untrusted_label(node.value, scope)
            return base or ("untrusted_input", f"attr '.{node.attr}'")
        return _untrusted_label(node.value, scope)
    # Call like requests.get(...).text, open(p).read(), tool.invoke(...).
    if isinstance(node, ast.Call):
        fn = node.func
        if isinstance(fn, ast.Attribute) and fn.attr.lower() in _UNTRUSTED_CALL_HINTS:
            recv = _root_name(fn.value)
            kind = "tool_output" if (recv and ("tool" in recv or "client" in recv)) else "untrusted_input"
            return (kind, f"call '{fn.attr}()'")
        if isinstance(fn, ast.Name) and fn.id.lower() in _UNTRUSTED_CALL_RECEIVERS:
            return ("untrusted_input", f"call '{fn.id}()'")
        # f-strings / concatenations: inspect the parts.
    if isinstance(node, ast.JoinedStr):
        for v in node.values:
            if isinstance(v, ast.FormattedValue):
                lab = _untrusted_label(v.value, scope)
                if lab:
                    return lab
    if isinstance(node, ast.BinOp):
        return _untrusted_label(node.left, scope) or _untrusted_label(node.right, scope)
    return None


def _is_sanitizer_call(node: ast.expr) -> bool:
    if not isinstance(node, ast.Call):
        return False
    fn = node.func
    name = ""
    if isinstance(fn, ast.Attribute):
        name = fn.attr
    elif isinstance(fn, ast.Name):
        name = fn.id
    n = name.lower()
    if n in _SANITIZER_TOKENS or any(t in n for t in ("scan", "guard", "sanitize", "redact")):
        return True
    # The aegis guard idiom — ``guard.write(...)`` / ``guard.protect(...)`` — is exactly the fix
    # ``aegis inspect`` recommends. Its methods are named ``write``/``protect`` (no sanitizer token
    # in the name), so the screening signal is the ``guard`` *receiver*. Recognising it is what lets
    # the inspect -> fix -> rescan loop close: apply the suggested guard, re-run, the lane flips green.
    if isinstance(fn, ast.Attribute) and n in ("write", "protect") and "guard" in _receiver_tokens(fn.value):
        return True
    return False


def _receiver_tokens(node: ast.expr) -> set[str]:
    """Lowercased identifier + attribute tokens in a call's receiver (e.g. ``self.guard`` ->
    {"self","guard"}), so the guard idiom is recognised however the module is referenced."""
    toks: set[str] = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Name):
            toks.add(n.id.lower())
        elif isinstance(n, ast.Attribute):
            toks.add(n.attr.lower())
    return toks


def _root_name(node: ast.expr) -> str | None:
    while isinstance(node, (ast.Attribute, ast.Subscript)):
        node = node.value
    if isinstance(node, ast.Name):
        return node.id.lower()
    if isinstance(node, ast.Call):
        return _root_name(node.func)
    return None


def _expr_names(node: ast.expr) -> set[str]:
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}


__all__ = ["FunctionScope", "TaintResult", "analyze", "build_scope"]
