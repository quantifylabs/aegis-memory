"""``agent_memory_map.html`` — the shareable, screenshot-first visual.

Self-contained single file (inline CSS/JS, no external CDN). Responsive / mobile-friendly.
Renders one source→memory lane per detected flow (so a multi-source project shows every
channel converging on shared memory), colours nodes by risk, and shows the heuristic score
transition in the header. The "after" value is kept non-zero on purpose — residual risk is
more credible than a green 0.

Both score endpoints come from real runs in the normal path: ``report.py`` passes the
computed ``after`` and a real ``before`` (a prior/unscreened run) when one is available. The
``86``/``29`` defaults below are **standalone-preview-only fallbacks** for calling
``render_html`` by hand with no scores — a real ``aegis inspect`` run never relies on them.
"""

from __future__ import annotations

import html
import json

from .findings import FLOW_CATEGORIES, Finding

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
    before_score: int = 86,  # standalone-preview-only fallback; real runs pass a measured "before"
    after_score: int | None = None,
    project_name: str = "agent project",
) -> str:
    # standalone-preview-only fallback (29) — real runs always pass the computed score.
    after = after_score if after_score is not None else score.get("score", 29)
    lanes_html, n_channels = _build_lanes(findings)
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
    caption = (
        f"{n_channels} untrusted source{'s' if n_channels != 1 else ''} "
        "converging on shared agent memory"
        if n_channels
        else "no untrusted source→memory flow detected at these sites"
    )
    return _TEMPLATE.format(
        project=html.escape(project_name),
        before=before_score,
        after=after,
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


def _node(title: str, sub: str, color: str) -> str:
    return (
        f'<div class="node {color}"><div class="ntitle">{html.escape(title)}</div>'
        f'<div class="nsub">{html.escape(sub)}</div></div>'
    )


def _build_lanes(findings: list[Finding]) -> tuple[str, int]:
    """One ``source → write → shared memory`` lane per detected flow, plus a converging
    decision outcome. Falls back to a single generic lane when no flow findings exist (keeps
    standalone preview and clean-project output legible)."""
    flows = [f for f in findings if f.category in FLOW_CATEGORIES]
    arrow = '<div class="arrow">&#8594;</div>'
    lanes: list[str] = []
    seen: set[tuple[str, int]] = set()
    for f in flows:
        loc = (f.sink.file, f.sink.line)
        if loc in seen:
            continue
        seen.add(loc)
        write_color = _node_color(f.severity, f.screened)
        source_sub = "tool output" if f.source == "tool_output" else "untrusted input"
        lane = (
            '<div class="lane">'
            + _node(_channel_label(f.sink.file), source_sub, "gray")
            + arrow
            + _node(f.sink.call, f"{f.sink.file.rsplit('/', 1)[-1]}:{f.sink.line}", write_color)
            + arrow
            + _node("shared memory", f.sink.framework, write_color)
            + "</div>"
        )
        lanes.append(lane)
    n = len(lanes)
    if not lanes:
        lanes.append(
            '<div class="lane">'
            + _node("source", "input", "gray")
            + arrow
            + _node("memory write", "sink", "gray")
            + arrow
            + _node("shared memory", "store", "gray")
            + "</div>"
        )
    # Converging outcome: red while any unscreened flow can poison the decision, else green.
    any_unscreened = any(not f.screened for f in flows)
    outcome_color = "red" if any_unscreened else "green"
    outcome = (
        '<div class="outcome">'
        + '<div class="arrow down">&#8595;</div>'
        + _node("privileged decision", "reads memory & acts", outcome_color)
        + "</div>"
    )
    return "".join(lanes) + outcome, n


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
  body {{ margin:0; background:
          radial-gradient(1200px 400px at 50% -120px, rgba(248,81,73,.10), transparent 70%) var(--bg);
          color:var(--text); font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif; }}
  .wrap {{ max-width:980px; margin:0 auto; padding:20px 16px 48px; }}
  header h1 {{ font-size:1.25rem; margin:0 0 4px; letter-spacing:.2px; }}
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
  .caption {{ color:var(--muted); font-size:.8rem; margin:0 2px 10px; }}
  .lanes {{ display:flex; flex-direction:column; gap:8px;
            background:var(--card); border:1px solid var(--line); border-radius:12px;
            padding:14px; margin-bottom:6px; }}
  .lane {{ display:flex; align-items:stretch; gap:6px; flex-wrap:nowrap; overflow-x:auto; }}
  .node {{ min-width:122px; flex:1 1 0; border-radius:10px; padding:10px 12px;
           border:1px solid var(--line); background:#0b0f14; }}
  .node .ntitle {{ font-weight:600; font-size:.85rem; word-break:break-word; }}
  .node .nsub {{ color:var(--muted); font-size:.72rem; margin-top:2px; word-break:break-word; }}
  .node.red {{ border-color:var(--red); box-shadow:inset 0 0 0 1px var(--red); }}
  .node.yellow {{ border-color:var(--yellow); }}
  .node.green {{ border-color:var(--green); box-shadow:inset 0 0 0 1px var(--green); }}
  .node.purple {{ border-color:var(--purple); }}
  .node.gray {{ border-color:var(--gray); }}
  .arrow {{ align-self:center; color:var(--muted); font-size:1.1rem; flex:0 0 auto; }}
  .outcome {{ display:flex; flex-direction:column; align-items:center; gap:4px; margin-top:10px;
              padding-top:10px; border-top:1px dashed var(--line); }}
  .outcome .node {{ flex:0 0 auto; min-width:220px; text-align:center; }}
  .arrow.down {{ font-size:1.2rem; }}
  .legend {{ display:flex; flex-wrap:wrap; gap:14px; margin:14px 0 18px; font-size:.78rem; color:var(--muted); }}
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
  @media (max-width:560px) {{
    .node {{ min-width:104px; }} .score {{ font-size:1.5rem; }}
    .outcome .node {{ min-width:160px; }}
  }}
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
  <p class="caption">{caption}</p>
  <div class="lanes">{lanes}</div>
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
