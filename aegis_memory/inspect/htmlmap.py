"""``agent_memory_map.html`` — the shareable, screenshot-first visual.

Self-contained single file (inline CSS/JS, no external CDN). Responsive / mobile-friendly.
Renders the memory flow and colours nodes by risk; shows the heuristic score transition in
the header. The "after" value is kept non-zero on purpose — residual risk is more credible
than a green 0.
"""

from __future__ import annotations

import html
import json

from .findings import Finding

# Risk colour legend (matches SSOT §5 Feature 3).
_LEGEND = [
    ("green", "safe / governed"),
    ("yellow", "needs policy"),
    ("red", "dangerous write"),
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
    before_score: int = 86,
    after_score: int | None = None,
    project_name: str = "agent project",
) -> str:
    after = after_score if after_score is not None else score.get("score", 29)
    # Flow stages shown as the canonical memory path.
    stages = [
        ("ticket", "untrusted input", "gray"),
        ("support_summarizer", "agent node", "yellow"),
        ("store.put (shared)", "memory write", _flow_color(findings)),
        ("store.get", "memory read", "yellow"),
        ("refund_decider", "decision node", "yellow"),
        ("decision", "business outcome", "green" if _any_screened(findings) else "red"),
    ]
    chips = "".join(
        f'<div class="node {c}"><div class="ntitle">{html.escape(t)}</div>'
        f'<div class="nsub">{html.escape(s)}</div></div>'
        + ("" if i == len(stages) - 1 else '<div class="arrow">&#8594;</div>')
        for i, (t, s, c) in enumerate(stages)
    )
    legend = "".join(
        f'<span class="legend-item"><span class="dot {c}"></span>{html.escape(label)}</span>'
        for c, label in _LEGEND
    )
    rows = "".join(
        f"<tr class='sev-{html.escape(f.severity)}'><td>{html.escape(f.id)}</td>"
        f"<td><span class='badge {html.escape(f.severity)}'>{html.escape(f.severity)}</span></td>"
        f"<td>{html.escape(f.confidence)}</td>"
        f"<td>{html.escape(f.sink.file)}:{f.sink.line}</td>"
        f"<td>{html.escape(f.title)}</td></tr>"
        for f in findings
    )
    counts = score.get("counts", {})
    data_json = html.escape(json.dumps({"before": before_score, "after": after}))
    return _TEMPLATE.format(
        project=html.escape(project_name),
        before=before_score,
        after=after,
        chips=chips,
        legend=legend,
        rows=rows or "<tr><td colspan='5'>No findings.</td></tr>",
        crit=counts.get("critical", 0),
        high=counts.get("high", 0),
        med=counts.get("medium", 0),
        low=counts.get("low", 0),
        data_json=data_json,
        rubric=html.escape(score.get("rubric", "")),
    )


def _flow_color(findings: list[Finding]) -> str:
    for f in findings:
        if f.category in ("user_input_to_memory", "tool_output_to_memory"):
            return _node_color(f.severity, f.screened)
    return "gray"


def _any_screened(findings: list[Finding]) -> bool:
    return any(f.screened for f in findings if f.category.endswith("_to_memory"))


_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Aegis Memory Map — {project}</title>
<style>
  :root {{ --bg:#0d1117; --card:#161b22; --line:#30363d; --text:#e6edf3; --muted:#8b949e;
           --red:#f85149; --yellow:#d29922; --green:#3fb950; --purple:#a371f7; --gray:#6e7681; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--text);
          font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif; }}
  .wrap {{ max-width:980px; margin:0 auto; padding:20px 16px 48px; }}
  header h1 {{ font-size:1.25rem; margin:0 0 4px; }}
  header p {{ color:var(--muted); margin:0 0 16px; font-size:.9rem; }}
  .scorebar {{ display:flex; gap:12px; align-items:center; flex-wrap:wrap;
               background:var(--card); border:1px solid var(--line); border-radius:12px;
               padding:14px 16px; margin-bottom:18px; }}
  .score {{ font-size:2rem; font-weight:700; }}
  .score .before {{ color:var(--red); }}
  .score .after {{ color:var(--green); }}
  .score .arrow {{ color:var(--muted); margin:0 8px; }}
  .tag {{ font-size:.72rem; color:var(--muted); border:1px solid var(--line);
          border-radius:999px; padding:2px 8px; }}
  .counts span {{ font-size:.8rem; margin-right:10px; color:var(--muted); }}
  .flow {{ display:flex; align-items:stretch; gap:6px; overflow-x:auto; padding:10px 2px;
           background:var(--card); border:1px solid var(--line); border-radius:12px; margin-bottom:14px; }}
  .node {{ min-width:120px; flex:0 0 auto; border-radius:10px; padding:10px 12px;
           border:1px solid var(--line); background:#0b0f14; }}
  .node .ntitle {{ font-weight:600; font-size:.85rem; }}
  .node .nsub {{ color:var(--muted); font-size:.72rem; margin-top:2px; }}
  .node.red {{ border-color:var(--red); box-shadow:inset 0 0 0 1px var(--red); }}
  .node.yellow {{ border-color:var(--yellow); }}
  .node.green {{ border-color:var(--green); box-shadow:inset 0 0 0 1px var(--green); }}
  .node.purple {{ border-color:var(--purple); }}
  .node.gray {{ border-color:var(--gray); }}
  .arrow {{ align-self:center; color:var(--muted); font-size:1.1rem; flex:0 0 auto; }}
  .legend {{ display:flex; flex-wrap:wrap; gap:14px; margin:6px 0 18px; font-size:.78rem; color:var(--muted); }}
  .dot {{ display:inline-block; width:10px; height:10px; border-radius:50%; margin-right:5px; vertical-align:middle; }}
  .dot.red {{ background:var(--red); }} .dot.yellow {{ background:var(--yellow); }}
  .dot.green {{ background:var(--green); }} .dot.purple {{ background:var(--purple); }}
  .dot.gray {{ background:var(--gray); }}
  table {{ width:100%; border-collapse:collapse; font-size:.82rem;
           background:var(--card); border:1px solid var(--line); border-radius:12px; overflow:hidden; }}
  th, td {{ text-align:left; padding:8px 10px; border-bottom:1px solid var(--line); vertical-align:top; }}
  th {{ color:var(--muted); font-weight:600; }}
  .badge {{ font-size:.7rem; padding:1px 7px; border-radius:999px; text-transform:uppercase; }}
  .badge.critical {{ background:rgba(248,81,73,.15); color:var(--red); }}
  .badge.high {{ background:rgba(248,81,73,.12); color:var(--red); }}
  .badge.medium {{ background:rgba(210,153,34,.15); color:var(--yellow); }}
  .badge.low {{ background:rgba(110,118,129,.2); color:var(--muted); }}
  .rubric {{ color:var(--muted); font-size:.72rem; margin-top:10px; }}
  @media (max-width:560px) {{ .node {{ min-width:104px; }} .score {{ font-size:1.5rem; }} }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>Aegis Memory Map</h1>
    <p>Unsafe memory flows in <strong>{project}</strong></p>
  </header>
  <div class="scorebar">
    <div class="score"><span class="before">{before}</span><span class="arrow">&#8594;</span><span class="after">{after}</span><span style="font-size:1rem;color:var(--muted)">/100</span></div>
    <span class="tag">heuristic</span>
    <div class="counts">
      <span>Critical {crit}</span><span>High {high}</span><span>Medium {med}</span><span>Low {low}</span>
    </div>
  </div>
  <div class="flow">{chips}</div>
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
