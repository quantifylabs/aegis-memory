"""``agent_memory_map.html`` — the shareable, screenshot-first visual.

Self-contained single file (inline CSS + inline SVG, no external CDN). The information
architecture is a **convergence before/after view**: many untrusted sources fan into one
shared-memory node, and two side-by-side states tell the story a non-expert can read in a
glance —

* **Without Aegis** — the untrusted writes reach shared memory, which is *poisoned*, and the
  privileged decision is *compromised*.
* **With aegis inspect** — an inspect checkpoint sits on the write path and *rejects* the
  malicious writes at the memory boundary, so memory stays *clean* and the decision is *trusted*.

The convergence shape (many → one) is the argument; the firewall's position on the write path
is drawn, not asserted. This is the general renderer for **any** project ``aegis inspect`` runs
on — source/sink counts are variable and the demo is just the showcase input.

Scores come from real runs: ``report.py`` passes the computed ``after`` and a real ``before``
(an unscreened baseline) when one exists; with no baseline the header shows a single score and
no arrow. The ``86``/``29`` defaults are **standalone-preview-only fallbacks** for calling
``render_html`` by hand with no run.
"""

from __future__ import annotations

import html
import json

from .findings import FLOW_CATEGORIES, Finding

# Two color meanings only (SSOT §5 / §3 of the redesign brief): danger vs safe/governed.
_LEGEND = [
    ("danger", "untrusted write (poison)"),
    ("safe", "screened · rejected at the gate"),
    ("muted", "not flagged"),
]

_MAX_SOURCES = 6  # beyond this we group the tail into a "+N more" node


def _is_danger(f: Finding) -> bool:
    """A flow that would poison memory: untrusted, unscreened, and high-severity."""
    return f.trust == "untrusted" and not f.screened and f.severity in ("critical", "high")


def _channel_label(file_path: str) -> str:
    """Human channel name from the sink's file (general — module stem, no demo tuning)."""
    stem = file_path.rsplit("/", 1)[-1].removesuffix(".py")
    return (stem.removeprefix("ingest_").replace("_", " ") or stem)[:18]


def _flow_sources(findings: list[Finding]) -> list[tuple[str, bool]]:
    """Distinct untrusted source channels feeding memory, as (label, danger). Deduped by
    sink location, capped with a '+N more' tail so the fan-in still reads for big projects."""
    out: list[tuple[str, bool]] = []
    seen: set[tuple[str, int]] = set()
    for f in findings:
        if f.category not in FLOW_CATEGORIES:
            continue
        loc = (f.sink.file, f.sink.line)
        if loc in seen:
            continue
        seen.add(loc)
        out.append((_channel_label(f.sink.file), _is_danger(f)))
    if len(out) > _MAX_SOURCES:
        head = out[: _MAX_SOURCES - 1]
        tail = out[_MAX_SOURCES - 1 :]
        head.append((f"+{len(tail)} more", any(d for _, d in tail)))
        out = head
    return out


def render_html(
    findings: list[Finding],
    score: dict,
    *,
    before_score: int | None = 86,  # standalone-preview-only fallback; real runs pass a measured "before"
    after_score: int | None = None,
    project_name: str = "agent project",
) -> str:
    # standalone-preview-only fallback (29) — real runs always pass the computed score.
    after = after_score if after_score is not None else score.get("score", 29)
    sources = _flow_sources(findings)
    n = len(sources)
    has_flows = n > 0

    counts = score.get("counts", {})
    data_json = html.escape(json.dumps({"before": before_score, "after": after}))

    # --- score header (direction unambiguous; "after" non-zero on purpose) ---
    if before_score is not None and has_flows:
        delta = before_score - after
        score_block = (
            f'<span class="before">{before_score}</span>'
            f'<span class="to">&#8594;</span>'
            f'<span class="after">{after}</span><span class="scale">/100</span>'
        )
        score_note = (
            f'<span class="pill delta">{("-" if delta >= 0 else "+")}{abs(delta)} after screening</span>'
        )
    else:
        score_block = f'<span class="after">{after}</span><span class="scale">/100</span>'
        score_note = ""

    # --- the two state cards (or a single governed card when there are no untrusted flows) ---
    if has_flows:
        body = (
            '<div class="states">'
            + _state_card(sources, screened=False)
            + _state_card(sources, screened=True)
            + "</div>"
        )
    else:
        body = (
            '<div class="states"><section class="state safe-state">'
            '<h2 class="state-h">No untrusted flows</h2>'
            '<p class="state-cap">No untrusted source&#8594;memory flow was detected at these '
            'sites. Memory is governed by default.</p></section></div>'
        )

    legend = "".join(
        f'<span class="legend-item"><span class="dot {c}"></span>{html.escape(label)}</span>'
        for c, label in _LEGEND
    )

    # --- findings table, moved OUT of the hero (below the fold) ---
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
        "<table><thead><tr><th>ID</th><th>Severity</th><th>Confidence</th>"
        "<th>Location</th><th>Finding</th></tr></thead><tbody>"
        + (rows or "<tr><td colspan='5'>No findings.</td></tr>")
        + "</tbody></table></section>"
    )

    return _TEMPLATE.format(
        project=html.escape(project_name),
        score_block=score_block,
        score_note=score_note,
        crit=counts.get("critical", 0),
        high=counts.get("high", 0),
        med=counts.get("medium", 0),
        low=counts.get("low", 0),
        body=body,
        legend=legend,
        table=table,
        data_json=data_json,
        rubric=html.escape(score.get("rubric", "")),
    )


# ---------------------------------------------------------------------------------
# Inline SVG convergence diagram (no CDN; scales responsively via viewBox).
# ---------------------------------------------------------------------------------

def _state_card(sources: list[tuple[str, bool]], *, screened: bool) -> str:
    title = "With aegis inspect" if screened else "Without Aegis"
    cap = (
        "Malicious writes are rejected at the memory boundary &#8594; memory stays clean and "
        "the decision is trusted."
        if screened
        else "Untrusted writes reach shared memory &#8594; memory is poisoned and the decision "
        "is compromised."
    )
    svg = _convergence_svg(sources, screened=screened)
    cls = "state safe-state" if screened else "state danger-state"
    return (
        f'<section class="{cls}">'
        f'<h2 class="state-h">{title}</h2>'
        f'<div class="svg-wrap">{svg}</div>'
        f'<p class="state-cap">{cap}</p>'
        "</section>"
    )


def _convergence_svg(sources: list[tuple[str, bool]], *, screened: bool) -> str:
    n = max(1, len(sources))
    SW, SH, GAP, TOP = 116, 26, 12, 18
    band_h = n * SH + (n - 1) * GAP
    src_x = 6
    mem_w, mem_h, mem_x = 104, 52, 256
    gate_x = 210
    cy = TOP + band_h / 2
    mem_y = cy - mem_h / 2
    dec_w, dec_h, dec_x = 104, 40, 256
    dec_y = max(mem_y + mem_h + 30, TOP + band_h - dec_h)
    total_h = max(TOP + band_h, dec_y + dec_h) + 14

    danger_col, safe_col, muted_col, ink, line = (
        "#e5534b", "#46b46e", "#8a90a0", "#0f1014", "#2a2e3a"
    )
    parts: list[str] = [
        f'<svg viewBox="0 0 372 {total_h:.0f}" width="100%" '
        f'preserveAspectRatio="xMidYMid meet" role="img" '
        f'aria-label="convergence diagram, {"with" if screened else "without"} Aegis">',
        '<defs>'
        f'<marker id="ah{int(screened)}" markerWidth="7" markerHeight="7" refX="6" refY="3" '
        f'orient="auto"><path d="M0,0 L6,3 L0,6 Z" fill="{muted_col}"/></marker>'
        f'<marker id="ahg{int(screened)}" markerWidth="7" markerHeight="7" refX="6" refY="3" '
        f'orient="auto"><path d="M0,0 L6,3 L0,6 Z" fill="{safe_col}"/></marker>'
        "</defs>",
    ]

    mem_cx, mem_cy = mem_x, mem_y + mem_h / 2  # left-center of the memory node (fan-in target)
    for i, (label, danger) in enumerate(sources or [("source", True)]):
        sy = TOP + i * (SH + GAP)
        scy = sy + SH / 2
        sxr = src_x + SW
        if screened and danger:
            # rejected at the gate: stub line to the gate + a red ✕, never reaches memory
            parts.append(
                f'<line x1="{sxr}" y1="{scy:.1f}" x2="{gate_x - 2}" y2="{scy:.1f}" '
                f'stroke="{danger_col}" stroke-width="2.4"/>'
            )
            parts.append(
                f'<text x="{gate_x + 4:.0f}" y="{scy + 3.5:.1f}" font-size="11" '
                f'fill="{danger_col}" font-weight="700">&#10005;</text>'
            )
        else:
            col = danger_col if (danger and not screened) else (safe_col if screened else muted_col)
            mk = "ahg" if screened else "ah"
            sw = "2.6" if (danger and not screened) else "1.4"
            parts.append(
                f'<path d="M{sxr},{scy:.1f} C{(sxr + mem_cx) / 2:.0f},{scy:.1f} '
                f'{(sxr + mem_cx) / 2:.0f},{mem_cy:.1f} {mem_cx - 4},{mem_cy:.1f}" '
                f'fill="none" stroke="{col}" stroke-width="{sw}" marker-end="url(#{mk}{int(screened)})"/>'
            )
        danger_chip = danger_col if danger else muted_col
        parts.append(
            f'<rect x="{src_x}" y="{sy}" width="{SW}" height="{SH}" rx="7" '
            f'fill="{ink}" stroke="{line}"/>'
            f'<rect x="{src_x}" y="{sy}" width="3.5" height="{SH}" rx="2" fill="{danger_chip}"/>'
            f'<text x="{src_x + 11}" y="{scy + 4:.1f}" font-size="11" fill="#ece9e3">'
            f"{html.escape(label)}</text>"
        )

    # the gate (right side only): a glowing cyan rail on the write path with a shield
    if screened:
        parts.append(
            f'<rect x="{gate_x - 3}" y="{TOP - 6:.0f}" width="6" height="{band_h + 12:.0f}" rx="3" '
            f'fill="#57c2cf"/>'
            f'<rect x="{gate_x - 13}" y="{cy - 13:.1f}" width="26" height="26" rx="6" '
            f'fill="{ink}" stroke="#57c2cf"/>'
            f'<text x="{gate_x:.0f}" y="{cy + 4:.1f}" font-size="12" text-anchor="middle" '
            f'fill="#57c2cf" font-weight="700">&#128737;</text>'
        )

    # memory node (poisoned / clean) — the single convergence point
    mem_stroke = safe_col if screened else danger_col
    mem_word = "clean" if screened else "poisoned"
    parts.append(
        f'<rect x="{mem_x}" y="{mem_y:.1f}" width="{mem_w}" height="{mem_h}" rx="10" '
        f'fill="{ink}" stroke="{mem_stroke}" stroke-width="1.6"/>'
        f'<text x="{mem_x + mem_w / 2:.0f}" y="{mem_y + 21:.1f}" font-size="11.5" '
        f'text-anchor="middle" fill="#ece9e3" font-weight="600">shared memory</text>'
        f'<text x="{mem_x + mem_w / 2:.0f}" y="{mem_y + 38:.1f}" font-size="11" '
        f'text-anchor="middle" fill="{mem_stroke}" font-weight="700">{mem_word}</text>'
    )

    # arrow memory -> decision, and the decision node (compromised / trusted)
    dcx = dec_x + dec_w / 2
    parts.append(
        f'<line x1="{mem_x + mem_w / 2:.0f}" y1="{mem_y + mem_h:.1f}" x2="{dcx:.0f}" '
        f'y2="{dec_y - 2:.1f}" stroke="{muted_col}" stroke-width="1.6" '
        f'marker-end="url(#ah{int(screened)})"/>'
    )
    dec_stroke = safe_col if screened else danger_col
    dec_word = "trusted" if screened else "compromised"
    parts.append(
        f'<rect x="{dec_x}" y="{dec_y:.1f}" width="{dec_w}" height="{dec_h}" rx="9" '
        f'fill="{ink}" stroke="{dec_stroke}" stroke-width="1.6"/>'
        f'<text x="{dcx:.0f}" y="{dec_y + 16:.1f}" font-size="11" text-anchor="middle" '
        f'fill="#ece9e3" font-weight="600">decision</text>'
        f'<text x="{dcx:.0f}" y="{dec_y + 30:.1f}" font-size="10.5" text-anchor="middle" '
        f'fill="{dec_stroke}" font-weight="700">{dec_word}</text>'
    )
    parts.append("</svg>")
    return "".join(parts)


_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Aegis Memory Firewall Map — {project}</title>
<style>
  :root {{
    --ink:#0f1014; --panel:#16181f; --panel2:#1b1e27; --line:#2a2e3a;
    --text:#ece9e3; --muted:#969aa6; --accent:#57c2cf;
    --danger:#e5534b; --safe:#46b46e; --soft:#8a90a0;
    --mono:ui-monospace,"SF Mono","JetBrains Mono",Menlo,Consolas,monospace;
    --sans:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;
  }}
  * {{ box-sizing:border-box; }}
  body {{
    margin:0; color:var(--text); font-family:var(--sans);
    background:
      radial-gradient(900px 360px at 78% -150px, rgba(87,194,207,.10), transparent 70%),
      var(--ink);
  }}
  .wrap {{ max-width:1040px; margin:0 auto; padding:26px 18px 56px; }}
  .eyebrow {{ font-family:var(--mono); font-size:.7rem; letter-spacing:.22em; text-transform:uppercase;
              color:var(--accent); margin:0 0 8px; }}
  h1 {{ font-family:var(--mono); font-size:1.5rem; font-weight:600; letter-spacing:-.01em; margin:0 0 4px; }}
  .sub {{ color:var(--muted); margin:0 0 18px; font-size:.92rem; }}
  .sub strong {{ color:var(--text); }}

  .panel {{ background:var(--panel); border:1px solid var(--line); border-radius:14px; }}
  .scorebar {{ display:flex; align-items:center; gap:18px; flex-wrap:wrap; padding:16px 18px; margin-bottom:16px; }}
  .gauge {{ display:flex; align-items:baseline; gap:9px; font-family:var(--mono); }}
  .gauge .before {{ font-size:2.1rem; font-weight:700; color:var(--danger); }}
  .gauge .to {{ color:var(--muted); font-size:1.1rem; }}
  .gauge .after {{ font-size:2.1rem; font-weight:700; color:var(--safe); }}
  .gauge .scale {{ color:var(--muted); font-size:.95rem; }}
  .meta {{ display:flex; flex-direction:column; gap:5px; }}
  .pill {{ font-family:var(--mono); font-size:.7rem; letter-spacing:.06em; text-transform:uppercase;
           color:var(--muted); border:1px solid var(--line); border-radius:999px; padding:3px 10px; align-self:flex-start; }}
  .pill.delta {{ color:var(--accent); border-color:rgba(87,194,207,.4); }}
  .counts {{ font-family:var(--mono); font-size:.78rem; color:var(--muted); }}
  .counts b {{ color:var(--text); font-weight:600; }}

  /* the hero: two convergence states */
  .states {{ display:flex; gap:14px; align-items:stretch; }}
  .state {{ flex:1 1 0; min-width:0; border:1px solid var(--line); border-radius:14px;
            background:var(--panel); padding:14px 14px 12px; display:flex; flex-direction:column; }}
  .danger-state {{ box-shadow:inset 0 2px 0 var(--danger); }}
  .safe-state {{ box-shadow:inset 0 2px 0 var(--safe); }}
  .state-h {{ font-family:var(--mono); font-size:.86rem; font-weight:600; margin:0 0 8px;
              letter-spacing:.02em; }}
  .danger-state .state-h {{ color:var(--danger); }}
  .safe-state .state-h {{ color:var(--safe); }}
  .svg-wrap {{ flex:1; }}
  .svg-wrap svg {{ display:block; }}
  .state-cap {{ color:var(--muted); font-size:.8rem; line-height:1.45; margin:10px 2px 0; }}

  .legend {{ display:flex; flex-wrap:wrap; gap:14px; margin:14px 2px 8px; font-size:.76rem; color:var(--muted); }}
  .dot {{ display:inline-block; width:9px; height:9px; border-radius:50%; margin-right:6px; vertical-align:middle; }}
  .dot.danger {{ background:var(--danger); }} .dot.safe {{ background:var(--safe); }} .dot.muted {{ background:var(--soft); }}

  .below-fold {{ margin-top:30px; padding-top:18px; border-top:1px solid var(--line); }}
  .ref-h {{ font-family:var(--mono); font-size:.95rem; margin:0 0 3px; }}
  .ref-sub {{ color:var(--muted); font-size:.78rem; margin:0 0 12px; }}
  .ref-sub code {{ font-family:var(--mono); color:var(--text); }}
  table {{ width:100%; border-collapse:collapse; font-size:.82rem; overflow:hidden; border-radius:14px;
           border:1px solid var(--line); background:var(--panel); }}
  th, td {{ text-align:left; padding:9px 11px; border-bottom:1px solid var(--line); vertical-align:top; }}
  th {{ font-family:var(--mono); color:var(--muted); font-weight:600; font-size:.72rem;
        letter-spacing:.06em; text-transform:uppercase; }}
  td.mono {{ font-family:var(--mono); font-size:.76rem; }}
  tr:last-child td {{ border-bottom:none; }}
  .badge {{ font-family:var(--mono); font-size:.66rem; padding:2px 8px; border-radius:999px; text-transform:uppercase; letter-spacing:.04em; }}
  .badge.critical {{ background:rgba(229,83,75,.16); color:var(--danger); }}
  .badge.high {{ background:rgba(229,83,75,.12); color:var(--danger); }}
  .badge.medium {{ background:rgba(211,154,54,.16); color:#d39a36; }}
  .badge.low {{ background:rgba(107,114,128,.22); color:var(--muted); }}
  .rubric {{ color:var(--muted); font-size:.72rem; margin-top:12px; line-height:1.5; }}

  @media (max-width:720px) {{
    .states {{ flex-direction:column; }}
    .gauge .before, .gauge .after {{ font-size:1.7rem; }}
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
    <div class="gauge">{score_block}</div>
    <div class="meta">
      <span class="pill">risk score · heuristic · lower is safer</span>
      {score_note}
    </div>
    <div class="counts">Critical <b>{crit}</b> &nbsp; High <b>{high}</b> &nbsp; Medium <b>{med}</b> &nbsp; Low <b>{low}</b></div>
  </div>

  {body}
  <div class="legend">{legend}</div>

  {table}
  <p class="rubric">Score: {rubric}</p>
</div>
<script>var AEGIS_SCORE = JSON.parse("{data_json}".replace(/&quot;/g,'"'));</script>
</body>
</html>
"""
