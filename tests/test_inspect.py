"""Unit + end-to-end tests for the ``aegis inspect`` engine and the support-agent demo.

Covers: the sink catalog per pattern, the headline untrusted flow on the demo, the
anti-demo-tuning generality fixture (acceptance #5), screened downgrade, canonical /
derived artifact relationship, determinism, the score being built from findings, the real
replay scan, and the demo's without/with outcomes differing.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aegis_memory.inspect import analyze_project, derive_unsafe_memory_flows, run_inspection, sinks

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "inspect"
DEMO_DIR = REPO_ROOT / "examples" / "aegis-demo-support-agent"


# --- sink catalog (per-pattern unit tests) ----------------------------------------


@pytest.mark.parametrize(
    "attr,func,receiver,expect_framework",
    [
        ("put", None, "store", "langgraph"),
        ("put", None, "self.memory_store", "langgraph"),
        ("put", None, "checkpointer", "langgraph"),
        (None, "add_messages", None, "langgraph"),
        ("upsert", None, "pinecone_index", "vectordb"),
        ("add_texts", None, "vectorstore", "vectordb"),
        ("append", None, "self.history", "custom"),
    ],
)
def test_sink_catalog_matches(attr, func, receiver, expect_framework):
    match = sinks.classify_call(attr=attr, func=func, receiver=receiver)
    assert match is not None
    assert match.framework == expect_framework


def test_sink_catalog_ignores_unrelated_calls():
    assert sinks.classify_call(attr="get", func=None, receiver="store") is None
    assert sinks.classify_call(attr="put", func=None, receiver="widget") is None
    assert sinks.classify_call(attr=None, func="print", receiver=None) is None


# --- the demo's headline flow ------------------------------------------------------


def test_demo_flow_detected_as_critical_untrusted():
    findings = analyze_project(DEMO_DIR)
    flows = [f for f in findings if f.category == "user_input_to_memory"]
    assert flows, "expected an untrusted user-input-to-memory flow in the demo"
    headline = flows[0]
    assert headline.severity == "critical"
    assert headline.trust == "untrusted"
    assert headline.sink.call == "store.put"
    assert headline.sink.framework == "langgraph"
    assert headline.sink.file.endswith("support_agent_graph.py")
    assert headline.sink.line > 0
    assert headline.confidence in ("EXTRACTED", "INFERRED")


# --- anti-demo-tuning: a different fixture must still be caught (acceptance #5) -----


def test_generality_second_fixture_store_put_found():
    findings = analyze_project(FIXTURES)
    b = [f for f in findings if f.sink.file.endswith("graph_b.py")]
    puts = [f for f in b if "put" in f.sink.call]
    assert puts, "general catalog must find graph_b's .put sink (not demo-tuned)"
    untrusted = [f for f in b if f.trust == "untrusted"]
    assert untrusted, "graph_b's untrusted flow must be detected via the general catalog"


def test_clean_fixture_has_no_untrusted_flow():
    findings = analyze_project(FIXTURES)
    clean = [f for f in findings if f.sink.file.endswith("graph_clean.py")]
    assert clean, "expected a structural memory-write finding for the clean fixture"
    assert all(f.trust != "untrusted" for f in clean)
    assert all(f.severity != "critical" for f in clean)


def test_screened_fixture_is_downgraded():
    findings = analyze_project(FIXTURES)
    screened = [f for f in findings if f.sink.file.endswith("graph_screened.py")]
    flow = [f for f in screened if f.category.endswith("_to_memory")]
    assert flow, "expected a flow finding for the screened fixture"
    assert any(f.screened for f in flow)
    assert all(f.severity != "critical" for f in flow)


# --- canonical findings vs derived view --------------------------------------------


def test_unsafe_flows_is_derived_from_findings():
    result = run_inspection(DEMO_DIR, write=False)
    derived = derive_unsafe_memory_flows(result.findings)
    flow_findings = [
        f.to_dict() for f in result.findings if f.category in ("user_input_to_memory", "tool_output_to_memory")
    ]
    assert derived == flow_findings


def test_every_finding_is_anchored():
    findings = analyze_project(DEMO_DIR)
    for f in findings:
        assert f.sink.file and f.sink.line > 0 and f.sink.call


# --- determinism -------------------------------------------------------------------


def test_analyze_is_deterministic():
    a = analyze_project(DEMO_DIR)
    b = analyze_project(DEMO_DIR)
    assert [(f.id, f.severity, f.confidence, f.title, f.sink.line) for f in a] == [
        (f.id, f.severity, f.confidence, f.title, f.sink.line) for f in b
    ]


# --- score is built from findings, labeled heuristic -------------------------------


def test_score_built_from_findings():
    result = run_inspection(DEMO_DIR, write=False)
    assert result.score["label"] == "heuristic"
    assert "rubric" in result.score
    counts = result.score["counts"]
    assert counts["critical"] == sum(1 for f in result.findings if f.severity == "critical")
    assert 0 < result.score["score"] <= 100


# --- artifacts written -------------------------------------------------------------


def test_inspection_writes_all_artifacts(tmp_path):
    out = tmp_path / "out"
    run_inspection(DEMO_DIR, out_dir=out, write=True)
    for name in (
        "INSPECTION_REPORT.md",
        "findings.json",
        "unsafe_memory_flows.json",
        "suggested_policies.yml",
        "agent_memory_map.html",
        "replay_attacks/memory_poisoning_demo.md",
    ):
        assert (out / name).exists(), f"missing artifact {name}"
    # History preserved under runs/.
    assert (out / "runs").is_dir() and any((out / "runs").iterdir())
    data = json.loads((out / "findings.json").read_text(encoding="utf-8"))
    assert data["schema"] == "aegis.findings.v1"
    html = (out / "agent_memory_map.html").read_text(encoding="utf-8")
    assert "viewport" in html and "86" in html  # responsive + score transition


# --- the real replay scan ----------------------------------------------------------


def test_replay_uses_real_scanner_and_rejects():
    from aegis_memory.inspect import replay

    result = replay.run_memory_poisoning()
    wa = result["with_aegis"]
    assert wa["action"] == "reject" and wa["allowed"] is False
    assert "injection" in wa["reason"]


# --- end-to-end: demo outcomes differ (without approves, with denies) --------------


@pytest.mark.parametrize("script,expected", [("run_without_aegis", "APPROVED"), ("run_with_aegis", "DENIED")])
def test_demo_outcomes_differ(script, expected):
    pytest.importorskip("langgraph")
    import sys

    sys.path.insert(0, str(DEMO_DIR))
    try:
        mod = __import__(script)
        assert mod.main() == expected
    finally:
        sys.path.remove(str(DEMO_DIR))
        for m in (script, "support_agent_graph", "_demo_common"):
            sys.modules.pop(m, None)
