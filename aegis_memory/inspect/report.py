"""Run orchestration + artifact writers.

A run never destroys history: it writes a new timestamped run under
``aegis-out/runs/<ts>/`` and refreshes the latest files at the ``aegis-out/`` root.
``findings.json`` is canonical; ``unsafe_memory_flows.json`` is derived from it.
"""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import yaml

from . import analyzer, cases, htmlmap, policies, replay
from . import score as scoring
from .findings import Finding, derive_unsafe_memory_flows

OUT_DIR_NAME = "aegis-out"

# Standalone/no-baseline fallback only: the "before" value shown in the headline transition
# when the caller supplies no real prior-run score. A real before/after (e.g. the demo's
# unscreened-vs-screened comparison) passes a computed ``before_score`` into ``run_inspection``,
# which overrides this. Never let this constant stand in for a real measured run.
BEFORE_SCORE = 86


@dataclass
class InspectionResult:
    findings: list[Finding]
    score: dict
    run_id: str
    out_root: Path
    run_dir: Path
    # Real "before" score from a prior/unscreened run, when the caller has one. None ->
    # the report/visual fall back to the labeled BEFORE_SCORE baseline above.
    before_score: int | None = None


def run_inspection(
    project_root: str | Path,
    *,
    out_dir: str | Path | None = None,
    framework: str | None = None,
    write: bool = True,
    before_score: int | None = None,
) -> InspectionResult:
    project_root = Path(project_root).resolve()
    findings = analyzer.analyze_project(project_root, framework=framework)
    return _finalize(project_root, findings, out_dir=out_dir, write=write, before_score=before_score)


def _finalize(
    project_root: Path,
    findings: list[Finding],
    *,
    out_dir: str | Path | None = None,
    write: bool = True,
    before_score: int | None = None,
) -> InspectionResult:
    """Score a finding set and (optionally) write all artifacts. Shared by the plain run,
    emit-cases, and ingest-verdicts paths."""
    score = scoring.compute_score(findings)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
    run_id = f"{ts}Z-{secrets.token_hex(3)}"
    out_root = Path(out_dir).resolve() if out_dir else project_root / OUT_DIR_NAME
    run_dir = out_root / "runs" / ts

    result = InspectionResult(findings, score, run_id, out_root, run_dir, before_score=before_score)
    if write:
        _write_artifacts(result, project_root.name)
    return result


def emit_cases(
    project_root: str | Path,
    *,
    out_dir: str | Path | None = None,
    framework: str | None = None,
) -> tuple[InspectionResult, dict]:
    """Run the deterministic inspection and write ``cases/cases.json`` for the session model."""
    project_root = Path(project_root).resolve()
    findings = analyzer.analyze_project(project_root, framework=framework)
    result = _finalize(project_root, findings, out_dir=out_dir, write=True)
    case_list = cases.build_cases(findings, project_root)
    doc = cases.write_cases(result.out_root, case_list)
    return result, doc


def ingest_verdicts(
    project_root: str | Path,
    *,
    out_dir: str | Path | None = None,
    framework: str | None = None,
) -> InspectionResult:
    """Fold session-model verdicts back into the findings and refresh the report."""
    project_root = Path(project_root).resolve()
    out_root = Path(out_dir).resolve() if out_dir else project_root / OUT_DIR_NAME
    cases_doc = cases.load_cases(out_root)
    verdicts_doc = cases.load_verdicts(out_root)
    # Deterministic re-analysis reproduces the exact findings the cases were built from.
    findings = analyzer.analyze_project(project_root, framework=framework)
    cases.apply_verdicts(findings, cases_doc, verdicts_doc)
    return _finalize(project_root, findings, out_dir=out_dir, write=True)


def _write_artifacts(result: InspectionResult, project_name: str) -> None:
    artifacts = _build_artifacts(result, project_name)
    # Timestamped run (history) + latest at root.
    (result.run_dir / "replay_attacks").mkdir(parents=True, exist_ok=True)
    (result.out_root / "replay_attacks").mkdir(parents=True, exist_ok=True)
    for rel, content in artifacts.items():
        (result.run_dir / rel).write_text(content, encoding="utf-8")
        (result.out_root / rel).write_text(content, encoding="utf-8")


def _build_artifacts(result: InspectionResult, project_name: str) -> dict[str, str]:
    findings = result.findings
    findings_json = {
        "schema": "aegis.findings.v1",
        "run_id": result.run_id,
        "score": result.score,
        "findings": [f.to_dict() for f in findings],
    }
    flows_json = {
        "schema": "aegis.unsafe_memory_flows.v1",
        "run_id": result.run_id,
        "note": "Derived view of findings.json (flow-category findings only).",
        "flows": derive_unsafe_memory_flows(findings),
    }
    replay_result = replay.run_memory_poisoning()
    # "after" is always the real computed score from this run. "before" is the caller's real
    # prior-run score when supplied; otherwise the generic in-run *unscreened-exposure* baseline
    # (the same heuristic with screening discounts ignored). When nothing is screened the two
    # coincide -> we drop the arrow and show a single score (no "-0 after screening" noise).
    after = result.score["score"]
    if result.before_score is not None:
        before: int | None = result.before_score
    else:
        raw = scoring.raw_score(findings)
        before = raw if raw != after else None
    return {
        "findings.json": json.dumps(findings_json, indent=2) + "\n",
        "unsafe_memory_flows.json": json.dumps(flows_json, indent=2) + "\n",
        "suggested_policies.yml": yaml.safe_dump(
            policies.suggest_policies(findings), sort_keys=False
        ),
        "INSPECTION_REPORT.md": _render_report(result, project_name, replay_result, before),
        "agent_memory_map.html": htmlmap.render_html(
            findings, result.score, before_score=before, after_score=after,
            project_name=project_name, replay_result=replay_result,
        ),
        "replay_attacks/memory_poisoning_demo.md": replay.render_markdown(replay_result),
    }


def _render_report(
    result: InspectionResult, project_name: str, replay_result: dict, before_score: int | None
) -> str:
    findings = result.findings
    score = result.score
    # Lead with concrete findings (file+line); score comes second.
    lines: list[str] = []
    lines.append(f"# Aegis Inspection Report — {project_name}\n")
    lines.append(f"_Run `{result.run_id}` · {len(findings)} findings_\n")

    # Two engines, two credibility levels — stated up front so neither borrows the other's standing.
    lines.append(
        "> **Two engines, labeled separately.** _Runtime content scanner_: benchmarked "
        "(see `benchmarks/results.json`) — the live `scan()` replay below uses it. "
        "_Static memory-map_ (the findings, flows, and risk score here): **heuristic, preliminary, "
        "not yet benchmarked** — best-effort, bounded-depth dataflow. Flow findings are tagged "
        "**OWASP ASI06 (Memory & Context Poisoning)**.\n"
    )

    # Scope is stated up front so a reader never reads the absence of `list.append` as a miss.
    lines.append(
        "> **Scope.** Aegis inspects writes to **persistent and shared** memory. Ephemeral in-process "
        "buffers (`list.append`, a local `dict`) are **out of scope by design** — a planned opt-in "
        "`--include-buffers` mode (see `docs/issues/buffer-memory-mode.md`) would flag them only when "
        "the value taints to an untrusted source.\n"
    )

    headline = [f for f in findings if f.severity in ("critical", "high")]
    lines.append("## Findings (the defensible core)\n")
    if headline:
        lines.append("### Critical / High\n")
        for f in headline:
            lines.append(_finding_block(f))
    others = [f for f in findings if f.severity in ("medium", "low")]
    if others:
        lines.append("### Medium / Low\n")
        for f in others:
            lines.append(_finding_block(f))
    if not findings:
        lines.append("_No memory-write sinks detected._\n")

    s = score["score"]
    c = score["counts"]
    lines.append("\n## Memory Risk Score (heuristic — UX sugar, not the benchmark)\n")
    transition = f"{before_score} → {s}" if before_score is not None else f"{s}"
    lines.append(
        f"**{transition} / 100** — **100 = maximum risk · lower is safer** (heuristic)\n"
    )
    lines.append(
        f"Critical {c['critical']} · High {c['high']} · Medium {c['medium']} · Low {c['low']}\n"
    )
    lines.append(f"> Rubric: {score['rubric']}\n")

    wa = replay_result["with_aegis"]
    lines.append("\n## Replay: memory-poisoning (live scan)\n")
    lines.append(
        f"Built-in payload screened by the real scanner → action `{wa['action']}` "
        f"({'REJECTED' if not wa['allowed'] else 'allowed'}); reason: {wa['reason']}.\n"
    )
    lines.append("See `replay_attacks/memory_poisoning_demo.md` for the before/after.\n")
    lines.append(
        "\n---\nFindings are anchored to a file + line + sink. Absence findings say "
        "\"not detected at this site\", never \"none exist\". Confidence tags: "
        "EXTRACTED (same-scope), INFERRED (cross-call heuristic), AMBIGUOUS (unresolved).\n"
    )
    return "\n".join(lines)


def _finding_block(f: Finding) -> str:
    notes = ("\n  " + "\n  ".join(f"- {n}" for n in f.notes)) if f.notes else ""
    fix_lines = "\n  ".join(f.fix.splitlines())
    tag = f" · `OWASP {f.owasp}`" if f.owasp else ""
    edge = ""
    if f.flow_path:
        steps = " → ".join(f"`{s['file']}:{s['line']}`" for s in f.flow_path)
        edge = f"\n  Source→sink path: {steps} → `{f.sink.file}:{f.sink.line}` (the sink)\n"
        for s in f.flow_path:
            edge += f"  - {s['file']}:{s['line']} — {s['note']}\n"
    return (
        f"- **{f.id} [{f.severity}/{f.confidence}]**{tag} {f.title}\n"
        f"  `{f.sink.file}:{f.sink.line}` · sink `{f.sink.call}` ({f.sink.framework}) · "
        f"source `{f.source}` · trust `{f.trust}`{' · screened' if f.screened else ''}\n"
        f"{edge}"
        f"  Fix:\n  ```python\n  {fix_lines}\n  ```{notes}\n"
    )


__all__ = ["InspectionResult", "emit_cases", "ingest_verdicts", "run_inspection"]
