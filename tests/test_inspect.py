"""Unit + end-to-end tests for the ``aegis inspect`` engine and the memory-firewall demo.

Covers: the sink catalog per pattern, the five-channel untrusted flows on the demo, the
anti-demo-tuning generality fixtures (acceptance §3.5), screened downgrade, real-score
rendering through the HTML, canonical / derived artifact relationship, determinism, the score
being built from findings, the real replay scan, and the demo's without/with outcomes differing.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aegis_memory.inspect import analyze_project, derive_unsafe_memory_flows, run_inspection, sinks

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "inspect"
DEMO_DIR = REPO_ROOT / "examples" / "aegis-memory-firewall"
AGENT_DIR = DEMO_DIR / "agent"


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


# --- the demo's five untrusted channels --------------------------------------------


def test_demo_flows_detected_as_critical_untrusted():
    """All five channels (user, document, tool, web, email) are flagged as untrusted
    memory writes, across the LangGraph / vector-DB / custom sink families."""
    findings = analyze_project(AGENT_DIR)
    flows = [f for f in findings if f.category.endswith("_to_memory")]
    assert len(flows) == 5, f"expected five untrusted source->memory flows, got {len(flows)}"
    assert all(f.severity == "critical" for f in flows)
    assert all(f.trust == "untrusted" for f in flows)
    assert all(f.confidence in ("EXTRACTED", "INFERRED") for f in flows)
    assert all(f.sink.file.startswith("ingest_") and f.sink.line > 0 for f in flows)
    # Generalizes across sink families, not one idiom.
    assert {f.sink.framework for f in flows} == {"langgraph", "vectordb", "custom"}
    calls = {f.sink.call for f in flows}
    assert {"store.put", "checkpointer.put", "vectorstore.add_documents", "memory.save"} <= calls
    # The tool channel is tagged tool_output; the rest untrusted_input.
    assert any(f.source == "tool_output" for f in flows)
    assert any(f.source == "untrusted_input" for f in flows)


# --- anti-demo-tuning: a different fixture must still be caught (acceptance #5) -----


def test_generality_second_fixture_store_put_found():
    findings = analyze_project(FIXTURES)
    b = [f for f in findings if f.sink.file.endswith("graph_b.py")]
    puts = [f for f in b if "put" in f.sink.call]
    assert puts, "general catalog must find graph_b's .put sink (not demo-tuned)"
    untrusted = [f for f in b if f.trust == "untrusted"]
    assert untrusted, "graph_b's untrusted flow must be detected via the general catalog"


def test_generality_multisource_fixture_all_channels_found():
    """The multi-channel anti-tuning fixture (different names, a vector store for the web
    sink) must still have every untrusted flow caught by the general catalog."""
    findings = analyze_project(FIXTURES)
    ms = [f for f in findings if f.sink.file.endswith("graph_multisource.py")]
    flows = [f for f in ms if f.category.endswith("_to_memory")]
    assert len(flows) == 4, f"expected four untrusted flows, got {len(flows)}"
    assert all(f.trust == "untrusted" and f.severity == "critical" for f in flows)
    assert all(not f.screened for f in flows)
    # Spans LangGraph store/checkpointer, a vector store, and a custom sink — no demo tuning.
    assert {f.sink.framework for f in flows} == {"langgraph", "vectordb", "custom"}


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
    result = run_inspection(DEMO_DIR, out_dir=out, write=True)
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
    # Responsive, and the header renders the real computed "after" score (not the 29 fallback).
    assert "viewport" in html
    assert f'"after">{result.score["score"]}<' in html


def test_real_before_score_renders_through_html_not_fallback(tmp_path):
    """A real run with a supplied before_score renders the computed values, never the
    standalone 86/29 fallbacks (the §2 score-rendering fix)."""
    out = tmp_path / "out"
    result = run_inspection(DEMO_DIR, out_dir=out, write=True, before_score=42)
    html = (out / "agent_memory_map.html").read_text(encoding="utf-8")
    assert '"before">42<' in html  # the real supplied "before"
    assert f'"after">{result.score["score"]}<' in html  # the real computed "after"
    assert '"before">86<' not in html and '"after">29<' not in html  # fallbacks not used
    # The report leads with the real transition too.
    report = (out / "INSPECTION_REPORT.md").read_text(encoding="utf-8")
    assert f"**42 → {result.score['score']} / 100**" in report


def test_map_is_proof_first_trace_then_scan_then_table(tmp_path):
    """The map leads with the faithful trace (lanes anchored to file:line), then the live
    scan-verdict panel, then the findings table — proof, not a convergence story. Self-contained
    (no CDN)."""
    out = tmp_path / "out"
    run_inspection(DEMO_DIR, out_dir=out, write=True, before_score=80)
    html = (out / "agent_memory_map.html").read_text(encoding="utf-8")
    assert "http://" not in html and "https://" not in html
    assert "viewport" in html
    # The old storytelling hero (two state cards / fan-in SVG / without-vs-with) is gone.
    assert 'class="state ' not in html
    assert "Without Aegis" not in html
    assert "<svg " not in html
    # Faithful trace leads, then the live-scan panel, then the findings table.
    assert '<section class="trace"' in html
    assert html.index('class="trace"') < html.index('class="scan"')
    assert html.index('class="scan"') < html.index("All findings")
    assert html.index('class="scan"') < html.index("<table")
    # Lanes are anchored to a real file:line from a demo sink.
    assert "ingest_web.py:" in html
    # The live-scan panel renders the REAL scanner verdict, not a story.
    assert 'class="verdict-chip reject"' in html
    assert "injection_override" in html


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
        # Drop the demo's modules (run scripts, helpers, and the ``agent`` package) so the
        # two parametrized runs import cleanly and don't leak into other tests.
        for m in list(sys.modules):
            if m == script or m == "_demo_common" or m == "agent" or m.startswith("agent."):
                sys.modules.pop(m, None)
