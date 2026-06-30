"""SARIF 2.1.0 export for ``aegis inspect`` findings.

SARIF (Static Analysis Results Interchange Format) is what GitHub code scanning, and most
CI annotators, ingest. Emitting it lets Aegis findings show up inline on a pull request
without any bespoke integration. This is a pure *view* over the canonical :class:`Finding`
model (``findings.py``) — it invents nothing; the same ``file``/``line``/``severity``/``title``
that drive ``findings.json`` drive the SARIF ``results`` here.
"""

from __future__ import annotations

from .findings import Finding

SARIF_VERSION = "2.1.0"
SARIF_SCHEMA = "https://json.schemastore.org/sarif-2.1.0.json"
_INFO_URI = "https://github.com/quantifylabs/aegis-memory"

# Aegis severity -> SARIF result level. Critical/high are actionable failures (error); medium is a
# warning; low/structural is informational (note). Kept explicit so the mapping is auditable.
_LEVEL = {"critical": "error", "high": "error", "medium": "warning", "low": "note"}


def _level(severity: str) -> str:
    return _LEVEL.get(severity, "note")


def _rule_id(category: str) -> str:
    # One SARIF rule per finding category, namespaced so it never collides with another tool's rules.
    return f"aegis/{category}"


def to_sarif(findings: list[Finding], *, run_id: str, tool_version: str) -> dict:
    """Build a SARIF 2.1.0 document from a finding set.

    Each distinct finding category becomes a ``rule``; each finding becomes a ``result`` anchored to
    its sink ``file:line``. ``partialFingerprints`` carry a stable per-site key so code-scanning can
    track a finding across runs even as ``AEG-NNN`` ids renumber.
    """
    rules: dict[str, dict] = {}
    results: list[dict] = []
    for f in findings:
        cat = f.category
        if cat not in rules:
            rules[cat] = {
                "id": _rule_id(cat),
                "name": cat,
                "shortDescription": {"text": cat.replace("_", " ")},
                "defaultConfiguration": {"level": _level(f.severity)},
                "properties": {"tags": (["OWASP-ASI06"] if f.owasp else []) + ["aegis", "agent-memory"]},
            }
        message = f.title
        if f.owasp:
            message = f"{message} (OWASP {f.owasp})"
        result = {
            "ruleId": _rule_id(cat),
            "level": _level(f.severity),
            "message": {"text": message},
            "locations": [
                {
                    "physicalLocation": {
                        "artifactLocation": {"uri": f.sink.file},
                        "region": {"startLine": max(1, int(f.sink.line or 1))},
                    }
                }
            ],
            # Stable across runs: the sink site + category, not the volatile AEG-NNN id.
            "partialFingerprints": {"aegisSinkSite": f"{f.sink.file}:{f.sink.line}:{cat}"},
            "properties": {
                "aegisId": f.id,
                "severity": f.severity,
                "confidence": f.confidence,
                "framework": f.sink.framework,
                "sink": f.sink.call,
                "source": f.source,
                "trust": f.trust,
                "screened": f.screened,
            },
        }
        if f.owasp:
            result["properties"]["owasp"] = f.owasp
        results.append(result)

    return {
        "$schema": SARIF_SCHEMA,
        "version": SARIF_VERSION,
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "Aegis",
                        "informationUri": _INFO_URI,
                        "version": tool_version,
                        "rules": list(rules.values()),
                    }
                },
                "automationDetails": {"id": run_id},
                "results": results,
            }
        ],
    }


__all__ = ["to_sarif", "SARIF_VERSION"]
