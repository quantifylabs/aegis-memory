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
    # Streamlit user-input widgets — the value typed by an end user is untrusted.
    "chat_input",
    "text_input",
    "text_area",
)
_UNTRUSTED_CALL_RECEIVERS = (
    "requests",
    "httpx",
    "urllib",
    "session",
    "client",
    "tool",
    "open",
    # Builtin ``input(...)`` — raw user input from the console.
    "input",
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
    # Parameter names that are untrusted-by-default for this function shape: a CrewAI
    # ``BaseTool._run`` carries scraped/fetched content, and a LangGraph node's ``state``
    # carries incoming (email/tool) content. Specific shapes only — never a blanket rule.
    untrusted_params: set[str] = field(default_factory=set)
    # name -> the value expression last assigned to it (best effort, top-level body)
    assignments: dict[str, ast.expr] = field(default_factory=dict)
    # variable names that flowed through a sanitizer call somewhere in the scope
    sanitized_names: set[str] = field(default_factory=set)
    # receiver names wrapped by ``guard.protect(...)`` — a write *through* one is screened (sink-tied)
    protected_receivers: set[str] = field(default_factory=set)
    # True if a scanner/sanitizer call appears anywhere in this scope (screening present). NB: the
    # guard idiom (``guard.write``/``guard.protect``) deliberately does NOT set this blanket flag —
    # it screens sink-tied (via sanitized_names / protected_receivers) so a discarded verdict or a
    # write to a *different* unprotected store is never green-lit. See _build_findings/build_scope.
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
    scope.untrusted_params = _untrusted_params(func)
    for node in ast.walk(func):
        if isinstance(node, ast.NamedExpr) and isinstance(node.target, ast.Name):
            # Walrus assignment (``prompt := st.chat_input(...)``) — record it like an Assign so
            # the variable resolves to its source. Common in Streamlit (``if x := st.chat_input()``).
            scope.assignments[node.target.id] = node.value
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name):
                    scope.assignments[tgt.id] = node.value
            rhs = node.value
            # A value assigned from a screening call (``scanner.scan`` / ``guard.write``) is
            # sanitized: the sink is screened ONLY if it then actually uses this variable
            # (``verdict.content`` / the scanned text). A discarded verdict screens nothing.
            if _is_sanitizer_call(rhs) or _is_guard_write_call(rhs):
                for tgt in node.targets:
                    if isinstance(tgt, ast.Name):
                        scope.sanitized_names.add(tgt.id)
            # ``store = guard.protect(store)`` -> writes whose receiver is this name are screened.
            if _is_guard_protect_call(rhs):
                for tgt in node.targets:
                    if isinstance(tgt, ast.Name):
                        scope.protected_receivers.add(tgt.id)
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


def untrusted_leaf(write_value: ast.expr | None, scope: FunctionScope) -> ast.expr | None:
    """The specific sub-expression of ``write_value`` that carries the untrusted data, so a fix can
    screen *that leaf* and preserve the surrounding container shape.

    For a scalar untrusted value (``prompt``, ``state['x']``, an f-string of untrusted parts) this is
    ``write_value`` itself. For a structured container (``{'text': state['x']}``) it is the inner
    untrusted node (``state['x']``), so the generated fix writes ``{'text': verdict.content}`` rather
    than replacing the whole dict with a string. Returns None if no untrusted leaf resolves."""
    if write_value is None:
        return None
    return _leaf(write_value, scope, 0)


def _leaf(node: ast.expr, scope: FunctionScope, depth: int) -> ast.expr | None:
    if depth > 4:
        return None
    # A node that is itself an untrusted source (name/subscript/attr/call/f-string/concat) — screen
    # it whole. This keeps f-strings and concatenations intact (they evaluate to a string anyway).
    if _untrusted_label(node, scope) is not None:
        return node
    # A bare variable assigned from an untrusted source: screen the variable at the call site.
    if isinstance(node, ast.Name):
        assigned = scope.assignments.get(node.id)
        if assigned is not None and depth < 4 and _classify(assigned, scope, depth + 1) is not None:
            return node
        return None
    # A field read off an untrusted value (``result.user_preferences`` from an LLM ``invoke``;
    # ``state['email']['body']``) — screen the *whole* expression, not its inner receiver, so the
    # generated fix swaps THIS node for ``verdict.content`` (node-identity contract). Without it,
    # descent would return the inner ``result`` and produce a broken ``verdict.content.user_preferences``.
    if isinstance(node, (ast.Attribute, ast.Subscript)) and _classify(node, scope, depth + 1) is not None:
        return node
    # Structured/wrapper container: descend to the first untrusted leaf, preserving the container.
    for child in _child_exprs(node):
        found = _leaf(child, scope, depth + 1)
        if found is not None:
            return found
    return None


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
    # Attribute read (``result.user_preferences``) — follow the receiver, so a field read off a
    # variable assigned from an untrusted source (``result = llm.invoke(...)``) stays untrusted.
    # Subscript already propagates via ``_untrusted_label``; this closes the same gap for attributes.
    if isinstance(node, ast.Attribute):
        return [node.value]
    return []


# --- helpers ----------------------------------------------------------------------


def _all_args(func: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.arg]:
    a = func.args
    return [*a.posonlyargs, *a.args, *([a.vararg] if a.vararg else []), *a.kwonlyargs]


def _untrusted_params(func: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    """Parameter names untrusted-by-default for two specific, high-signal function shapes.

    * **CrewAI tool ``_run``/``_arun``** — a method on a class that subclasses a ``*Tool`` base;
      its parameters carry the scraped/fetched content the tool exists to retrieve.
    * **LangGraph node** — a function with a parameter named exactly ``state`` (the node signature)
      **in a module that imports ``langgraph``**; ``state`` then carries the incoming email/tool
      content the graph is processing. The import gate keeps an ordinary internal
      ``def persist(state): ...`` in a non-LangGraph app from being treated as untrusted.

    Deliberately narrow: this only re-scores *already-detected* sinks, never adds sink sites."""
    out: set[str] = set()
    params = [a.arg for a in _all_args(func)]
    # LangGraph node — exact ``state`` parameter, gated on a langgraph import in the module.
    if "state" in params and _module_imports_langgraph(func):
        out.add("state")
    # CrewAI tool _run — method whose enclosing class subclasses something named ``*Tool``.
    if func.name in ("_run", "_arun") and _enclosing_is_tool_subclass(func):
        out.update(p for p in params if p not in ("self", "cls"))
    return out


def _module_imports_langgraph(func: ast.AST) -> bool:
    """True if the module enclosing ``func`` imports ``langgraph`` — the framework gate for the
    LangGraph-node ``state`` heuristic. Uses the parent pointers the analyzer annotates; an
    un-annotated (hand-parsed) tree simply yields False."""
    mod = _root_module(func)
    if mod is None:
        return False
    for node in ast.walk(mod):
        if isinstance(node, ast.Import):
            if any(a.name.split(".")[0] == "langgraph" for a in node.names):
                return True
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".")[0] == "langgraph":
                return True
    return False


def _root_module(node: ast.AST) -> ast.Module | None:
    """Walk parent pointers to the enclosing :class:`ast.Module`, or None if not reachable."""
    cur: ast.AST | None = node
    seen = 0
    while cur is not None and seen < 200:
        if isinstance(cur, ast.Module):
            return cur
        cur = getattr(cur, "parent", None)
        seen += 1
    return None


def _enclosing_is_tool_subclass(func: ast.AST) -> bool:
    """True if ``func``'s nearest enclosing class has a base whose name contains ``Tool``
    (e.g. CrewAI ``BaseTool``). Relies on parent pointers annotated by the analyzer; absent
    parents (hand-parsed trees) simply yield False."""
    cur = getattr(func, "parent", None)
    while cur is not None:
        if isinstance(cur, ast.ClassDef):
            for base in cur.bases:
                if "tool" in (_attr_or_name(base) or "").lower():
                    return True
            return False
        cur = getattr(cur, "parent", None)
    return False


def _attr_or_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _untrusted_label(node: ast.expr, scope: FunctionScope) -> tuple[str, str] | None:
    """Return (source, human-note) if node reads an untrusted source, else None."""
    # Name matching an untrusted hint (param or var), or a param marked untrusted-by-shape
    # (CrewAI tool ``_run`` arg / LangGraph ``state``).
    if isinstance(node, ast.Name):
        n = node.id.lower()
        if node.id in scope.untrusted_params:
            # LangGraph ``state`` carries incoming (email/user) content; a CrewAI tool ``_run``
            # parameter carries scraped/fetched tool output.
            kind = "untrusted_input" if node.id == "state" else "tool_output"
            return (kind, f"untrusted param '{node.id}'")
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
    name = name.lower()
    return name in _SANITIZER_TOKENS or any(t in name for t in ("scan", "guard", "sanitize", "redact"))


def _is_guard_write_call(node: ast.expr) -> bool:
    """``guard.write(...)`` — the screening gate. Recognised by the ``guard`` *receiver* (its method
    is named ``write``). The assigned verdict is sanitized; a sink counts as screened only if it then
    uses it (``verdict.content``). This is what lets the inspect -> fix -> rescan loop close soundly:
    apply the suggested guard *and route the screened value to the write*, re-run, the lane flips."""
    return _is_guard_method_call(node, "write")


def _is_guard_protect_call(node: ast.expr) -> bool:
    """``guard.protect(store)`` — wraps a store so its writes are screened. The wrapped receiver name
    is recorded; a write through it counts as screened (a write to a different store does not)."""
    return _is_guard_method_call(node, "protect")


def _is_guard_method_call(node: ast.expr, method: str) -> bool:
    if not isinstance(node, ast.Call):
        return False
    fn = node.func
    return (
        isinstance(fn, ast.Attribute)
        and fn.attr.lower() == method
        and "guard" in _receiver_tokens(fn.value)
    )


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


__all__ = ["FunctionScope", "TaintResult", "analyze", "build_scope", "untrusted_leaf"]
