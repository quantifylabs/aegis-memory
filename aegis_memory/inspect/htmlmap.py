"""``agent_memory_map.html`` — a proof-first memory-trace report (not a sales poster).

Self-contained single file (inline CSS, no external CDN, no JS framework). The information
architecture is **evidence, anchored to code**:

* a **faithful trace** of every untrusted source -> write sink -> shared-memory flow, each node
  carrying its real ``file:line`` and sink call. The edge style is the *only* place color
  carries meaning, and it carries exactly one provable distinction: **screened** (the write is
  guarded, so it's blocked at the gate) vs **exposed** (no guard in scope, so it reaches memory).
* a **live scan replay** panel showing the real ``ContentSecurityScanner.scan()`` verdict on a
  memory-poisoning payload — the action, the concrete detector that fired, and the literal text
  it matched. This is a real ``scan()`` call, never a hardcoded string.
* the full **findings table** below, the same data as ``findings.json`` / ``INSPECTION_REPORT.md``.

There is no stylized convergence cartoon and no "without/with" storytelling: a reviewer reads the
trace and the scan verdict and verifies each claim against a file and a line.

Scores come from real runs: ``report.py`` passes the computed ``after`` and a real ``before``
(an unscreened-exposure baseline, or a caller-supplied prior run). The ``86``/``29`` defaults are
**standalone-preview-only fallbacks** for calling ``render_html`` by hand with no run.
"""

from __future__ import annotations

import html
import json

from .findings import FLOW_CATEGORIES, Finding


def _risk_class(score: int) -> str:
    """Risk band for colouring a score number — high is alarming, low is calm. Lower is safer."""
    if score >= 67:
        return "risk-high"
    if score >= 34:
        return "risk-mid"
    return "risk-low"


def _channel_label(file_path: str) -> str:
    """Human channel name from the sink's file (general — module stem, no demo tuning)."""
    stem = file_path.rsplit("/", 1)[-1].removesuffix(".py")
    return (stem.removeprefix("ingest_").replace("_", " ") or stem)[:22]


def _flow_findings(findings: list[Finding]) -> list[Finding]:
    """The source->memory flow findings, deduped by sink location, in report order."""
    out: list[Finding] = []
    seen: set[tuple[str, int]] = set()
    for f in findings:
        if f.category not in FLOW_CATEGORIES:
            continue
        loc = (f.sink.file, f.sink.line)
        if loc in seen:
            continue
        seen.add(loc)
        out.append(f)
    return out


def render_html(
    findings: list[Finding],
    score: dict,
    *,
    before_score: int | None = 86,  # standalone-preview-only fallback; real runs pass a measured "before"
    after_score: int | None = None,
    project_name: str = "agent project",
    replay_result: dict | None = None,
) -> str:
    # standalone-preview-only fallback (29) — real runs always pass the computed score.
    after = after_score if after_score is not None else score.get("score", 29)
    flows = _flow_findings(findings)
    counts = score.get("counts", {})
    data_json = html.escape(json.dumps({"before": before_score, "after": after}))

    # --- score header (direction unambiguous; the spans are a stable contract) ---
    # Colour every number by its own risk value: high (~100) is alarming red, low is calm green.
    # "Lower is safer" — so a green 100 (the old bug) would have read like an A+ at maximum risk.
    if before_score is not None:
        delta = before_score - after
        score_block = (
            f'<span class="{_risk_class(before_score)} before">{before_score}</span>'
            f'<span class="to">&#8594;</span>'
            f'<span class="{_risk_class(after)} after">{after}</span><span class="scale">/100</span>'
        )
        score_note = (
            f'<span class="pill delta">{("-" if delta >= 0 else "+")}{abs(delta)} after screening</span>'
        )
    else:
        score_block = f'<span class="{_risk_class(after)} after">{after}</span><span class="scale">/100</span>'
        score_note = ""

    trace = _trace_section(flows)
    scan = _scan_panel(replay_result) if replay_result else ""

    # --- findings table (reference detail; same data as findings.json) ---
    rows = "".join(
        f"<tr class='sev-{html.escape(f.severity)}'><td class='mono'>{html.escape(f.id)}</td>"
        f"<td><span class='badge {html.escape(f.severity)}'>{html.escape(f.severity)}</span></td>"
        f"<td class='mono'>{html.escape(f.confidence)}</td>"
        f"<td class='mono'>{html.escape(f.sink.file)}:{f.sink.line}</td>"
        f"<td>{html.escape(f.title)}</td></tr>"
        for f in findings
    )
    table = (
        '<section class="below-fold"><h2 class="ref-h">All findings</h2>'
        '<p class="ref-sub">Reference detail — the same data as '
        '<code>findings.json</code> / <code>INSPECTION_REPORT.md</code>.</p>'
        '<div class="table-scroll"><table><thead><tr><th>ID</th><th>Severity</th><th>Confidence</th>'
        "<th>Location</th><th>Finding</th></tr></thead><tbody>"
        + (rows or "<tr><td colspan='5'>No findings.</td></tr>")
        + "</tbody></table></div></section>"
    )

    return _TEMPLATE.format(
        project=html.escape(project_name),
        score_block=score_block,
        score_note=score_note,
        crit=counts.get("critical", 0),
        high=counts.get("high", 0),
        med=counts.get("medium", 0),
        low=counts.get("low", 0),
        trace=trace,
        scan=scan,
        table=table,
        data_json=data_json,
        rubric=html.escape(score.get("rubric", "")),
    )


# ---------------------------------------------------------------------------------
# Faithful trace: one lane per source->sink->memory flow, anchored to file:line.
# ---------------------------------------------------------------------------------

def _trace_section(flows: list[Finding]) -> str:
    if not flows:
        return (
            '<section class="trace"><h2 class="sec-h">Untrusted memory flows</h2>'
            '<p class="empty">No untrusted source&#8594;memory flow was detected at these '
            'sites. (Absence finding — "not detected here", not a proof that none exists.)</p>'
            "</section>"
        )
    n_exposed = sum(1 for f in flows if not f.screened)
    n_screened = len(flows) - n_exposed
    explainer = _howto_explainer(n_exposed, n_screened)
    lanes = "".join(_lane(f) for f in flows)
    return (
        '<section class="trace"><h2 class="sec-h">Untrusted memory flows</h2>'
        f'<p class="sec-sub">{len(flows)} write(s) into shared memory &#183; '
        f'<b class="x-exposed">{n_exposed} reach memory unscreened</b> &#183; '
        f'{n_screened} blocked at a guard. Each lane is anchored to a file and line.</p>'
        f'{explainer}'
        '<div class="lanes">' + lanes + "</div></section>"
    )


def _howto_explainer(n_exposed: int, n_screened: int) -> str:
    """One calm, collapsible 'how to fix & verify' explainer — progressive disclosure, shown once.

    Serves the seasoned dev (collapsed by default, out of the way) and the engineer new to AI
    tooling (the explicit loop). The per-lane snippets carry the actual fix; this names the re-run
    action and points at the already-green screened lane as the live example."""
    if n_exposed == 0:
        return ""
    green_ref = (
        ' The green <b>blocked at gate</b> lane below is the live example: it&#8217;s safe because '
        'a guard already wraps that write &#8212; an exposed lane looks exactly like it once you fix '
        'and re-run.'
        if n_screened
        else ""
    )
    return (
        '<details class="howto"><summary>How to fix &amp; verify</summary>'
        '<div class="howto-body">'
        '<p>Each exposed lane below carries the exact, verdict-checked fix for <em>its own</em> '
        'write. To close the loop:</p>'
        '<ol>'
        '<li>Apply the fix shown on the lane in your code &#8212; screen the value through '
        '<code>guard.write(&#8230;)</code>, or wrap the store with <code>guard.protect(&#8230;)</code>.</li>'
        '<li>Save the file.</li>'
        '<li>Re-run <code>/aegis:inspect</code>.</li>'
        '<li>The lane flips from red <b>reaches memory</b> to green <b>blocked at gate</b>.</li>'
        '</ol>'
        f'<p class="howto-ref">{green_ref}</p>'
        '</div></details>'
    )


def _lane(f: Finding) -> str:
    screened = f.screened
    state = "screened" if screened else "exposed"
    status = "blocked at gate" if screened else "reaches memory"
    source_kind = html.escape(f.source)
    trust = html.escape(f.trust)
    channel = html.escape(_channel_label(f.sink.file))
    call = html.escape(f.sink.call)
    loc = f"{html.escape(f.sink.file)}:{f.sink.line}"
    fw = html.escape(f.sink.framework)
    mem_meta = f"key={html.escape(f.sink.key)}" if f.sink.key else "shared scope"
    # the screening boundary: a guard glyph (blocked) or a bare arrow (reaches memory)
    boundary = "&#9211;" if screened else "&#9654;"  # ⛛ gate vs ▶
    owasp = f'<span class="conf">OWASP {html.escape(f.owasp)}</span>' if f.owasp else ""
    return (
        f'<article class="lane {state}">'
        f'<div class="lane-head">'
        f'<span class="aeg">{html.escape(f.id)}</span>'
        f'<span class="badge {html.escape(f.severity)}">{html.escape(f.severity)}</span>'
        f'<span class="conf">{html.escape(f.confidence)}</span>'
        f"{owasp}"
        f'<span class="status {state}">{status}</span>'
        f"</div>"
        f'<div class="flow">'
        f'<div class="node src"><div class="nk">source</div>'
        f'<div class="nv">{channel}</div>'
        f'<div class="nm">{source_kind} &#183; <span class="trust {trust}">{trust}</span></div></div>'
        f'<div class="arrow"><span class="op">writes</span>&#8594;</div>'
        f'<div class="node sink"><div class="nk">write sink</div>'
        f'<div class="nv mono">{call}</div>'
        f'<div class="nm mono">{loc} · {fw}</div></div>'
        f'<div class="arrow {state}"><span class="op">{boundary}</span></div>'
        f'<div class="node mem"><div class="nk">memory</div>'
        f'<div class="nv">shared memory</div>'
        f'<div class="nm mono">{mem_meta}</div></div>'
        f"</div>"
        f"{_lane_fix(f)}"
        f"</article>"
    )


def _lane_fix(f: Finding) -> str:
    """Per-lane disclosure: the screened lane shows why it's green; an exposed lane shows its own
    verdict-checked fix + a single 're-run to verify' cue (no repeated step list — that lives once
    in the explainer above)."""
    if f.screened:
        return (
            '<p class="lane-note screened-note">This lane is <b>green</b> because a content-security '
            'guard already wraps this write. An exposed lane looks like this once you apply its fix '
            'and re-run.</p>'
        )
    fix = html.escape(f.fix)
    return (
        '<details class="lane-fix"><summary>Fix this lane'
        '<span class="cue"> &#8212; apply, then re-run <code>/aegis:inspect</code> to verify '
        '&#8594;</span></summary>'
        f'<pre class="fix-code"><code>{fix}</code></pre></details>'
    )


# ---------------------------------------------------------------------------------
# Live scan replay: the real scan() verdict, rendered as evidence.
# ---------------------------------------------------------------------------------

def _scan_panel(r: dict) -> str:
    wa = r.get("with_aegis", {})
    action = html.escape(str(wa.get("action", "")))
    blocked = not wa.get("allowed", True)
    payload = html.escape(r.get("payload", ""))
    if len(payload) > 160:
        payload = payload[:157] + "&#8230;"
    dets = wa.get("detections", []) or []
    det_chips = (
        "".join(
            f'<span class="det">{html.escape(str(d.get("type", "")))}'
            f' <span class="conf-n">{d.get("confidence", "")}</span></span>'
            for d in dets
        )
        or '<span class="det">none</span>'
    )
    matched = next((d.get("matched") for d in dets if d.get("matched")), "")
    matched_row = (
        f'<div class="row"><span class="k">matched</span>'
        f'<code class="ev">{html.escape(str(matched))}</code></div>'
        if matched
        else ""
    )
    verdict = (
        "write BLOCKED at the memory boundary" if blocked
        else "write allowed (no reject signal)"
    )
    vcls = "reject" if blocked else "allow"
    return (
        '<section class="scan"><h2 class="sec-h">Live scan replay '
        '<span class="real">real <code>scan()</code> call</span></h2>'
        '<div class="scan-card">'
        f'<div class="row"><span class="k">payload</span><code class="ev">{payload}</code></div>'
        f'<div class="row"><span class="k">action</span>'
        f'<span class="verdict-chip {vcls}">{action}</span></div>'
        f'<div class="row"><span class="k">detection</span><span class="dets">{det_chips}</span></div>'
        f"{matched_row}"
        f'<div class="row"><span class="k">verdict</span><span class="vsum {vcls}">{verdict}</span></div>'
        "</div></section>"
    )


# ---------------------------------------------------------------------------------
# Template (inline CSS; self-contained single file).
# ---------------------------------------------------------------------------------

_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Aegis memory inspection — {project}</title>
<style>
  :root {{
    --ink:#0f1014; --panel:#16181f; --panel2:#1b1e27; --line:#2a2e3a;
    --text:#ece9e3; --muted:#969aa6; --accent:#57c2cf;
    --danger:#e5534b; --safe:#46b46e; --soft:#8a90a0; --warn:#d39a36;
    --mono:ui-monospace,"SF Mono","JetBrains Mono",Menlo,Consolas,monospace;
    --sans:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;
  }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; color:var(--text); font-family:var(--sans); background:var(--ink); }}
  .wrap {{ max-width:1040px; margin:0 auto; padding:26px 18px 56px; }}
  .eyebrow {{ font-family:var(--mono); font-size:.7rem; letter-spacing:.22em; text-transform:uppercase;
              color:var(--accent); margin:0 0 8px; }}
  h1 {{ font-family:var(--mono); font-size:1.4rem; font-weight:600; letter-spacing:-.01em; margin:0 0 4px; }}
  .sub {{ color:var(--muted); margin:0 0 18px; font-size:.92rem; }}
  .sub strong {{ color:var(--text); }}

  .panel {{ background:var(--panel); border:1px solid var(--line); border-radius:14px; }}
  .scorebar {{ display:flex; align-items:center; gap:18px; flex-wrap:wrap; padding:16px 18px; margin-bottom:22px; }}
  .gauge {{ display:flex; align-items:baseline; gap:9px; font-family:var(--mono); }}
  .gauge .before, .gauge .after {{ font-size:2.0rem; font-weight:700; }}
  .gauge .to {{ color:var(--muted); font-size:1.1rem; }}
  .gauge .risk-high {{ color:var(--danger); }}
  .gauge .risk-mid {{ color:var(--warn); }}
  .gauge .risk-low {{ color:var(--safe); }}
  .gauge .scale {{ color:var(--muted); font-size:.95rem; }}
  .meta {{ display:flex; flex-direction:column; gap:5px; }}
  .pill {{ font-family:var(--mono); font-size:.7rem; letter-spacing:.06em; text-transform:uppercase;
           color:var(--muted); border:1px solid var(--line); border-radius:999px; padding:3px 10px; align-self:flex-start; }}
  .pill.delta {{ color:var(--accent); border-color:rgba(87,194,207,.4); }}
  .counts {{ font-family:var(--mono); font-size:.78rem; color:var(--muted); }}
  .counts b {{ color:var(--text); font-weight:600; }}

  .sec-h {{ font-family:var(--mono); font-size:1.0rem; font-weight:600; margin:0 0 4px; }}
  .sec-h .real {{ font-family:var(--mono); font-size:.66rem; font-weight:600; color:var(--accent);
                  border:1px solid rgba(87,194,207,.4); border-radius:999px; padding:2px 8px; margin-left:8px;
                  text-transform:uppercase; letter-spacing:.06em; vertical-align:middle; }}
  .sec-h .real code {{ color:var(--accent); }}
  .sec-sub {{ color:var(--muted); font-size:.82rem; margin:0 0 14px; }}
  .sec-sub b.x-exposed {{ color:var(--danger); font-weight:600; }}
  .empty {{ color:var(--muted); font-size:.85rem; }}

  /* trace lanes */
  .trace {{ margin-bottom:26px; }}
  .lanes {{ display:flex; flex-direction:column; gap:12px; }}
  .lane {{ border:1px solid var(--line); border-left-width:3px; border-radius:12px;
           background:var(--panel); padding:12px 14px; }}
  .lane.exposed {{ border-left-color:var(--danger); }}
  .lane.screened {{ border-left-color:var(--safe); }}
  .lane-head {{ display:flex; align-items:center; gap:9px; flex-wrap:wrap; margin-bottom:11px; font-size:.74rem; }}
  .lane-head .aeg {{ font-family:var(--mono); color:var(--muted); }}
  .lane-head .conf {{ font-family:var(--mono); color:var(--muted); font-size:.68rem;
                      border:1px solid var(--line); border-radius:6px; padding:1px 6px; }}
  .status {{ font-family:var(--mono); font-size:.68rem; text-transform:uppercase; letter-spacing:.05em;
             margin-left:auto; font-weight:700; }}
  .status.exposed {{ color:var(--danger); }}
  .status.screened {{ color:var(--safe); }}

  .flow {{ display:grid; grid-template-columns:1fr auto 1.1fr auto 1fr; align-items:stretch; gap:8px; }}
  .node {{ background:var(--panel2); border:1px solid var(--line); border-radius:10px; padding:9px 11px; min-width:0; }}
  .node .nk {{ font-family:var(--mono); font-size:.6rem; text-transform:uppercase; letter-spacing:.1em;
               color:var(--soft); margin-bottom:4px; }}
  .node .nv {{ font-size:.86rem; font-weight:600; word-break:break-word; }}
  .node .nv.mono, .node .nm.mono {{ font-family:var(--mono); }}
  .node .nv.mono {{ font-size:.8rem; }}
  .node .nm {{ font-size:.72rem; color:var(--muted); margin-top:3px; word-break:break-word; }}
  .trust {{ font-weight:700; }}
  .trust.untrusted {{ color:var(--danger); }}
  .trust.internal {{ color:var(--safe); }}
  .trust.unknown {{ color:var(--warn); }}
  .arrow {{ display:flex; flex-direction:column; align-items:center; justify-content:center;
            color:var(--soft); font-size:1.1rem; }}
  .arrow .op {{ font-family:var(--mono); font-size:.6rem; text-transform:uppercase; letter-spacing:.06em;
                color:var(--soft); margin-bottom:2px; }}
  .arrow.exposed {{ color:var(--danger); }}
  .arrow.screened {{ color:var(--safe); }}
  .node.mem {{ border-style:dashed; }}

  /* live scan panel */
  .scan {{ margin-bottom:26px; }}
  .scan-card {{ border:1px solid var(--line); border-radius:12px; background:var(--panel); padding:6px 14px; }}
  .scan-card .row {{ display:flex; gap:12px; align-items:baseline; padding:9px 0; border-bottom:1px solid var(--line); }}
  .scan-card .row:last-child {{ border-bottom:none; }}
  .scan-card .k {{ font-family:var(--mono); font-size:.66rem; text-transform:uppercase; letter-spacing:.08em;
                   color:var(--soft); min-width:78px; }}
  .ev {{ font-family:var(--mono); font-size:.78rem; color:var(--text); word-break:break-word; }}
  .verdict-chip {{ font-family:var(--mono); font-size:.72rem; font-weight:700; text-transform:uppercase;
                   border-radius:6px; padding:2px 9px; }}
  .verdict-chip.reject {{ background:rgba(229,83,75,.16); color:var(--danger); }}
  .verdict-chip.allow {{ background:rgba(70,180,110,.16); color:var(--safe); }}
  .dets {{ display:flex; flex-wrap:wrap; gap:6px; }}
  .det {{ font-family:var(--mono); font-size:.72rem; color:var(--text);
          border:1px solid var(--line); border-radius:6px; padding:1px 7px; }}
  .det .conf-n {{ color:var(--muted); }}
  .vsum {{ font-size:.82rem; font-weight:600; }}
  .vsum.reject {{ color:var(--safe); }}
  .vsum.allow {{ color:var(--warn); }}

  /* findings table */
  .below-fold {{ margin-top:30px; padding-top:18px; border-top:1px solid var(--line); }}
  .ref-h {{ font-family:var(--mono); font-size:.95rem; margin:0 0 3px; }}
  .ref-sub {{ color:var(--muted); font-size:.78rem; margin:0 0 12px; }}
  .ref-sub code {{ font-family:var(--mono); color:var(--text); }}
  .table-scroll {{ overflow-x:auto; border-radius:14px; -webkit-overflow-scrolling:touch; }}
  table {{ width:100%; border-collapse:collapse; font-size:.82rem; overflow:hidden; border-radius:14px;
           border:1px solid var(--line); background:var(--panel); }}
  td.mono {{ word-break:break-word; }}
  th, td {{ text-align:left; padding:9px 11px; border-bottom:1px solid var(--line); vertical-align:top; }}
  th {{ font-family:var(--mono); color:var(--muted); font-weight:600; font-size:.72rem;
        letter-spacing:.06em; text-transform:uppercase; }}
  td.mono {{ font-family:var(--mono); font-size:.76rem; }}
  tr:last-child td {{ border-bottom:none; }}
  .badge {{ font-family:var(--mono); font-size:.66rem; padding:2px 8px; border-radius:999px;
            text-transform:uppercase; letter-spacing:.04em; }}
  .badge.critical {{ background:rgba(229,83,75,.16); color:var(--danger); }}
  .badge.high {{ background:rgba(229,83,75,.12); color:var(--danger); }}
  .badge.medium {{ background:rgba(211,154,54,.16); color:var(--warn); }}
  .badge.low {{ background:rgba(107,114,128,.22); color:var(--muted); }}
  .rubric {{ color:var(--muted); font-size:.72rem; margin-top:14px; line-height:1.5; }}
  .rubric .prov {{ display:block; margin-top:6px; }}

  /* per-lane fix + how-to-fix explainer (progressive disclosure) */
  .howto {{ border:1px solid var(--line); border-radius:10px; background:var(--panel2);
            margin:0 0 14px; font-size:.84rem; }}
  .howto > summary {{ cursor:pointer; padding:9px 13px; color:var(--accent); font-family:var(--mono);
                      font-size:.74rem; letter-spacing:.04em; text-transform:uppercase; list-style:none; }}
  .howto > summary::-webkit-details-marker {{ display:none; }}
  .howto > summary::before {{ content:"+ "; color:var(--soft); }}
  .howto[open] > summary::before {{ content:"\\2212 "; }}
  .howto-body {{ padding:2px 15px 12px; color:var(--muted); }}
  .howto-body code {{ font-family:var(--mono); color:var(--text); }}
  .howto-body ol {{ margin:8px 0; padding-left:20px; line-height:1.7; }}
  .howto-ref {{ color:var(--muted); margin:6px 0 0; }}

  .lane-fix {{ margin-top:11px; border-top:1px solid var(--line); padding-top:9px; }}
  .lane-fix > summary {{ cursor:pointer; color:var(--accent); font-family:var(--mono); font-size:.72rem;
                         list-style:none; }}
  .lane-fix > summary::-webkit-details-marker {{ display:none; }}
  .lane-fix > summary::before {{ content:"\\25B8 "; color:var(--soft); }}
  .lane-fix[open] > summary::before {{ content:"\\25BE "; }}
  .lane-fix .cue {{ color:var(--muted); text-transform:none; letter-spacing:0; }}
  .lane-fix .cue code {{ color:var(--accent); }}
  .fix-code {{ margin:10px 0 2px; padding:11px 13px; background:var(--ink); border:1px solid var(--line);
               border-radius:9px; overflow-x:auto; font-family:var(--mono); font-size:.76rem;
               line-height:1.55; color:var(--text); white-space:pre; }}
  .lane-note {{ margin:11px 0 0; padding-top:9px; border-top:1px solid var(--line);
                font-size:.78rem; color:var(--muted); }}
  .screened-note b {{ color:var(--safe); }}
  .footnote {{ color:var(--soft); font-size:.72rem; margin:18px 0 0; }}
  .footnote code {{ font-family:var(--mono); color:var(--muted); }}

  @media (max-width:720px) {{
    .flow {{ grid-template-columns:1fr; }}
    .arrow {{ flex-direction:row; gap:6px; padding:2px 0; }}
    .arrow .op {{ margin-bottom:0; }}
    .status {{ margin-left:0; }}
    .gauge .before, .gauge .after {{ font-size:1.7rem; }}
  }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <p class="eyebrow">Aegis · static memory inspection</p>
    <h1>Memory inspection — {project}</h1>
    <p class="sub">Untrusted source&#8594;memory flows, anchored to <strong>file + line</strong></p>
    <p class="sub engines"><strong>Runtime content scanner:</strong> benchmarked (the live
      <code>scan()</code> replay). &nbsp;<strong>Static memory-map</strong> (flows, findings, score
      below): <strong>heuristic, preliminary, not yet benchmarked</strong> — best-effort,
      bounded-depth dataflow. Flow findings are tagged <strong>OWASP ASI06</strong>.</p>
  </header>

  <div class="panel scorebar">
    <div class="gauge">{score_block}</div>
    <div class="meta">
      <span class="pill">Memory Risk Score &#8212; 100 = maximum risk &#183; lower is safer</span>
      {score_note}
    </div>
    <div class="counts">Critical <b>{crit}</b> &nbsp; High <b>{high}</b> &nbsp; Medium <b>{med}</b> &nbsp; Low <b>{low}</b></div>
  </div>

  {trace}
  {scan}
  {table}
  <p class="rubric">Score: {rubric}
    <span class="prov">Findings are anchored to a file + line + sink. Absence findings say
    &ldquo;not detected at this site&rdquo;, never &ldquo;none exist&rdquo;. Confidence:
    EXTRACTED (same-scope dataflow), INFERRED (cross-call heuristic), AMBIGUOUS (source unresolved).</span>
  </p>
  <p class="footnote">Full source&#8594;sink paths and machine-readable findings are in
    <code>aegis-out/</code> (<code>INSPECTION_REPORT.md</code>, <code>findings.json</code>).</p>
</div>
<script>var AEGIS_SCORE = JSON.parse("{data_json}".replace(/&quot;/g,'"'));</script>
</body>
</html>
"""
