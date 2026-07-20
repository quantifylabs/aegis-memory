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

# Callables whose return value is untrusted (network / file / tool / LLM egress). Split into two
# tiers so a plain ``dict.get(...)`` / ``config.get(...)`` / ``model.run(...)`` isn't mistaken for
# network egress (the corpus surfaced ``reflection.get("insight")`` flagged purely on the verb):
#   * STRONG — distinctive egress verbs unlikely to be an innocent local method; fire on any receiver.
#   * WEAK   — common verbs that are usually local; fire ONLY on a known network/IO/tool receiver.
_UNTRUSTED_CALL_METHODS_STRONG = (
    "fetch",
    "read_text",
    "invoke",
    "complete",
    # Streamlit user-input widgets — the value typed by an end user is untrusted.
    "chat_input",
    "text_input",
    "text_area",
)
_UNTRUSTED_CALL_METHODS_WEAK = (
    "get",
    "post",
    "read",
    "load",
    "run",
    "call",
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
    # Parameter name -> source kind ("untrusted_input" | "tool_output") for params that are
    # untrusted-by-default for this function shape: a LangGraph node's ``state`` (incoming
    # email/tool content), a CrewAI ``BaseTool._run`` arg (scraped/fetched output), and a
    # LangChain/LangGraph tool function's model-supplied args. Specific shapes only — never blanket.
    untrusted_params: dict[str, str] = field(default_factory=dict)
    # name -> the value expression last assigned to it (best effort, top-level body)
    assignments: dict[str, ast.expr] = field(default_factory=dict)
    # variable names that flowed through a sanitizer call somewhere in the scope
    sanitized_names: set[str] = field(default_factory=set)
    # receiver names wrapped by ``guard.protect(...)`` — a write *through* one is screened (sink-tied)
    protected_receivers: set[str] = field(default_factory=set)
    # variable names passed *into* a generic scanner/sanitizer call in this scope (``scanner.scan(x)``
    # -> {"x"}). A write is screened by such a scan only if its untrusted leaf shares one of these
    # names — the gate-then-write idiom (scan the value, write it if allowed). This is sink-tied: a
    # ``scan(other)`` of an unrelated value never screens a raw write of ``request.body``. The guard
    # idiom (``guard.write``/``guard.protect``) is deliberately NOT collected here — it screens via
    # sanitized_names / protected_receivers, so discarding its verdict and writing raw is never green.
    scanned_value_names: set[str] = field(default_factory=set)


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
        # A generic scanner/sanitizer call anywhere in scope (``scanner.scan(summary)``) — record the
        # variable names it screened, so a later write of one of those values counts as screened. The
        # guard idiom is excluded by ``_is_sanitizer_call`` (it returns sanitized content to use).
        if isinstance(node, ast.Call) and _is_sanitizer_call(node):
            for arg in (*node.args, *(kw.value for kw in node.keywords)):
                scope.scanned_value_names |= _expr_names(arg)
    return scope


_CONF_RANK = {"EXTRACTED": 3, "INFERRED": 2, "AMBIGUOUS": 1}


def analyze(write_value: ast.expr | None, scope: FunctionScope) -> TaintResult:
    """Classify the trust of the value being written by a sink call.

    Recurses through containers (dict/list/tuple/f-string/concat) that wrap the value, and
    follows a single variable hop into its in-scope assignment. The strongest evidence wins.
    """
    if write_value is None:
        # Value couldn't be resolved — we cannot claim it was screened.
        return TaintResult("unknown", "unknown", "AMBIGUOUS", False)

    screened = _value_screened(write_value, scope)
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
    # Field read off a variable — follow the receiver so a value assigned from an untrusted source
    # (``result = llm.invoke(...)``) stays untrusted whether the field is read by attribute
    # (``result.user_preferences``) or subscript (``result["user_preferences"]`` — chains return
    # dict-shaped data too). We follow only the receiver (``node.value``), never the index/slice.
    if isinstance(node, (ast.Attribute, ast.Subscript)):
        return [node.value]
    return []


# --- helpers ----------------------------------------------------------------------


def _all_args(func: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.arg]:
    a = func.args
    return [*a.posonlyargs, *a.args, *([a.vararg] if a.vararg else []), *a.kwonlyargs]


def _untrusted_params(func: ast.FunctionDef | ast.AsyncFunctionDef) -> dict[str, str]:
    """Parameter name -> source kind for three specific, high-signal function shapes.

    * **LangGraph node** — a function with a parameter named exactly ``state`` (the node signature)
      **in a module that imports ``langgraph``**; ``state`` carries the incoming email/tool content
      the graph is processing (``untrusted_input``). The import gate keeps an ordinary internal
      ``def persist(state): ...`` in a non-LangGraph app from being treated as untrusted.
    * **CrewAI tool ``_run``/``_arun``** — a method on a class that subclasses a ``*Tool`` base; its
      parameters carry the scraped/fetched content the tool exists to retrieve (``tool_output``).
    * **LangChain/LangGraph tool function** — a function the model calls with model-supplied
      arguments (``@tool``-decorated, or carrying an ``Injected*`` runtime param). Its non-injected
      params are model/user-derived (``untrusted_input``); the injected params (state/store/config/
      runtime) are framework-populated and excluded. This is the canonical ``upsert_memory(content,
      …)`` shape that writes a tool arg straight into long-term memory.

    Deliberately narrow: this only re-scores *already-detected* sinks, never adds sink sites."""
    out: dict[str, str] = {}
    params = [a.arg for a in _all_args(func)]
    # LangGraph node — exact ``state`` parameter, gated on a langgraph import in the module.
    if "state" in params and _module_imports(func, ("langgraph",)):
        out["state"] = "untrusted_input"
    # CrewAI tool _run — method whose enclosing class subclasses something named ``*Tool``.
    if func.name in ("_run", "_arun") and _enclosing_is_tool_subclass(func):
        for p in params:
            if p not in ("self", "cls"):
                out.setdefault(p, "tool_output")
    # LangChain/LangGraph tool function — model-supplied args are untrusted; injected args are not.
    if _is_langchain_tool(func):
        for a in _all_args(func):
            if a.arg in ("self", "cls") or _is_injected_param(a):
                continue
            out.setdefault(a.arg, "untrusted_input")
    return out


# Annotation markers for framework-injected (non-model) tool params — these are populated at runtime
# and hidden from the model, so they are NOT the untrusted, model-supplied arguments.
_INJECTED_MARKERS = (
    "injectedtoolarg",
    "injectedstate",
    "injectedstore",
    "injectedtoolcallid",
    "runnableconfig",
    "toolruntime",
)


def _is_injected_param(arg: ast.arg) -> bool:
    """True if ``arg``'s annotation references a LangChain/LangGraph injected marker (e.g.
    ``Annotated[str, InjectedToolArg]`` / ``state: Annotated[dict, InjectedState]``). Walks the whole
    annotation so the marker is found whether it sits bare or inside an ``Annotated[...]``."""
    ann = arg.annotation
    if ann is None:
        return False
    for node in ast.walk(ann):
        name = _attr_or_name(node) if isinstance(node, (ast.Name, ast.Attribute)) else None
        if name and name.lower() in _INJECTED_MARKERS:
            return True
    return False


def _is_langchain_tool(func: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """True if ``func`` is a LangChain/LangGraph tool — a function the model calls with model-supplied
    arguments. Gated on a langchain/langgraph import, then recognised by either an explicit ``@tool``
    decorator (``@tool`` / ``@tool("name")`` / ``langchain_core.tools.tool`` / an aliased
    ``from ...tools import tool as lc_tool`` -> ``@lc_tool``) or the presence of an ``Injected*``
    runtime param (a near-certain signal the function is exposed to the model as a tool). The import
    gate keeps a plain ``def run(query): ...`` in an unrelated module from qualifying."""
    if not _module_imports(func, ("langchain", "langchain_core", "langgraph")):
        return False
    aliases = _tool_decorator_aliases(func)
    for dec in func.decorator_list:
        target = dec.func if isinstance(dec, ast.Call) else dec
        name = _attr_or_name(target)
        if name and (name.lower() == "tool" or name in aliases):
            return True
    return any(_is_injected_param(a) for a in _all_args(func))


def _tool_decorator_aliases(func: ast.AST) -> set[str]:
    """Local names bound to the LangChain/LangGraph ``tool`` decorator in the enclosing module,
    including import aliases (``from langchain_core.tools import tool as lc_tool`` -> ``{"lc_tool"}``).
    Without this an aliased ``@lc_tool`` would not match the bare ``tool`` name and the tool's
    model-supplied args would be left unknown (downgrading a real tool-arg→memory flow to low)."""
    mod = _root_module(func)
    if mod is None:
        return set()
    out: set[str] = set()
    for node in ast.walk(mod):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".")[0] in ("langchain", "langchain_core", "langgraph"):
                for a in node.names:
                    if a.name == "tool":
                        out.add(a.asname or a.name)
    return out


def _module_imports(func: ast.AST, roots: tuple[str, ...]) -> bool:
    """True if the module enclosing ``func`` imports any of ``roots`` (top-level package name) — the
    framework gate for the shape heuristics (LangGraph ``state``, LangChain/LangGraph tool args). Uses
    the parent pointers the analyzer annotates; an un-annotated (hand-parsed) tree simply yields False."""
    mod = _root_module(func)
    if mod is None:
        return False
    for node in ast.walk(mod):
        if isinstance(node, ast.Import):
            if any(a.name.split(".")[0] in roots for a in node.names):
                return True
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".")[0] in roots:
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
            # Source kind is recorded per-param by the shape that marked it (LangGraph ``state`` and
            # LangChain tool args -> untrusted_input; CrewAI ``_run`` args -> tool_output).
            kind = scope.untrusted_params.get(node.id, "untrusted_input")
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
        if isinstance(fn, ast.Attribute):
            m = fn.attr.lower()
            # Tokens across the whole receiver (``self.client.get`` -> {self, client}) so a network
            # receiver is recognised however it is referenced — not just the dotted root.
            recv_tokens = _receiver_tokens(fn.value)
            on_egress_receiver = bool(recv_tokens & set(_UNTRUSTED_CALL_RECEIVERS))
            # STRONG verb fires anywhere; WEAK verb only on a known network/IO/tool receiver.
            if m in _UNTRUSTED_CALL_METHODS_STRONG or (
                m in _UNTRUSTED_CALL_METHODS_WEAK and on_egress_receiver
            ):
                kind = "tool_output" if ({"tool", "client"} & recv_tokens) else "untrusted_input"
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


def _unwrap_await(node: ast.expr) -> ast.expr:
    """``await f(x)`` -> ``f(x)``.

    ``await`` changes when a call runs, never whether it screens. Without this, every recognizer
    below silently fails on async code: ``verdict = await scanner.scan_async(x)`` parses as an
    ``ast.Await`` wrapping the ``ast.Call``, the ``isinstance(node, ast.Call)`` guards return
    False, and the verdict is never recorded as sanitized. Async is the dominant idiom for agent
    servers, so the effect was that a correctly-screened async write still reported
    "no injection screening detected" -- including on Aegis's own ``add_memory``.
    """
    while isinstance(node, ast.Await):
        node = node.value
    return node


def _is_sanitizer_call(node: ast.expr) -> bool:
    node = _unwrap_await(node)
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
    node = _unwrap_await(node)
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


def _assigned_from_sanitized(node: ast.expr, scope: FunctionScope, depth: int = 0) -> bool:
    """Does this expression read a variable assigned (transitively) from a sanitizer's output?

    Follows ``ast.Name -> its assignment`` hops, bounded like ``_classify``, and reports True only
    when a hop lands on a name in ``scope.sanitized_names``. Bounded depth also terminates the
    ``a = a`` / mutual-assignment cases rather than recursing forever.
    """
    if depth > 4:
        return False
    for name_node in (n for n in ast.walk(node) if isinstance(n, ast.Name)):
        if name_node.id in scope.sanitized_names:
            return True
        assigned = scope.assignments.get(name_node.id)
        if assigned is not None and _assigned_from_sanitized(assigned, scope, depth + 1):
            return True
    return False


def _value_screened(write_value: ast.expr, scope: FunctionScope) -> bool:
    """Is the written value's untrusted data actually screened? **Sink-tied, never blanket.**

    Screening is tied to the *untrusted leaf of this write*, not to any sanitizer call that happens
    to appear elsewhere in the function. This is what keeps an unrelated ``scanner.scan(other)`` —
    or a *discarded* ``guard.write(req.json)`` whose verdict is never used — from green-lighting a
    raw untrusted write in the same scope (the worst error class: a false "screened").

    A write counts as screened when its untrusted leaf is:
      * read from a variable assigned by a sanitizer / ``guard.write`` (``v = guard.write(x); put(
        v.content)``; ``clean = sanitize(x); put(clean)``) — via ``scope.sanitized_names``; or
      * a value a generic scanner screened in this scope (``scan(summary); put({"text": summary})``)
        — its name overlaps ``scope.scanned_value_names``; or
      * enclosed by a sanitizer / ``guard.write`` call *within the written value itself*
        (inline ``put(sanitize(x))``).
    """
    leaf = untrusted_leaf(write_value, scope)
    names = _expr_names(leaf) if leaf is not None else _expr_names(write_value)
    # Leaf read from a guard verdict / assigned-from-sanitizer variable, or a value a scanner in this
    # scope screened. Both are sink-tied to a variable this write's untrusted leaf actually uses.
    if names & (scope.sanitized_names | scope.scanned_value_names):
        return True
    # The leaf may be a plain variable holding the screened value one hop back
    # (``content_to_store = verdict.content; add(content=content_to_store)``) -- the shape almost
    # every real handler uses, and the one Aegis's own add_memory uses.
    #
    # Deliberately narrower than the check above: this follows assignments only into
    # ``sanitized_names`` (a value *returned by* a sanitizer or ``guard.write``, which is proven
    # screened output), never into ``scanned_value_names`` (merely a name that appeared as a
    # scanner *argument* somewhere in scope). Widening the loose heuristic across assignment hops
    # is how an unrelated ``scan(other)`` would start green-lighting raw writes -- a false
    # "screened", the worst error this analyzer can make.
    if _assigned_from_sanitized(leaf if leaf is not None else write_value, scope):
        return True
    # Inline sanitizer / guard.write wrapping *this* leaf within the written value.
    if leaf is not None:
        for node in ast.walk(write_value):
            if (_is_sanitizer_call(node) or _is_guard_write_call(node)) and any(
                sub is leaf for sub in ast.walk(node)
            ):
                return True
    return False


__all__ = ["FunctionScope", "TaintResult", "analyze", "build_scope", "untrusted_leaf"]
