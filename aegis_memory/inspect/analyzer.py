"""The static analysis engine. Walks a project with Python's ``ast``, matches memory-
write sinks (``sinks.py``), runs the same-scope taint check (``taint.py``), and emits
location-anchored :class:`Finding` objects.

General, never demo-tuned: the only inputs are the documented sink shapes and source
hints. No rule keys off any demo filename or string.
"""

from __future__ import annotations

import ast
import io
import re
import tokenize
from collections.abc import Iterator
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import cast

from . import bindings, fixgen, interproc, notebooks, sinks, taint
from .findings import Category, Finding, Sink

# Inline suppression: ``# aegis: ignore`` on (or directly above) a sink call drops its findings, so a
# reviewed/accepted sink can be silenced without churn. An optional reason may follow (``# aegis:
# ignore - trusted internal seed``). Matched on real COMMENT tokens, never inside a string literal.
_SUPPRESS_RE = re.compile(r"#\s*aegis:\s*ignore\b", re.IGNORECASE)

# Directories we never descend into.
_SKIP_DIRS = {
    ".git",
    ".hg",
    "__pycache__",
    "aegis-out",
    "node_modules",
    ".venv",
    "venv",
    "env",
    ".env",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".ipynb_checkpoints",
    "build",
    "dist",
    ".tox",
    "site-packages",
}

# Keyword arg names that commonly carry the written value.
_VALUE_KWARGS = ("value", "content", "data", "text", "texts", "documents", "memory", "messages", "item")

# Memory-read calls (for the read-path / provenance heuristic).
_READ_METHODS = ("get", "aget", "search", "asearch", "query")
_READ_RECEIVER_HINTS = ("store", "memory", "checkpointer", "saver", "index", "collection", "vectorstore")

# Prompt-ish tokens that indicate memory re-entering a model prompt.
_PROMPT_TOKENS = ("prompt", "messages", "system", "invoke", "complete", "chat", "llm")

_PROVENANCE_TOKENS = ("provenance", "source", "trust", "origin", "metadata")


@dataclass
class _SinkSite:
    file: str
    line: int
    match: sinks.SinkMatch
    taint: taint.TaintResult
    namespace_shared: bool
    key: str | None = None  # literal memory key when statically known
    # AST context kept for the bounded interprocedural resolver (taint across functions/files).
    call: ast.Call | None = None
    func: ast.FunctionDef | ast.AsyncFunctionDef | None = None
    write_value: ast.expr | None = None
    # The untrusted *leaf* within ``write_value`` (e.g. ``state['x']`` inside ``{'text': state['x']}``),
    # so the generated fix screens that leaf and preserves the written container's shape.
    write_leaf: ast.expr | None = None
    flow_path: list[dict] = field(default_factory=list)


def analyze_project(root: str | Path, framework: str | None = None) -> list[Finding]:
    """Analyze every ``.py`` file under ``root`` and return sorted, id-assigned findings.

    Two passes: parse every module and build a project-wide :class:`interproc.ProjectIndex`, then
    scan sinks. Each sink's written value is resolved same-scope first; when that is inconclusive,
    the bounded interprocedural resolver follows the value across function/file boundaries."""
    root = Path(root).resolve()
    modules: list[tuple[str, ast.Module]] = []
    # rel -> (all ``# aegis: ignore`` lines, standalone-marker lines)
    suppressed: dict[str, tuple[set[int], set[int]]] = {}
    for path in _iter_source_files(root):
        if path.suffix == ".ipynb":
            tree = notebooks.load_notebook(path)
            if tree is None:
                continue
            rel = _rel(path, root)
        else:
            try:
                source = path.read_text(encoding="utf-8")
                tree = ast.parse(source, filename=str(path))
            except (SyntaxError, UnicodeDecodeError):
                continue
            rel = _rel(path, root)
            suppressed[rel] = _suppressed_lines(source)
        _annotate_parents(tree)
        modules.append((rel, tree))

    index = interproc.ProjectIndex.build(modules)
    # Constructor-resolved receiver->library bindings (Batch B): recover aliased-receiver sinks
    # (m.add / self.warm.put) the name-hint catalog misses, without widening the substring hints.
    receiver_bindings = bindings.ReceiverBindings.build(modules)

    sites: list[_SinkSite] = []
    read_flows: list[tuple[str, int, str, str]] = []
    for rel, tree in modules:
        sites.extend(_scan_module(tree, rel, receiver_bindings))
        read_flows.extend(_scan_read_paths(tree, rel))

    # Resolve each sink's source — same-scope, then bounded interprocedural/cross-file. A resolved
    # untrusted source upgrades the (possibly internal/unknown) same-scope verdict and records the
    # source->sink edge; an unresolved sink is left structural (never dropped).
    for s in sites:
        res = interproc.resolve_sink(s.write_value, s.func, s.file, index, screened=s.taint.screened)
        if res is not None:
            s.taint = res.taint
            s.flow_path = res.flow_path

    # Inline suppression (``# aegis: ignore``): drop sinks and read-flows the author has accepted.
    sites = [s for s in sites if not _site_suppressed(s, suppressed)]
    read_flows = [rf for rf in read_flows if not _line_suppressed(rf[0], rf[1], suppressed)]

    findings = _build_findings(sites, read_flows, framework)
    return findings


def _suppressed_lines(source: str) -> tuple[set[int], set[int]]:
    """Find ``# aegis: ignore`` markers. Returns ``(all_marker_lines, standalone_marker_lines)``.

    Matched on real COMMENT tokens so the marker is never honoured inside a string literal. A
    *standalone* marker (a comment alone on its line) applies to the statement directly below it; an
    *inline* marker (trailing code) applies only to that statement — this split keeps an inline marker
    on one sink from leaking onto the next line's sink. Falls back to a line scan if the source can't
    be tokenized (e.g. a fragment), staying best-effort rather than failing the whole analysis."""
    all_marks: set[int] = set()
    standalone: set[int] = set()

    def _record(lineno: int, line_text: str) -> None:
        all_marks.add(lineno)
        if line_text.lstrip().startswith("#"):
            standalone.add(lineno)

    try:
        for tok in tokenize.generate_tokens(io.StringIO(source).readline):
            if tok.type == tokenize.COMMENT and _SUPPRESS_RE.search(tok.string):
                _record(tok.start[0], tok.line)
    except (tokenize.TokenError, IndentationError, SyntaxError, ValueError):
        for i, line in enumerate(source.splitlines(), start=1):
            if _SUPPRESS_RE.search(line):
                _record(i, line)
    return all_marks, standalone


def _line_suppressed(rel: str, line: int, suppressed: dict[str, tuple[set[int], set[int]]]) -> bool:
    """A finding anchored to ``line`` is suppressed by an inline/any marker on that line, or by a
    *standalone* marker on the line directly above it."""
    marks = suppressed.get(rel)
    if not marks:
        return False
    all_marks, standalone = marks
    return line in all_marks or (line - 1) in standalone


def _site_suppressed(s: _SinkSite, suppressed: dict[str, tuple[set[int], set[int]]]) -> bool:
    """A sink is suppressed by an ``# aegis: ignore`` anywhere within its (possibly multi-line) call
    span, or by a *standalone* marker on the line directly above the call."""
    marks = suppressed.get(s.file)
    if not marks:
        return False
    all_marks, standalone = marks
    start = getattr(s.call, "lineno", s.line)
    end = getattr(s.call, "end_lineno", start) or start
    return any(start <= n <= end for n in all_marks) or (start - 1) in standalone


# --- module scan -------------------------------------------------------------------


def _scan_module(tree: ast.Module, rel: str, receiver_bindings: bindings.ReceiverBindings) -> list[_SinkSite]:
    """Visit each Call once, scoped to its nearest enclosing function (no double-count)."""
    out: list[_SinkSite] = []
    scope_cache: dict[int, taint.FunctionScope] = {}
    framework_hint = _module_framework(tree)
    for call in ast.walk(tree):
        if not isinstance(call, ast.Call):
            continue
        func = _enclosing_function(call)
        # Resolve the receiver to a memory constructor (Batch B). Supplies the binding that recovers
        # aliased receivers and upgrades the label; None leaves the name-hint tiers in charge.
        binding = None
        if isinstance(call.func, ast.Attribute):
            receiver = _receiver_string(call.func.value)
            binding = receiver_bindings.resolve(rel, func, _enclosing_class(call), receiver)
        match = _match_call(call, binding)
        if match is None:
            continue
        # Label-only refinement: when the receiver did NOT bind, a generic sink in a module that
        # clearly imports a known memory library is still attributed to it (Batch-A heuristic, e.g.
        # ``custom`` -> ``mem0``). A bound receiver already carries the precise label from the binding.
        if binding is None and framework_hint and match.framework in ("custom", "vectordb"):
            match = replace(match, framework=framework_hint)
        if func is None:
            scope = taint.FunctionScope(func=_EMPTY_FUNC)
        else:
            scope = scope_cache.get(id(func)) or taint.build_scope(func)
            scope_cache[id(func)] = scope
        value = _write_value(call)
        tr = taint.analyze(value, scope)
        leaf = taint.untrusted_leaf(value, scope)
        # ``store = guard.protect(store)`` in this scope screens writes *through that receiver*
        # (sink-tied — a write to a different, unprotected store is left exposed).
        if not tr.screened and isinstance(call.func, ast.Attribute):
            recv_root = _root_name(call.func.value)
            if recv_root and recv_root in scope.protected_receivers:
                tr.screened = True
        out.append(
            _SinkSite(
                file=rel,
                line=getattr(call, "lineno", 0),
                match=match,
                taint=tr,
                namespace_shared=_writes_shared_scope(call),
                key=_write_key(call),
                call=call,
                func=func,
                write_value=value,
                write_leaf=leaf,
            )
        )
    return out


# Top-level import roots that attribute a module's generic memory sinks to a known library.
_FRAMEWORK_IMPORTS = {
    "mem0": "mem0",
    "embedchain": "embedchain",
    "crewai": "crewai",
    "crewai_tools": "crewai",
}


def _module_framework(tree: ast.Module) -> str | None:
    """A framework label inferred from the module's imports, or None. Label-only (Fix 4) — a
    lightweight stand-in for receiver->library binding (deferred to Batch B)."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in _FRAMEWORK_IMPORTS:
                    return _FRAMEWORK_IMPORTS[root]
        elif isinstance(node, ast.ImportFrom) and node.module:
            root = node.module.split(".")[0]
            if root in _FRAMEWORK_IMPORTS:
                return _FRAMEWORK_IMPORTS[root]
    return None


def _match_call(call: ast.Call, binding: sinks.BindingInfo | None = None) -> sinks.SinkMatch | None:
    fn = call.func
    kwargs = tuple(kw.arg for kw in call.keywords if kw.arg)
    if isinstance(fn, ast.Attribute):
        # Use the dotted receiver path (e.g. "self.memory_store") so hint matching sees
        # the meaningful attribute name, not just the root object.
        receiver = _receiver_string(fn.value)
        return sinks.classify_call(
            attr=fn.attr, func=None, receiver=receiver, keywords=kwargs, binding=binding
        )
    if isinstance(fn, ast.Name):
        return sinks.classify_call(attr=None, func=fn.id, receiver=None, keywords=kwargs)
    return None


def _receiver_string(node: ast.expr) -> str | None:
    """Dotted receiver path, e.g. ``self.memory_store`` or ``store``."""
    parts: list[str] = []
    cur: ast.expr | None = node
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        parts.append(cur.id)
    elif isinstance(cur, ast.Call):
        inner = _receiver_string(cur.func)
        if inner:
            parts.append(inner)
    return ".".join(reversed(parts)) if parts else None


def _write_value(call: ast.Call) -> ast.expr | None:
    """Best-effort extraction of the *written* value from a sink call's args."""
    # Keyword args take priority when named like a value carrier.
    for kw in call.keywords:
        if kw.arg and kw.arg.lower() in _VALUE_KWARGS:
            return kw.value
    if not call.args:
        return None
    # BaseStore.put(namespace, key, value) -> value is the 3rd positional.
    fn = call.func
    if isinstance(fn, ast.Attribute) and fn.attr in ("put", "aput") and len(call.args) >= 3:
        return call.args[2]
    # add_messages(left, right) -> the appended messages are the last positional.
    if isinstance(fn, ast.Name) and fn.id == "add_messages":
        return call.args[-1]
    # Default: first positional carries the content for add/upsert/save/etc.
    return call.args[0]


def _write_key(call: ast.Call) -> str | None:
    """Best-effort: the literal memory key a write targets, when it's a string constant.

    ``store.put(namespace, key, value)`` / ``checkpointer.put(cfg, key, value)`` carry the key
    as the 2nd positional; some sinks name it ``key=``. Non-literal keys return ``None`` — the
    trace then renders a generic memory node rather than asserting a key it can't prove."""
    for kw in call.keywords:
        if kw.arg == "key" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
            return kw.value.value
    fn = call.func
    if isinstance(fn, ast.Attribute) and fn.attr in ("put", "aput") and len(call.args) >= 2:
        second = call.args[1]
        if isinstance(second, ast.Constant) and isinstance(second.value, str):
            return second.value
    return None


def _writes_shared_scope(call: ast.Call) -> bool:
    """Does this write target a shared/global namespace? **Tied to the scope/namespace argument**,
    never to an arbitrary string constant anywhere in the call. The old version matched any literal
    containing ``shared``/``global``, so a benign ``key="shared_calendar"`` or ``value="all done"``
    minted a spurious overbroad-shared-access finding. We look only where scope is actually declared:
    a ``scope=``/``shared_with_agents=`` keyword, or the namespace argument of a ``put``/``aput``."""

    def _is_shared_literal(node: ast.expr) -> bool:
        for n in ast.walk(node):
            if isinstance(n, ast.Constant) and isinstance(n.value, str):
                v = n.value.lower()
                if "shared" in v or "global" in v or v in ("public", "all-agents", "everyone"):
                    return True
        return False

    def _is_empty_or_none(node: ast.expr) -> bool:
        # An empty literal collection (``[]``/``()``/``{}``) or ``None`` — not a shared write. A
        # non-literal (a variable / call) is treated as possibly-shared and left to flag conservatively.
        if isinstance(node, ast.Constant) and node.value is None:
            return True
        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            return not node.elts
        if isinstance(node, ast.Dict):
            return not node.keys
        return False

    for kw in call.keywords:
        # A *non-empty* shared-with list is a shared write. An explicit ``shared_with_agents=[]``
        # (or ``=None``) means the memory is NOT shared, so it must not flag overbroad access.
        if kw.arg == "shared_with_agents" and not _is_empty_or_none(kw.value):
            return True
        # scope="agent-shared" / scope="global" — the declared write scope.
        if kw.arg in ("scope", "namespace") and _is_shared_literal(kw.value):
            return True
    # LangGraph ``store.put(namespace, key, value)`` — the namespace is the 1st positional.
    fn = call.func
    if isinstance(fn, ast.Attribute) and fn.attr in ("put", "aput") and call.args:
        if _is_shared_literal(call.args[0]):
            return True
    return False


# --- read-path / provenance heuristic ----------------------------------------------


def _read_framework(recv: str) -> str:
    """Map a memory-read receiver name to its framework label, so a provenance finding reflects the
    real store (a Chroma/mem0 read isn't mislabeled as a LangGraph ``store.get``). Vector-store
    receivers win first; checkpointer/saver/``*store*`` are LangGraph; anything else is custom."""
    if any(h in recv for h in ("index", "collection", "vectorstore")):
        return "vectordb"
    if any(h in recv for h in ("checkpointer", "saver")) or "store" in recv:
        return "langgraph"
    return "custom"


def _identifier_tokens(func: ast.AST) -> str:
    """Lowercased identifier/attribute/argument names in a function — NOT string-literal contents.

    The provenance heuristic must key off code structure, not text: the old ``ast.dump(func)`` folded
    in every string constant, so a docstring or a literal containing ``source`` falsely satisfied the
    provenance check (a false negative), and a literal containing ``prompt`` falsely tripped it. We
    look only at identifiers a programmer actually named (``Name``/``Attribute``/``arg``/keyword/def)."""
    parts: list[str] = []
    for node in ast.walk(func):
        if isinstance(node, ast.Name):
            parts.append(node.id)
        elif isinstance(node, ast.Attribute):
            parts.append(node.attr)
        elif isinstance(node, ast.arg):
            parts.append(node.arg)
        elif isinstance(node, ast.keyword) and node.arg:
            parts.append(node.arg)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            parts.append(node.name)
    return " ".join(parts).lower()


def _scan_read_paths(tree: ast.Module, rel: str) -> list[tuple[str, int, str, str]]:
    """Find memory reads that feed a prompt without provenance, scoped to the read's nearest
    enclosing function (deduped by location). Returns ``(file, line, framework, call)`` so the
    finding names the real store rather than a hardcoded LangGraph ``store.get``."""
    seen: set[tuple[str, int]] = set()
    out: list[tuple[str, int, str, str]] = []
    tok_cache: dict[int, str] = {}
    for call in ast.walk(tree):
        if not isinstance(call, ast.Call):
            continue
        fn = call.func
        if not (isinstance(fn, ast.Attribute) and fn.attr.lower() in _READ_METHODS):
            continue
        recv = (_root_name(fn.value) or "").lower()
        if not any(h in recv for h in _READ_RECEIVER_HINTS):
            continue
        func = _enclosing_function(call)
        if func is None:
            continue
        tokens = tok_cache.get(id(func))
        if tokens is None:
            tokens = _identifier_tokens(func)
            tok_cache[id(func)] = tokens
        prompt_used = any(t in tokens for t in _PROMPT_TOKENS)
        has_provenance = any(t in tokens for t in _PROVENANCE_TOKENS)
        loc = (rel, getattr(call, "lineno", 0))
        if prompt_used and not has_provenance and loc not in seen:
            seen.add(loc)
            out.append((rel, getattr(call, "lineno", 0), _read_framework(recv), f"{recv}.{fn.attr}"))
    return out


# --- finding construction ----------------------------------------------------------


def _build_findings(
    sites: list[_SinkSite], read_flows: list[tuple[str, int, str, str]], framework: str | None
) -> list[Finding]:
    raw: list[Finding] = []

    for s in sites:
        if framework and s.match.framework not in (framework, "custom", "vectordb", "aegis"):
            # Explicit --framework filters to that adapter (+ generic fallbacks).
            if s.match.framework != framework:
                continue
        sink = Sink(file=s.file, line=s.line, framework=s.match.framework, call=s.match.call, key=s.key)
        tr = s.taint

        if tr.trust == "untrusted":
            # Headline flow finding.
            is_tool = tr.source == "tool_output"
            category = (
                Category.TOOL_OUTPUT_TO_MEMORY.value if is_tool else Category.USER_INPUT_TO_MEMORY.value
            )
            severity = "critical" if not tr.screened else "low"
            title = (
                f"{'Tool output' if is_tool else 'Untrusted input'} written to "
                f"{'shared ' if s.namespace_shared else ''}memory via {s.match.call}"
            )
            if tr.screened:
                title = f"Screened {title[0].lower()}{title[1:]}"
            notes = list(tr.notes)
            if tr.screened:
                notes.append("a content-security guard wraps this write (screened flow)")
            else:
                notes.append("no injection screening detected at this site before the write")
            raw.append(
                Finding(
                    id="",
                    severity=severity,
                    confidence=tr.confidence,
                    category=category,
                    sink=sink,
                    source=("tool_output" if is_tool else "untrusted_input"),
                    trust="untrusted",
                    title=title,
                    fix=fixgen.build_flow_fix(
                        s.call,
                        s.write_value,
                        screen_value=s.write_leaf,
                        scope="agent-shared" if s.namespace_shared else "agent-private",
                        trust="untrusted",
                    ),
                    screened=tr.screened,
                    notes=notes,
                    owasp="ASI06",  # OWASP ASI06 — Memory & Context Poisoning
                    flow_path=list(s.flow_path),
                )
            )
            # Absence finding: missing injection screening before an untrusted write.
            if not tr.screened:
                raw.append(
                    Finding(
                        id="",
                        severity="medium",
                        confidence="INFERRED",
                        category=Category.MISSING_INJECTION_SCREENING.value,
                        sink=sink,
                        source=("tool_output" if is_tool else "untrusted_input"),
                        trust="untrusted",
                        title=f"No injection screening detected at this site before {s.match.call}",
                        fix="Screen the value with ContentSecurityScanner.scan() before writing.",
                        screened=False,
                        notes=["absence: not detected at this site (not a claim that none exists)"],
                    )
                )
        else:
            # Structural sink: report it as a memory-write site (low severity).
            cat = (
                Category.VECTOR_DB_WRITE.value
                if s.match.category == Category.VECTOR_DB_WRITE.value
                else Category.MEMORY_WRITE.value
            )
            raw.append(
                Finding(
                    id="",
                    severity="low",
                    confidence=s.match.base_confidence,
                    category=cat,
                    sink=sink,
                    source=tr.source,
                    trust=tr.trust,
                    title=f"Memory write sink: {s.match.call}",
                    fix="Confirm the written value's trust level; route untrusted content through the guard.",
                    screened=tr.screened,
                    notes=[
                        "Looks like a memory write, but I couldn't tell where the stored data "
                        "comes from (source not resolved within the bounded search — best-effort, "
                        "not proof the value is safe)."
                    ],
                )
            )
        # Over-broad shared/global access (absence/structural).
        if s.namespace_shared:
            raw.append(
                Finding(
                    id="",
                    severity="medium" if tr.trust == "untrusted" else "low",
                    confidence="INFERRED",
                    category=Category.OVERBROAD_SHARED_ACCESS.value,
                    sink=sink,
                    source=tr.source,
                    trust=tr.trust,
                    title=f"Write targets shared/global memory scope via {s.match.call}",
                    fix="Restrict scope or require approval for shared/global writes.",
                    screened=tr.screened,
                    notes=["absence: shared-scope governance not detected at this site"],
                )
            )

    for rel, line, fw, call_label in read_flows:
        raw.append(
            Finding(
                id="",
                severity="low",
                confidence="AMBIGUOUS",
                category=Category.MISSING_PROVENANCE.value,
                sink=Sink(file=rel, line=line, framework=fw, call=call_label),
                source="unknown",
                trust="unknown",
                title="Memory re-enters a prompt without provenance metadata",
                fix="Attach provenance/trust metadata to loaded memory before prompting.",
                screened=False,
                notes=["absence: provenance not detected at this site"],
            )
        )

    return _assign_ids(raw)


def _assign_ids(findings: list[Finding]) -> list[Finding]:
    # Deterministic order: severity rank, then file, line, category.
    rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    findings.sort(key=lambda f: (rank.get(f.severity, 9), f.sink.file, f.sink.line, f.category))
    for i, f in enumerate(findings, start=1):
        f.id = f"AEG-{i:03d}"
    return findings


# --- ast utilities -----------------------------------------------------------------


def _iter_source_files(root: Path) -> Iterator[Path]:
    """Python source and Jupyter notebooks, skipping vendored/output dirs. Sorted for determinism."""
    for path in sorted(root.rglob("*.py")) + sorted(root.rglob("*.ipynb")):
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        yield path


# Sentinel function node for calls that sit at module scope (no enclosing def).
_EMPTY_FUNC = cast(ast.FunctionDef, ast.parse("def _aegis_module_scope():\n    pass").body[0])


def _enclosing_function(node: ast.AST) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    """Nearest enclosing FunctionDef/AsyncFunctionDef via parent pointers, or None."""
    cur = getattr(node, "parent", None)
    while cur is not None:
        if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return cur
        cur = getattr(cur, "parent", None)
    return None


def _enclosing_class(node: ast.AST) -> ast.ClassDef | None:
    """Nearest enclosing ClassDef via parent pointers, or None — scopes ``self.attr`` bindings."""
    cur = getattr(node, "parent", None)
    while cur is not None:
        if isinstance(cur, ast.ClassDef):
            return cur
        cur = getattr(cur, "parent", None)
    return None


def _annotate_parents(tree: ast.AST) -> None:
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            child.parent = parent  # type: ignore[attr-defined]


def _root_name(node: ast.expr) -> str | None:
    while isinstance(node, (ast.Attribute, ast.Subscript)):
        node = node.value
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Call):
        return _root_name(node.func)
    return None


def _rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


__all__ = ["analyze_project"]
