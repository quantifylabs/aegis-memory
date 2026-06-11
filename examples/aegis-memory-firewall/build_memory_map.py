"""Render ``agent_memory_map.html`` from TWO real ``aegis inspect`` runs.

* "before" = inspect the unscreened ``agent/`` package (five untrusted writes, critical).
* "after"  = inspect the screened ``agent_screened/`` package (the same writes, guarded).

Both scores come from the real ``compute_score`` — nothing is hardcoded. The map shows the
unscreened channels (the threat) with the real before→after governance transition in the
header. Offline and deterministic.

Run:  python build_memory_map.py
"""

from __future__ import annotations

from pathlib import Path

from aegis_memory.inspect import htmlmap
from aegis_memory.inspect.report import run_inspection

HERE = Path(__file__).resolve().parent


def main() -> Path:
    before = run_inspection(HERE / "agent", write=False)
    after = run_inspection(HERE / "agent_screened", write=False)
    before_score = before.score["score"]
    after_score = after.score["score"]

    html = htmlmap.render_html(
        before.findings,
        before.score,
        before_score=before_score,
        after_score=after_score,
        project_name="aegis-memory-firewall",
    )
    out = HERE / "agent_memory_map.html"
    out.write_text(html, encoding="utf-8")

    n_flows = sum(1 for f in before.findings if f.category.endswith("_to_memory"))
    print(f"unscreened (before): {before_score}/100  -  {n_flows} untrusted source->memory flows")
    print(f"screened   (after):  {after_score}/100  -  same writes, guarded by real scan()")
    print(f"wrote {out}  (both scores are real computed values, not the 86/29 fallbacks)")
    return out


if __name__ == "__main__":
    main()
