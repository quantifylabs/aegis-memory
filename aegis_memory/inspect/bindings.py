"""Receiver -> library binding via constructor resolution (Batch B — the detection fix).

The sink catalog (:mod:`sinks`) matches on *receiver name shape*: a write verb on a receiver whose
dotted name contains a hint (``store``/``memory``/...). That misses the most common real idioms,
whose receiver is an alias carrying no hint — ``m.add`` (``m = Memory()``), ``app.add``
(``app = App()``), ``manager.store``, tiered ``self.warm.put`` / ``self.hot.put``, ``router.write``,
``self.backend.save``. The methods are already in the catalog; only the *receiver* is unrecognized.

Widening the hint lists to catch these would re-introduce the substring false positives the catalog
header warns about (a local ``results.append`` named like a store). Instead this module **resolves
the receiver to its constructor** and authorizes the write *only when the constructor is a known or
heuristically-recognized memory handle* — precision keyed on the constructor class name, never on the
receiver variable name. New detection, gated by the owned FP-fixture set (``tests/test_inspect.py``).

Two binding shapes are resolved (both name-keyed to the exact AST nodes the analyzer scans, so node
identity is shared):

* **local variable** — ``m = Memory(); m.add(...)`` within one function.
* **self-attribute** — ``self.warm = WarmTier()`` in one method, ``self.warm.put(...)`` in another,
  resolved per enclosing ``class``.

Honest limits (same spirit as :mod:`interproc`): no import-alias/type resolution beyond a per-module
import gate, no cross-instance flow. A receiver that does not resolve to a constructor is simply left
to the name-hint tiers — never bound on a guess.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator

from .findings import Category
from .sinks import _CUSTOM_WRITE_METHODS_STATIC, BindingInfo
from .taint import _all_args

_FuncDef = ast.FunctionDef | ast.AsyncFunctionDef

# ---- Known-library constructors (exact class name -> binding), import-gated -----------------
# Generic class names (``Memory``/``App``) collide across libraries, so a known-library binding is
# honored only when the module that constructs it imports that library (mirrors the langgraph gate
# in ``taint._module_imports_langgraph``). Methods are sourced from the catalog; the table just
# authorizes them on a *bound* receiver.
#   class name -> (library, required import root, write methods, sink category)
_KNOWN_CONSTRUCTORS: dict[str, tuple[str, str, frozenset[str], str]] = {
    "Memory": ("mem0", "mem0", frozenset({"add", "update"}), Category.MEMORY_WRITE.value),
    "MemoryClient": ("mem0", "mem0", frozenset({"add", "update"}), Category.MEMORY_WRITE.value),
    "AsyncMemory": ("mem0", "mem0", frozenset({"add", "update"}), Category.MEMORY_WRITE.value),
    "AsyncMemoryClient": ("mem0", "mem0", frozenset({"add", "update"}), Category.MEMORY_WRITE.value),
    "App": ("embedchain", "embedchain", frozenset({"add"}), Category.VECTOR_DB_WRITE.value),
}

# ---- Custom memory-class heuristic (lowest confidence) --------------------------------------
# A constructor whose *class name* carries a memory-storage token is treated as a custom memory
# handle. This is the sanctioned substring match — on the constructor, not the receiver. ``update``
# is included here (bound-only) but deliberately NOT added to the name-hint tier in ``sinks.py``:
# ``dict.update`` is far too common to flag on a receiver name.
_CUSTOM_BOUND_METHODS: frozenset[str] = frozenset(_CUSTOM_WRITE_METHODS_STATIC) | {"update"}
_CUSTOM_CLASS_TOKENS: tuple[str, ...] = (
    "memory",
    "store",
    "cache",
    "buffer",
    "backend",
    "tier",
    "knowledgebase",
    "scratchpad",
    "vectorstore",
    "vectordb",
)


def _binding_for(ctor: str, imported: set[str]) -> BindingInfo | None:
    """Resolve a constructor class name to a :class:`BindingInfo`, or None.

    Known-library constructors win when their import is present; otherwise (and for everything else)
    the custom memory-class heuristic applies. ``App`` without an ``embedchain`` import binds to
    nothing — it carries no memory token — so an unrelated ``App()`` never registers."""
    known = _KNOWN_CONSTRUCTORS.get(ctor)
    if known is not None:
        library, root, methods, category = known
        if root in imported:
            return BindingInfo(library, methods, category, "INFERRED")
        # Import gate failed — fall through to the heuristic (a local ``Memory`` class still binds
        # as a custom handle via its name token, but is not attributed to mem0).
    low = ctor.lower()
    if any(tok in low for tok in _CUSTOM_CLASS_TOKENS):
        return BindingInfo("custom", _CUSTOM_BOUND_METHODS, Category.MEMORY_WRITE.value, "AMBIGUOUS")
    return None


class ReceiverBindings:
    """Project-wide receiver->library bindings, keyed by the exact AST nodes the analyzer scans."""

    def __init__(self) -> None:
        # (file, id(enclosing func), receiver name) -> binding, for ``m = Memory()`` locals.
        self._local: dict[tuple[str, int, str], BindingInfo] = {}
        # (file, receiver name) -> binding, for module-scope ``m = Memory()`` (dominant in notebooks,
        # where most code sits at module level).
        self._module: dict[tuple[str, str], BindingInfo] = {}
        # (file, id(func)) -> names bound locally (params + assigned), so a function-local ``m`` that
        # shadows a module-global ``m = Memory()`` is NOT mis-resolved to the global.
        self._func_locals: dict[tuple[str, int], set[str]] = {}
        # (file, id(enclosing class), "self.attr") -> binding, for ``self.warm = WarmTier()``.
        self._attr: dict[tuple[str, int, str], BindingInfo] = {}

    @classmethod
    def build(cls, modules: list[tuple[str, ast.Module]]) -> ReceiverBindings:
        rb = cls()
        for rel, tree in modules:
            imported = _imported_roots(tree)
            # Module-scope locals (notebook cells, script bodies).
            for name, ctor in _local_constructors(tree):
                info = _binding_for(ctor, imported)
                if info is not None:
                    rb._module[(rel, name)] = info
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    rb._func_locals[(rel, id(node))] = _func_local_names(node)
                    for name, ctor in _local_constructors(node):
                        info = _binding_for(ctor, imported)
                        if info is not None:
                            rb._local[(rel, id(node), name)] = info
                elif isinstance(node, ast.ClassDef):
                    for attr, ctor in _self_attr_constructors(node):
                        info = _binding_for(ctor, imported)
                        if info is not None:
                            rb._attr[(rel, id(node), f"self.{attr}")] = info
        return rb

    def resolve(
        self, file: str, func: _FuncDef | None, klass: ast.ClassDef | None, receiver: str | None
    ) -> BindingInfo | None:
        """The binding for ``receiver`` at a call site in ``file`` (within ``func`` / ``klass``)."""
        if not receiver:
            return None
        if "." not in receiver:
            if func is not None:
                local = self._local.get((file, id(func), receiver))
                if local is not None:
                    return local
                # The function defines its own ``receiver`` (param or non-constructor local, e.g.
                # ``m = []``) — it shadows any module global of the same name; do not fall through.
                if receiver in self._func_locals.get((file, id(func)), set()):
                    return None
            return self._module.get((file, receiver))
        if receiver.startswith("self.") and klass is not None:
            return self._attr.get((file, id(klass), receiver))
        return None


# --- helpers -----------------------------------------------------------------------


def _imported_roots(tree: ast.Module) -> set[str]:
    """Top-level import roots in the module (``import mem0`` / ``from mem0 import Memory`` -> mem0)."""
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def _own_scope_stmts(scope: ast.AST) -> Iterator[ast.AST]:
    """Descendants of ``scope`` that belong to its own scope — not descending into a nested
    function/class/lambda (whose assignments belong to a different scope)."""
    for child in ast.iter_child_nodes(scope):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            continue
        yield child
        yield from _own_scope_stmts(child)


def _local_constructors(scope: ast.AST) -> Iterator[tuple[str, str]]:
    """``name = Constructor()`` assignments in a scope's own body (a function or the module) ->
    (name, class name)."""
    for stmt in _own_scope_stmts(scope):
        if isinstance(stmt, ast.Assign):
            ctor = _ctor_name(stmt.value)
            if ctor is None:
                continue
            for tgt in stmt.targets:
                if isinstance(tgt, ast.Name):
                    yield tgt.id, ctor


def _func_local_names(func: _FuncDef) -> set[str]:
    """Names that belong to ``func``'s own scope — its parameters plus every plain-``Name`` assignment
    target. Used to detect a local that shadows a module global of the same name."""
    names = {a.arg for a in _all_args(func)}
    for stmt in _own_scope_stmts(func):
        if isinstance(stmt, ast.Assign):
            for tgt in stmt.targets:
                if isinstance(tgt, ast.Name):
                    names.add(tgt.id)
        elif isinstance(stmt, ast.For) and isinstance(stmt.target, ast.Name):
            names.add(stmt.target.id)
    return names


def _self_attr_constructors(klass: ast.ClassDef) -> Iterator[tuple[str, str]]:
    """``self.attr = Constructor()`` assignments in the class's methods -> (attr, class name)."""
    for item in klass.body:
        if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for stmt in _own_scope_stmts(item):
            if isinstance(stmt, ast.Assign):
                ctor = _ctor_name(stmt.value)
                if ctor is None:
                    continue
                for tgt in stmt.targets:
                    attr = _self_attr_name(tgt)
                    if attr is not None:
                        yield attr, ctor


def _ctor_name(value: ast.expr) -> str | None:
    """The class name a value is constructed from: ``Memory()`` -> ``Memory``, ``mem0.Memory()`` ->
    ``Memory``. Only a direct call expression counts (no factory-return tracking)."""
    if not isinstance(value, ast.Call):
        return None
    fn = value.func
    if isinstance(fn, ast.Name):
        return fn.id
    if isinstance(fn, ast.Attribute):
        return fn.attr
    return None


def _self_attr_name(tgt: ast.expr) -> str | None:
    """``self.warm`` (an attribute on ``self``) -> ``warm``; anything else -> None."""
    if isinstance(tgt, ast.Attribute) and isinstance(tgt.value, ast.Name) and tgt.value.id == "self":
        return tgt.attr
    return None


__all__ = ["ReceiverBindings"]
