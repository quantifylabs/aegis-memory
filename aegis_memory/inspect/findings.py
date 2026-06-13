"""The canonical finding model — the unit of truth for ``aegis inspect``.

Every finding is anchored to a real ``file + line + sink``. No location, no finding.
``findings.json`` is the canonical artifact; ``unsafe_memory_flows.json`` is *derived*
from it (flow-category findings only) and never maintained separately.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Confidence(str, Enum):
    # Borrowed from graphify: how sure we are about the source feeding a sink.
    EXTRACTED = "EXTRACTED"  # direct, same-scope dataflow we actually traced
    INFERRED = "INFERRED"  # cross-call heuristic
    AMBIGUOUS = "AMBIGUOUS"  # source unresolved


class Category(str, Enum):
    # Structural (high precision)
    MEMORY_WRITE = "memory_write"
    VECTOR_DB_WRITE = "vector_db_write"
    PROMPT_TEMPLATE_FLOW = "prompt_template_flow"
    # Flow (confidence-tagged — the headline findings)
    USER_INPUT_TO_MEMORY = "user_input_to_memory"
    TOOL_OUTPUT_TO_MEMORY = "tool_output_to_memory"
    # Absence (phrased "not detected at this site", never "they have none")
    OVERBROAD_SHARED_ACCESS = "overbroad_shared_access"
    MISSING_PROVENANCE = "missing_provenance"
    MISSING_REDACTION = "missing_redaction"
    MISSING_INJECTION_SCREENING = "missing_injection_screening"


# Categories that flow into the derived unsafe_memory_flows.json view.
FLOW_CATEGORIES = frozenset(
    {Category.USER_INPUT_TO_MEMORY.value, Category.TOOL_OUTPUT_TO_MEMORY.value}
)


@dataclass
class Sink:
    file: str  # repo-relative path
    line: int
    framework: str  # e.g. "langgraph", "vectordb", "custom"
    call: str  # e.g. "store.put"
    key: str | None = None  # literal memory key when statically known (e.g. "latest_note")


@dataclass
class Finding:
    id: str  # "AEG-001"
    severity: str
    confidence: str  # Confidence value; absent for pure structural findings -> "EXTRACTED"
    category: str
    sink: Sink
    source: str  # "untrusted_input" | "tool_output" | "unknown"
    trust: str  # "untrusted" | "internal" | "unknown"
    title: str
    fix: str
    screened: bool = False  # True when a content-security guard wraps this sink
    notes: list[str] = field(default_factory=list)
    # Populated only when the session-model classification loop runs (skill mode).
    classifier: str | None = None  # e.g. "session_model"
    classifier_label: str | None = None  # "malicious" | "benign" | "uncertain"
    classifier_reason: str | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        # Drop the optional classifier fields when unused to keep the artifact clean.
        if self.classifier is None:
            for k in ("classifier", "classifier_label", "classifier_reason"):
                d.pop(k, None)
        return d


def derive_unsafe_memory_flows(findings: list[Finding]) -> list[dict]:
    """Derived view: flow-category findings only. Generated from findings, never kept apart."""
    return [f.to_dict() for f in findings if f.category in FLOW_CATEGORIES]
