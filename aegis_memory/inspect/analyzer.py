"""The static analysis engine. Walks a project with Python's ``ast``, matches memory-
write sinks (``sinks.py``), runs the same-scope taint check (``taint.py``), and emits
location-anchored :class:`Finding` objects.

General, never demo-tuned: the only inputs are the documented sink shapes and source
hints. No rule keys off any demo filename or string.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

from . import interproc, sinks, taint
from .findings import Category, Finding, Sink

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
    flow_path: list[dict] = field(default_factory=list)


def analyze_project(root: str | Path, framework: str | None = None) -> list[Finding]:
    """Analyze every ``.py`` file under ``root`` and return sorted, id-assigned findings.

    Two passes: parse every module and build a project-wide :class:`interproc.ProjectIndex`, then
    scan sinks. Each sink's written value is resolved same-scope first; when that is inconclusive,
    the bounded interprocedural resolver follows the value across function/file boundaries."""
    root = Path(root).resolve()
    modules: list[tuple[str, ast.Module]] = []
    for path in _iter_python_files(root):
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
        except (SyntaxError, UnicodeDecodeError):
            continue
        rel = _rel(path, root)
        _annotate_parents(tree)
        modules.append((rel, tree))

    index = interproc.ProjectIndex.build(modules)

    sites: list[_SinkSite] = []
    read_flows: list[tuple[str, int]] = []
    for rel, tree in modules:
        sites.extend(_scan_module(tree, rel))
        read_flows.extend(_scan_read_paths(tree, rel))

    # Resolve each sink's source — same-scope, then bounded interprocedural/cross-file. A resolved
    # untrusted source upgrades the (possibly internal/unknown) same-scope verdict and records the
    # source->sink edge; an unresolved sink is left structural (never dropped).
    for s in sites:
        res = interproc.resolve_sink(s.write_value, s.func, s.file, index, screened=s.taint.screened)
        if res is not None:
            s.taint = res.taint
            s.flow_path = res.flow_path

    findings = _build_findings(sites, read_flows, framework)
    return findings


# --- module scan -------------------------------------------------------------------


def _scan_module(tree: ast.Module, rel: str) -> list[_SinkSite]:
    """Visit each Call once, scoped to its nearest enclosing function (no double-count)."""
    out: list[_SinkSite] = []
    scope_cache: dict[int, taint.FunctionScope] = {}
    for call in ast.walk(tree):
        if not isinstance(call, ast.Call):
            continue
        match = _match_call(call)
        if match is None:
            continue
        func = _enclosing_function(call)
        if func is None:
            scope = taint.FunctionScope(func=_EMPTY_FUNC)
        else:
            scope = scope_cache.get(id(func)) or taint.build_scope(func)
            scope_cache[id(func)] = scope
        value = _write_value(call)
        tr = taint.analyze(value, scope)
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
            )
        )
    return out


def _match_call(call: ast.Call) -> sinks.SinkMatch | None:
    fn = call.func
    kwargs = tuple(kw.arg for kw in call.keywords if kw.arg)
    if isinstance(fn, ast.Attribute):
        # Use the dotted receiver path (e.g. "self.memory_store") so hint matching sees
        # the meaningful attribute name, not just the root object.
        receiver = _receiver_string(fn.value)
        return sinks.classify_call(attr=fn.attr, func=None, receiver=receiver, keywords=kwargs)
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
    """Heuristic: does this write target a shared/global namespace?"""
    for node in ast.walk(call):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            v = node.value.lower()
            if v in ("shared", "global", "public", "all") or "shared" in v or "global" in v:
                return True
    return False


# --- read-path / provenance heuristic ----------------------------------------------


def _scan_read_paths(tree: ast.Module, rel: str) -> list[tuple[str, int]]:
    """Find memory reads that feed a prompt without provenance, scoped to the read's
    nearest enclosing function (deduped by location)."""
    seen: set[tuple[str, int]] = set()
    out: list[tuple[str, int]] = []
    dump_cache: dict[int, str] = {}
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
        body_src = dump_cache.get(id(func)) or ast.dump(func).lower()
        dump_cache[id(func)] = body_src
        prompt_used = any(t in body_src for t in _PROMPT_TOKENS)
        has_provenance = any(t in body_src for t in _PROVENANCE_TOKENS)
        loc = (rel, getattr(call, "lineno", 0))
        if prompt_used and not has_provenance and loc not in seen:
            seen.add(loc)
            out.append(loc)
    return out


# --- finding construction ----------------------------------------------------------


def _build_findings(
    sites: list[_SinkSite], read_flows: list[tuple[str, int]], framework: str | None
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
                    fix=(
                        "from aegis_memory import guard\n"
                        "store = guard.protect(store, scope='agent-shared')  # screen every write, or:\n"
                        "guard.write(content, trust_level='untrusted', scope='agent-shared')"
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

    for rel, line in read_flows:
        raw.append(
            Finding(
                id="",
                severity="low",
                confidence="AMBIGUOUS",
                category=Category.MISSING_PROVENANCE.value,
                sink=Sink(file=rel, line=line, framework="langgraph", call="store.get"),
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


def _iter_python_files(root: Path) -> Iterator[Path]:
    for path in sorted(root.rglob("*.py")):
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
