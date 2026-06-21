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
TAINT_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "inspect_taint"
NAMECOLLIDE_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "inspect_namecollide"
DEMO_DIR = REPO_ROOT / "examples" / "aegis-memory-firewall"
AGENT_DIR = DEMO_DIR / "agent"


# --- sink catalog (per-pattern unit tests) ----------------------------------------


@pytest.mark.parametrize(
    "attr,func,receiver,keywords,expect_framework",
    [
        ("put", None, "store", (), "langgraph"),
        ("put", None, "self.memory_store", (), "langgraph"),
        ("put", None, "checkpointer", (), "langgraph"),
        (None, "add_messages", None, (), "langgraph"),
        ("upsert", None, "pinecone_index", (), "vectordb"),
        ("add_texts", None, "vectorstore", (), "vectordb"),
        ("remember", None, "self.scratchpad", (), "custom"),
        # Distinctive memory-write method — matched on the method alone, no name hint needed.
        ("store_intelligence", None, "self.memory", (), "aegis"),
        # Generic verb on a non-hinted receiver, matched by the memory-API keyword signature.
        ("add", None, "self.client", ("scope", "shared_with_agents"), "aegis"),
    ],
)
def test_sink_catalog_matches(attr, func, receiver, keywords, expect_framework):
    match = sinks.classify_call(attr=attr, func=func, receiver=receiver, keywords=keywords)
    assert match is not None
    assert match.framework == expect_framework


def test_sink_catalog_ignores_unrelated_calls():
    assert sinks.classify_call(attr="get", func=None, receiver="store") is None
    assert sinks.classify_call(attr="put", func=None, receiver="widget") is None
    assert sinks.classify_call(attr=None, func="print", receiver=None) is None
    # A plain local ``list.append`` is never a sink — even when the variable name contains
    # "store" (the old false-positive shape). ``append`` was dropped from the static matcher.
    assert sinks.classify_call(attr="append", func=None, receiver="stored") is None
    assert sinks.classify_call(attr="append", func=None, receiver="self.history") is None
    # A generic ``add`` on a non-memory receiver without an API signature is not a sink.
    assert sinks.classify_call(attr="add", func=None, receiver="self.client") is None


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


# --- the regression gate: cross-file ASI06 flow + the list.append false positive -----


def test_crossfile_store_intelligence_flow_is_flagged_asi06():
    """The canonical missed flow: untrusted web content -> helper -> store_intelligence (and the
    cross-file client.add) must be detected, ASI06-tagged, with a non-empty source->sink edge."""
    findings = analyze_project(TAINT_FIXTURES)
    flows = [f for f in findings if f.category.endswith("_to_memory")]
    assert flows, "expected the cross-file untrusted->memory flow to be detected"
    assert all(f.trust == "untrusted" for f in flows)
    assert all(f.owasp == "ASI06" for f in flows), "flow findings must carry the OWASP ASI06 tag"
    assert all(f.flow_path for f in flows), "each flow must carry a non-empty source->sink edge"

    # The distinctive-method sink (store_intelligence) is recognized despite a receiver named `memory`.
    assert any("store_intelligence" in f.sink.call for f in flows)
    # The signature sink (client.add(scope=...)) is recognized despite a receiver named `client`, and
    # its source resolves cross-file (the edge references the other fixture file).
    add_flow = next((f for f in flows if f.sink.call.endswith(".add")), None)
    assert add_flow is not None, "client.add(scope=...) must be recognized via its API signature"
    assert add_flow.sink.file.endswith("client.py")
    assert any(step["file"].endswith("hunter.py") for step in add_flow.flow_path), (
        "the client.add flow must trace its source across the file boundary into hunter.py"
    )


def test_crossfile_flow_is_in_derived_unsafe_memory_flows():
    """unsafe_memory_flows.json (the derived view) is non-empty for the fixture and points at a real
    memory-write sink line — never a list append."""
    result = run_inspection(TAINT_FIXTURES, write=False)
    flows = derive_unsafe_memory_flows(result.findings)
    assert flows, "unsafe_memory_flows must be non-empty for the cross-file fixture"
    calls = {f["sink"]["call"] for f in flows}
    assert any(c.endswith(".add") or "store_intelligence" in c for c in calls)
    assert all("append" not in f["sink"]["call"] for f in flows)
    assert all(f.get("owasp") == "ASI06" for f in flows)


def test_namecollision_flow_paths_resolve_per_file():
    """Two agents each define their own ``_format_for_storage`` fed by their own untrusted source.
    Each finding's flow_path must cite *its own* file — no cross-file contamination (the resolver
    must not resolve the helper by name to the first definition and stamp another file's lines)."""
    findings = analyze_project(NAMECOLLIDE_FIXTURES)
    flows = [f for f in findings if f.category.endswith("_to_memory")]
    by_file = {f.sink.file.rsplit("/", 1)[-1]: f for f in flows}
    assert "alpha_agent.py" in by_file and "beta_agent.py" in by_file, by_file

    for stem, f in by_file.items():
        assert f.flow_path, f"{stem} must carry a source->sink edge"
        cited = {step["file"].rsplit("/", 1)[-1] for step in f.flow_path}
        assert cited == {stem}, (
            f"{stem}'s flow_path must cite only its own file, got {cited}"
        )


def test_loop_demo_guard_write_flips_finding_green(tmp_path):
    """The fix->verify loop, proven: the *same* write is critical/red when unscreened and
    screened/green once the recommended ``guard.write(...)`` fix is applied — no auto-apply, just
    re-run. This is the loop the report promises (apply fix -> /aegis:inspect -> lane turns green)."""
    unscreened = (
        "import httpx\n"
        "class A:\n"
        "    def __init__(self, memory): self.memory = memory\n"
        "    def hunt(self, url):\n"
        "        raw = httpx.get(url)\n"
        "        self.memory.store_intelligence(content=f'intel: {raw}')\n"
    )
    screened = (
        "import httpx\n"
        "from aegis_memory import guard\n"
        "class A:\n"
        "    def __init__(self, memory): self.memory = memory\n"
        "    def hunt(self, url):\n"
        "        raw = httpx.get(url)\n"
        "        verdict = guard.write(f'intel: {raw}', trust_level='untrusted',"
        " scope='agent-shared', on_reject='return')\n"
        "        if verdict.allowed:\n"
        "            self.memory.store_intelligence(content=verdict.content)\n"
    )
    before = tmp_path / "before"; before.mkdir()
    after = tmp_path / "after"; after.mkdir()
    (before / "agent.py").write_text(unscreened, encoding="utf-8")
    (after / "agent.py").write_text(screened, encoding="utf-8")

    bflow = [f for f in analyze_project(before) if f.category.endswith("_to_memory")]
    aflow = [f for f in analyze_project(after) if f.category.endswith("_to_memory")]
    assert bflow and all(not f.screened and f.severity == "critical" for f in bflow), bflow
    assert aflow and all(f.screened and f.severity != "critical" for f in aflow), aflow


def test_discarded_verdict_does_not_screen_a_raw_write(tmp_path):
    """Soundness gate (codex P1): computing a guard verdict but writing the RAW value must NOT be
    screened — the fix/verify loop must never accept an unsafe patch. Screening is sink-tied: only
    a write that uses verdict.content (or a guard-protected receiver) counts."""
    unsafe = (
        "import httpx\n"
        "from aegis_memory import guard\n"
        "class A:\n"
        "    def __init__(self, memory): self.memory = memory\n"
        "    def hunt(self, url):\n"
        "        raw = httpx.get(url)\n"
        "        verdict = guard.write(raw, trust_level='untrusted', scope='agent-shared',"
        " on_reject='return')\n"
        "        self.memory.store_intelligence(content=raw)  # BUG: ignores verdict, writes raw\n"
    )
    d = tmp_path / "unsafe"; d.mkdir()
    (d / "agent.py").write_text(unsafe, encoding="utf-8")
    flows = [f for f in analyze_project(d) if f.category.endswith("_to_memory")]
    assert flows and all(not f.screened and f.severity == "critical" for f in flows), flows


def test_applied_guard_write_is_not_itself_a_sink(tmp_path):
    """codex P2: the recommended fix contains ``guard.write(value, trust_level=..., scope=...)`` —
    that screening call must NOT be re-flagged as a memory-write sink (nor an overbroad-shared
    finding) on rescan; only the real downstream write is a sink."""
    fixed = (
        "import httpx\n"
        "from aegis_memory import guard\n"
        "class A:\n"
        "    def __init__(self, memory): self.memory = memory\n"
        "    def hunt(self, url):\n"
        "        raw = httpx.get(url)\n"
        "        verdict = guard.write(raw, trust_level='untrusted', scope='agent-shared',"
        " on_reject='return')\n"
        "        if verdict.allowed:\n"
        "            self.memory.store_intelligence(content=verdict.content)\n"
    )
    d = tmp_path / "fixed"; d.mkdir()
    (d / "agent.py").write_text(fixed, encoding="utf-8")
    findings = analyze_project(d)
    assert all("guard.write" not in f.sink.call and "guard.protect" not in f.sink.call
               for f in findings), [f.sink.call for f in findings]
    # The single real sink is the store_intelligence write, and it's screened (uses verdict.content).
    flows = [f for f in findings if f.category.endswith("_to_memory")]
    assert flows and all(f.screened for f in flows)


def test_guard_protect_screens_only_its_own_receiver(tmp_path):
    """Sink-tied screening for ``guard.protect``: a write through the wrapped receiver is screened;
    a write to a *different*, unprotected store in the same function is not (no blanket green)."""
    src = (
        "import httpx\n"
        "from aegis_memory import guard\n"
        "def run(store, audit_store, url):\n"
        "    raw = httpx.get(url)\n"
        "    store = guard.protect(store, scope='agent-shared')\n"
        "    store.put(('ns',), 'k', {'text': raw})       # screened: through the protected store\n"
        "    audit_store.put(('ns',), 'k', {'text': raw}) # exposed: different, unprotected store\n"
    )
    d = tmp_path / "protect"; d.mkdir()
    (d / "agent.py").write_text(src, encoding="utf-8")
    flows = {f.sink.call: f for f in analyze_project(d) if f.category.endswith("_to_memory")}
    assert flows.get("store.put") and flows["store.put"].screened
    assert flows.get("audit_store.put") and not flows["audit_store.put"].screened


def test_generated_flow_fix_is_verdict_checked_and_tailored():
    """Task A: the generated fix uses the real verdict-checked API (never the old
    verdict-discarding ``guard.write(content, ...)``), built from the finding's own call site."""
    findings = analyze_project(TAINT_FIXTURES)
    flow = next(f for f in findings if "store_intelligence" in f.sink.call and not f.screened)
    fix = flow.fix
    assert "guard.write(" in fix and "verdict.allowed" in fix and "verdict.content" in fix
    assert 'on_reject="return"' in fix
    # Tailored to the real receiver/method, not a hardcoded ``store``.
    assert "guard.protect(self.memory" in fix
    assert flow.sink.call.split(".")[-1] in fix  # the real sink method appears in the rewritten call


def test_local_list_append_is_not_flagged():
    """The true negative: a plain ``stored.append(x)`` returned locally is NOT a memory sink, even
    though the variable name contains 'store' (the old false-positive shape)."""
    findings = analyze_project(TAINT_FIXTURES)
    append_findings = [f for f in findings if f.sink.file.endswith("local_list.py")]
    assert append_findings == [], f"local list.append must not be flagged, got {append_findings}"


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
    assert f' after">{result.score["score"]}<' in html


def test_real_before_score_renders_through_html_not_fallback(tmp_path):
    """A real run with a supplied before_score renders the computed values, never the
    standalone 86/29 fallbacks (the §2 score-rendering fix)."""
    out = tmp_path / "out"
    result = run_inspection(DEMO_DIR, out_dir=out, write=True, before_score=42)
    html = (out / "agent_memory_map.html").read_text(encoding="utf-8")
    assert ' before">42<' in html  # the real supplied "before" (risk-coloured span)
    assert f' after">{result.score["score"]}<' in html  # the real computed "after"
    assert ' before">86<' not in html and ' after">29<' not in html  # fallbacks not used
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
