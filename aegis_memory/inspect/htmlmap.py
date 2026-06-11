"""``agent_memory_map.html`` — the shareable, screenshot-first visual.

Self-contained single file (inline CSS/JS, no external CDN). Responsive / mobile-friendly,
honours ``prefers-reduced-motion``. The design is grounded in the tool's own world — static
taint inspection of untrusted data crossing a **firewall boundary** into shared agent memory.
The signature element is the Aegis gate: every source→memory lane visibly crosses it, and the
gate shows whether that write was screened (passes) or not (blocked).

Both score endpoints come from real runs in the normal path: ``report.py`` passes the computed
``after`` and a real ``before`` (a prior/unscreened run) when one is available. The ``86``/``29``
defaults below are **standalone-preview-only fallbacks** for calling ``render_html`` by hand
with no scores — a real ``aegis inspect`` run never relies on them.
"""

from __future__ import annotations

import html
import json

from .findings import FLOW_CATEGORIES, Finding

# Risk colour legend (semantic — reserved strictly for flow nodes; SSOT §5 Feature 3).
_LEGEND = [
    ("green", "screened / governed"),
    ("yellow", "needs policy"),
    ("red", "unscreened write"),
    ("purple", "privileged / system"),
    ("gray", "unknown"),
]


def _node_color(severity: str, screened: bool) -> str:
    if screened:
        return "green"
    return {"critical": "red", "high": "red", "medium": "yellow", "low": "gray"}.get(severity, "gray")


def render_html(
    findings: list[Finding],
    score: dict,
    *,
    before_score: int = 86,  # standalone-preview-only fallback; real runs pass a measured "before"
    after_score: int | None = None,
    project_name: str = "agent project",
) -> str:
    # standalone-preview-only fallback (29) — real runs always pass the computed score.
    after = after_score if after_score is not None else score.get("score", 29)
    lanes_html, n_channels, any_unscreened = _build_lanes(findings)
    legend = "".join(
        f'<span class="legend-item"><span class="dot {c}"></span>{html.escape(label)}</span>'
        for c, label in _LEGEND
    )
    rows = "".join(
        f"<tr class='sev-{html.escape(f.severity)}'><td class='mono'>{html.escape(f.id)}</td>"
        f"<td><span class='badge {html.escape(f.severity)}'>{html.escape(f.severity)}</span></td>"
        f"<td class='mono'>{html.escape(f.confidence)}</td>"
        f"<td class='mono'>{html.escape(f.sink.file)}:{f.sink.line}</td>"
        f"<td>{html.escape(f.title)}</td></tr>"
        for f in findings
    )
    counts = score.get("counts", {})
    data_json = html.escape(json.dumps({"before": before_score, "after": after}))
    caption = (
        f"{n_channels} untrusted source{'s' if n_channels != 1 else ''} crossing the Aegis gate "
        "into shared agent memory"
        if n_channels
        else "no untrusted source→memory flow detected at these sites"
    )
    delta = before_score - after
    verdict = "poisonable" if any_unscreened else "governed"
    return _TEMPLATE.format(
        project=html.escape(project_name),
        before=before_score,
        after=after,
        delta=("-" if delta >= 0 else "+") + str(abs(delta)),
        verdict=verdict,
        lanes=lanes_html,
        caption=html.escape(caption),
        legend=legend,
        rows=rows or "<tr><td colspan='5'>No findings.</td></tr>",
        crit=counts.get("critical", 0),
        high=counts.get("high", 0),
        med=counts.get("medium", 0),
        low=counts.get("low", 0),
        data_json=data_json,
        rubric=html.escape(score.get("rubric", "")),
    )


def _channel_label(file_path: str) -> str:
    """Human channel name from the sink's file (general — just the module stem, no demo tuning)."""
    stem = file_path.rsplit("/", 1)[-1].removesuffix(".py")
    return stem.removeprefix("ingest_").replace("_", " ") or stem


def _build_lanes(findings: list[Finding]) -> tuple[str, int, bool]:
    """One ``source →| gate |→ shared memory`` lane per detected flow. The gate is the signature:
    it shows a pass (screened) or a block (unscreened) for each crossing. Falls back to a single
    generic lane when no flow findings exist (keeps standalone preview legible)."""
    flows = [f for f in findings if f.category in FLOW_CATEGORIES]
    lanes: list[str] = []
    seen: set[tuple[str, int]] = set()
    idx = 0
    for f in flows:
        loc = (f.sink.file, f.sink.line)
        if loc in seen:
            continue
        seen.add(loc)
        idx += 1
        color = _node_color(f.severity, f.screened)
        source_sub = "tool output" if f.source == "tool_output" else "untrusted input"
        gate_state = "pass" if f.screened else "block"
        # check = guarded crossing; bang = ungoverned crossing (no guard, reaches memory unchecked).
        gate_glyph = "&#10003;" if f.screened else "&#33;"
        gate_word = (
            "screened by Aegis — write allowed after scan"
            if f.screened
            else "no guard at this crossing — write reaches memory unchecked"
        )
        fname = f.sink.file.rsplit("/", 1)[-1]
        lanes.append(
            '<div class="lane">'
            f'<div class="src"><span class="idx">{idx:02d}</span>'
            f'<span class="src-t">{html.escape(_channel_label(f.sink.file))}</span>'
            f'<span class="src-s">{html.escape(source_sub)}</span></div>'
            '<div class="wire"></div>'
            f'<div class="sink {color}"><span class="call">{html.escape(f.sink.call)}</span>'
            f'<span class="loc">{html.escape(fname)}:{f.sink.line}</span></div>'
            f'<div class="gate {gate_state}" title="{gate_word}">'
            f'<span class="glyph">{gate_glyph}</span></div>'
            f'<div class="mem {color}"><span class="mem-t">shared memory</span>'
            f'<span class="mem-s">{html.escape(f.sink.framework)}</span></div>'
            "</div>"
        )
    n = len(lanes)
    if not lanes:
        lanes.append(
            '<div class="lane">'
            '<div class="src"><span class="idx">01</span><span class="src-t">source</span>'
            '<span class="src-s">input</span></div>'
            '<div class="wire"></div>'
            '<div class="sink gray"><span class="call">memory write</span>'
            '<span class="loc">sink</span></div>'
            '<div class="gate pass"><span class="glyph">&#8226;</span></div>'
            '<div class="mem gray"><span class="mem-t">shared memory</span>'
            '<span class="mem-s">store</span></div>'
            "</div>"
        )
    any_unscreened = any(not f.screened for f in flows)
    outcome_color = "red" if any_unscreened else "green"
    decision = (
        '<div class="outcome">'
        '<div class="down">&#8595;</div>'
        f'<div class="decide {outcome_color}"><span class="dec-t">privileged decision</span>'
        '<span class="dec-s">reads memory &amp; acts</span></div>'
        "</div>"
    )
    return "".join(lanes) + decision, n, any_unscreened


_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Aegis Memory Firewall Map — {project}</title>
<style>
  :root {{
    --ink:#0f1014; --panel:#16181f; --panel2:#1b1e27; --line:#2a2e3a;
    --text:#ece9e3; --muted:#969aa6; --accent:#57c2cf;       /* instrument cyan = structure/gate */
    --red:#e5534b; --yellow:#d39a36; --green:#46b46e; --purple:#9a73d6; --gray:#6b7280;
    --mono:ui-monospace,"SF Mono","JetBrains Mono",Menlo,Consolas,monospace;
    --sans:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;
  }}
  * {{ box-sizing:border-box; }}
  body {{
    margin:0; color:var(--text); font-family:var(--sans);
    background:
      linear-gradient(transparent 0 31px, rgba(87,194,207,.035) 31px 32px) 0 0/100% 32px,
      linear-gradient(90deg, transparent 0 31px, rgba(87,194,207,.035) 31px 32px) 0 0/32px 100%,
      radial-gradient(900px 360px at 78% -140px, rgba(87,194,207,.10), transparent 70%),
      var(--ink);
  }}
  .wrap {{ max-width:1000px; margin:0 auto; padding:26px 18px 56px; }}
  .eyebrow {{ font-family:var(--mono); font-size:.7rem; letter-spacing:.22em; text-transform:uppercase;
              color:var(--accent); margin:0 0 8px; }}
  h1 {{ font-family:var(--mono); font-size:1.5rem; font-weight:600; letter-spacing:-.01em; margin:0 0 4px; }}
  .sub {{ color:var(--muted); margin:0 0 20px; font-size:.92rem; }}
  .sub strong {{ color:var(--text); }}

  .panel {{ background:var(--panel); border:1px solid var(--line); border-radius:14px; }}
  .scorebar {{ display:flex; align-items:center; gap:18px; flex-wrap:wrap; padding:16px 18px; margin-bottom:16px; }}
  .gauge {{ display:flex; align-items:baseline; gap:10px; font-family:var(--mono); }}
  .gauge .before {{ font-size:2.1rem; font-weight:700; color:var(--red); }}
  .gauge .to {{ color:var(--muted); font-size:1.1rem; }}
  .gauge .after {{ font-size:2.1rem; font-weight:700; color:var(--green); }}
  .gauge .scale {{ color:var(--muted); font-size:.95rem; }}
  .meta {{ display:flex; flex-direction:column; gap:5px; }}
  .pill {{ font-family:var(--mono); font-size:.7rem; letter-spacing:.08em; text-transform:uppercase;
           color:var(--muted); border:1px solid var(--line); border-radius:999px; padding:3px 10px; align-self:flex-start; }}
  .pill.delta {{ color:var(--accent); border-color:rgba(87,194,207,.4); }}
  .counts {{ font-family:var(--mono); font-size:.78rem; color:var(--muted); }}
  .counts b {{ color:var(--text); font-weight:600; }}

  .caption {{ color:var(--muted); font-size:.85rem; margin:0 2px 12px; }}
  .caption b {{ color:var(--accent); font-weight:600; }}

  /* ---- the firewall diagram (the signature) ---- */
  .diagram {{ padding:16px 16px 10px; margin-bottom:8px; }}
  .lane {{
    display:grid; align-items:stretch; gap:0;
    grid-template-columns: 1.05fr 22px 1.25fr 52px 1fr;
    margin-bottom:10px;
  }}
  .src, .sink, .mem {{ border:1px solid var(--line); border-radius:10px; padding:9px 12px; background:var(--panel2);
                       display:flex; flex-direction:column; justify-content:center; min-width:0; }}
  .src .idx {{ font-family:var(--mono); font-size:.66rem; color:var(--accent); letter-spacing:.1em; }}
  .src-t {{ font-weight:600; font-size:.86rem; text-transform:capitalize; }}
  .src-s {{ color:var(--muted); font-size:.72rem; }}
  .call {{ font-family:var(--mono); font-size:.82rem; font-weight:600; word-break:break-all; }}
  .loc {{ font-family:var(--mono); color:var(--muted); font-size:.7rem; word-break:break-all; }}
  .mem-t {{ font-weight:600; font-size:.84rem; }}
  .mem-s {{ font-family:var(--mono); color:var(--muted); font-size:.7rem; }}
  .wire {{ align-self:center; height:2px; background:linear-gradient(90deg,var(--line),var(--accent)); opacity:.7; }}

  /* the gate column: a glowing cyan rail every lane crosses */
  .gate {{ position:relative; display:flex; align-items:center; justify-content:center; }}
  .gate::before {{ content:""; position:absolute; top:-5px; bottom:-5px; width:3px; left:50%; transform:translateX(-50%);
                   background:var(--accent); border-radius:2px; box-shadow:0 0 10px rgba(87,194,207,.55); }}
  .gate .glyph {{ position:relative; z-index:1; width:26px; height:26px; border-radius:50%;
                  display:flex; align-items:center; justify-content:center; font-size:.8rem; font-weight:700;
                  border:1px solid var(--line); background:var(--ink); }}
  .gate.pass .glyph {{ color:var(--green); border-color:var(--green); box-shadow:0 0 8px rgba(70,180,110,.5); }}
  .gate.block .glyph {{ color:var(--red); border-color:var(--red); box-shadow:0 0 8px rgba(229,83,75,.5); }}

  /* risk tint on the sink + memory nodes (semantic) */
  .sink.red, .mem.red {{ border-color:var(--red); box-shadow:inset 0 0 0 1px rgba(229,83,75,.5); }}
  .sink.yellow, .mem.yellow {{ border-color:var(--yellow); }}
  .sink.green, .mem.green {{ border-color:var(--green); box-shadow:inset 0 0 0 1px rgba(70,180,110,.45); }}
  .sink.gray, .mem.gray {{ border-color:var(--gray); }}

  .outcome {{ display:flex; flex-direction:column; align-items:center; gap:2px; margin-top:6px;
              padding-top:8px; border-top:1px dashed var(--line); }}
  .down {{ color:var(--accent); font-size:1.1rem; }}
  .decide {{ border:1px solid var(--line); border-radius:10px; padding:9px 16px; text-align:center; min-width:230px; }}
  .decide.red {{ border-color:var(--red); box-shadow:inset 0 0 0 1px rgba(229,83,75,.5); }}
  .decide.green {{ border-color:var(--green); box-shadow:inset 0 0 0 1px rgba(70,180,110,.45); }}
  .dec-t {{ display:block; font-weight:600; font-size:.86rem; }}
  .dec-s {{ display:block; color:var(--muted); font-size:.72rem; }}

  .legend {{ display:flex; flex-wrap:wrap; gap:14px; margin:14px 2px 20px; font-size:.76rem; color:var(--muted); }}
  .dot {{ display:inline-block; width:9px; height:9px; border-radius:50%; margin-right:6px; vertical-align:middle; }}
  .dot.red {{ background:var(--red); }} .dot.yellow {{ background:var(--yellow); }}
  .dot.green {{ background:var(--green); }} .dot.purple {{ background:var(--purple); }} .dot.gray {{ background:var(--gray); }}

  table {{ width:100%; border-collapse:collapse; font-size:.82rem; overflow:hidden; border-radius:14px;
           border:1px solid var(--line); background:var(--panel); }}
  th, td {{ text-align:left; padding:9px 11px; border-bottom:1px solid var(--line); vertical-align:top; }}
  th {{ font-family:var(--mono); color:var(--muted); font-weight:600; font-size:.72rem;
        letter-spacing:.06em; text-transform:uppercase; }}
  td.mono {{ font-family:var(--mono); font-size:.76rem; }}
  tr:last-child td {{ border-bottom:none; }}
  .badge {{ font-family:var(--mono); font-size:.66rem; padding:2px 8px; border-radius:999px; text-transform:uppercase; letter-spacing:.04em; }}
  .badge.critical {{ background:rgba(229,83,75,.16); color:var(--red); }}
  .badge.high {{ background:rgba(229,83,75,.12); color:var(--red); }}
  .badge.medium {{ background:rgba(211,154,54,.16); color:var(--yellow); }}
  .badge.low {{ background:rgba(107,114,128,.22); color:var(--muted); }}
  .rubric {{ color:var(--muted); font-size:.72rem; margin-top:12px; line-height:1.5; }}

  .lane {{ opacity:0; transform:translateY(4px); animation:rise .5s ease forwards; }}
  .lane:nth-child(2) {{ animation-delay:.05s; }} .lane:nth-child(3) {{ animation-delay:.10s; }}
  .lane:nth-child(4) {{ animation-delay:.15s; }} .lane:nth-child(5) {{ animation-delay:.20s; }}
  .lane:nth-child(6) {{ animation-delay:.25s; }}
  @keyframes rise {{ to {{ opacity:1; transform:none; }} }}
  @media (prefers-reduced-motion: reduce) {{ .lane {{ animation:none; opacity:1; transform:none; }} }}

  @media (max-width:620px) {{
    .lane {{ grid-template-columns:1fr; gap:6px; padding:10px; border:1px solid var(--line); border-radius:12px; background:var(--panel2); }}
    .src, .sink, .mem {{ background:var(--ink); }}
    .wire {{ display:none; }}
    .gate {{ height:30px; }}
    .gate::before {{ top:50%; bottom:auto; left:8px; right:8px; width:auto; height:3px; transform:translateY(-50%); }}
    .gauge .before, .gauge .after {{ font-size:1.6rem; }}
    .decide {{ min-width:0; width:100%; }}
  }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <p class="eyebrow">Aegis · static memory inspection</p>
    <h1>Memory Firewall Map</h1>
    <p class="sub">Untrusted memory flows in <strong>{project}</strong></p>
  </header>

  <div class="panel scorebar">
    <div class="gauge"><span class="before">{before}</span><span class="to">&#8594;</span><span class="after">{after}</span><span class="scale">/100</span></div>
    <div class="meta">
      <span class="pill">heuristic risk · {verdict}</span>
      <span class="pill delta">{delta} after screening</span>
    </div>
    <div class="counts">Critical <b>{crit}</b> &nbsp; High <b>{high}</b> &nbsp; Medium <b>{med}</b> &nbsp; Low <b>{low}</b></div>
  </div>

  <p class="caption"><b>{caption}</b></p>
  <div class="panel diagram">{lanes}</div>
  <div class="legend">{legend}</div>

  <table>
    <thead><tr><th>ID</th><th>Severity</th><th>Confidence</th><th>Location</th><th>Finding</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
  <p class="rubric">Score: {rubric}</p>
</div>
<script>var AEGIS_SCORE = JSON.parse("{data_json}".replace(/&quot;/g,'"'));</script>
</body>
</html>
"""
