"""Aegis Inspect — static analysis for unsafe agent-memory flows.

A new, standalone, server-free mode: ``aegis inspect`` runs offline and deterministic on
any project, finds memory-write sinks, and reports the unsafe flows where untrusted input
reaches durable memory. Detection reuses the real ``ContentSecurityScanner`` (the
benchmark-validated pipeline) via :mod:`aegis_memory.inspect._scanner_bridge`; this package
adds the static sink/taint analysis around it, never new detection rules.
"""

from __future__ import annotations

from .analyzer import analyze_project
from .findings import Finding, derive_unsafe_memory_flows
from .report import InspectionResult, run_inspection

__all__ = [
    "Finding",
    "InspectionResult",
    "analyze_project",
    "derive_unsafe_memory_flows",
    "run_inspection",
]
