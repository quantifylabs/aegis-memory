"""Render docs/security/benchmark.md from results/results.json.

Keeps the human-readable writeup consistent with the machine-readable results:
narrative is hand-written here; every table is generated from the data. Run
after ``run_benchmark.py``::

    python benchmarks/injection/render_report.py
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
RESULTS = HERE / "results" / "results.json"
ERROR_MD = HERE / "results" / "error_analysis.md"
OUT = REPO_ROOT / "docs" / "security" / "benchmark.md"

# Display order + friendly labels.
SYSTEM_ORDER = [
    "no_protection", "naive_regex", "protectai_deberta", "llm_guard",
    "llm_judge_openai", "llm_judge_anthropic",
    "aegis_stages_1_3", "aegis_stages_1_4_openai", "aegis_stages_1_4_anthropic",
]
DATASET_ORDER = ["deepset", "injecagent", "benign_public", "benign_synth"]
MALICIOUS = {"deepset", "injecagent"}


def f3(v) -> str:
    return "—" if v is None else f"{v:.3f}"


def with_ci(v, ci) -> str:
    if v is None:
        return "—"
    if not ci:
        return f"{v:.3f}"
    return f"{v:.3f} [{ci[0]:.2f}–{ci[1]:.2f}]"


def lat(v) -> str:
    if v is None:
        return "—"
    if v < 1:
        return f"{v*1000:.0f} µs"
    return f"{v:.1f} ms"


def main() -> int:
    data = json.loads(RESULTS.read_text(encoding="utf-8"))
    meta, dsmeta, sysmeta = data["meta"], data["datasets"], data["systems"]
    results, ablation = data["results"], data["ablation"]

    datasets = [d for d in DATASET_ORDER if d in dsmeta]
    systems = [s for s in SYSTEM_ORDER if s in sysmeta]

    L: list[str] = []
    L.append("# Aegis content-security pipeline — injection-detection benchmark\n")
    L.append(f"_Generated from `benchmarks/injection/results/results.json` · "
             f"run {meta['timestamp']} · seed {meta['seed']} · "
             f"bootstrap n={meta['n_bootstrap']}_\n")
    if meta.get("limit"):
        L.append(f"> ⚠️ This report was generated with `--limit {meta['limit']}` "
                 "(smoke mode), not the full corpus.\n")

    # ---- Threat model ----
    L.append("## Threat model\n")
    L.append(
        "Aegis's content-security pipeline detects **prompt injection / memory "
        "poisoning in content being written to memory** — text that, once stored "
        "and later retrieved, could manipulate an agent. This is the scope measured "
        "here. It is **not** an LLM-jailbreak defense and is not evaluated as one. "
        "Every system is scored on **both** malicious and benign corpora, so the "
        "false-positive rate (FPR) is reported next to recall everywhere — a "
        "detector that flags everything scores 100% recall and is useless.\n")

    # ---- Methodology ----
    L.append("## Methodology\n")
    L.append(
        "- **Systems** are wrapped as `predict(text) -> bool` (True = flagged). "
        "Aegis systems call the real `ContentSecurityScanner` from "
        "`server/content_security.py`; detection logic is never reimplemented.\n"
        "- **`aegis_stages_1_3`** runs the deterministic Stages 1–3 (`scan`). "
        "**`aegis_stages_1_4_*`** add the Stage-4 LLM classifier (`scan_async`), "
        "forced on every item via `trust_level=\"untrusted\"` so the ablation can "
        "measure Stage 4's standalone contribution. *Production gates Stage 4 "
        "conditionally — this is a measurement choice, not production behavior.*\n"
        "- **Metrics:** confusion matrix → precision, recall, F1, FPR, accuracy, "
        "with bootstrapped 95% CIs (resampling cases, "
        f"n={meta['n_bootstrap']}, seed={meta['seed']}). Median per-item latency too.\n"
        "- A metric is shown as `—` when undefined (e.g. FPR on a malicious-only "
        "dataset, precision on a benign-only dataset).\n")
    lv = meta.get("lib_versions", {})
    L.append(f"- **Environment:** Python {meta['python']}, {meta['platform']}. "
             f"Models: OpenAI `{meta['models']['openai']}`, Anthropic "
             f"`{meta['models']['anthropic']}`. "
             f"Key libs: transformers `{lv.get('transformers','?')}`, "
             f"torch `{lv.get('torch','?')}`, datasets `{lv.get('datasets','?')}`, "
             f"llm_guard `{lv.get('llm_guard','?')}`.\n")

    # ---- Datasets ----
    L.append("## Datasets\n")
    L.append("| Dataset | Kind | N | Injection | Benign | Revision | Status |")
    L.append("|---|---|--:|--:|--:|---|---|")
    for name in datasets:
        d = dsmeta[name]
        rev = (d["revision"] or "")[:12]
        L.append(f"| `{name}` | {d['kind']} | {d['n']} | {d['n_pos']} | "
                 f"{d['n_neg']} | `{rev}` | {d['status']} |")
    L.append("")
    for name in datasets:
        d = dsmeta[name]
        if d.get("notes"):
            L.append(f"- **{name}** — {d['notes']} _(source: {d['source']})_")
        if d.get("status") != "ok" and d.get("error"):
            L.append(f"- **{name}** — not run: {d['error']}")
    L.append("")

    # ---- Systems not run ----
    skipped = [(s, sysmeta[s].get("reason", "")) for s in systems
               if sysmeta[s].get("status") != "ok"]
    if skipped:
        L.append("### Systems not run\n")
        for s, reason in skipped:
            L.append(f"- `{s}` — {reason}")
        L.append("")

    # ---- Headline results, per dataset ----
    L.append("## Headline results\n")
    L.append("Recall and FPR shown with 95% CI. Full CIs for precision/F1 are in "
             "`results.json`.\n")
    for name in datasets:
        d = dsmeta[name]
        if d["status"] != "ok":
            continue
        L.append(f"### `{name}` ({d['kind']}, N={d['n']})\n")
        L.append("| System | Precision | Recall [95% CI] | F1 | FPR [95% CI] | Acc | Median latency |")
        L.append("|---|--:|--:|--:|--:|--:|--:|")
        for s in systems:
            r = results.get(s, {}).get(name)
            if not r or r.get("status") == "not_run":
                continue
            ci = r.get("ci95", {})
            L.append(
                f"| `{s}` | {f3(r['precision'])} | "
                f"{with_ci(r['recall'], ci.get('recall'))} | {f3(r['f1'])} | "
                f"{with_ci(r['fpr'], ci.get('fpr'))} | {f3(r['accuracy'])} | "
                f"{lat(r['median_latency_ms'])} |")
        L.append("")

    # ---- Ablation ----
    L.append("## Aegis stage ablation\n")
    L.append(
        "Cumulative contribution as each stage is added (Stage 1 → +2 → +3 → +4). "
        "This is the central research contribution: it quantifies whether the "
        "LLM-backed Stage 4 earns its latency/cost over the free deterministic "
        "core (Stages 1–3).\n")
    # Compute Stage 2's marginal flag count per malicious dataset from a
    # representative aegis system, so the narrative matches the tables on re-runs.
    def _s2_counts() -> dict[str, int]:
        for sid in ("aegis_stages_1_3", "aegis_stages_1_4_openai",
                    "aegis_stages_1_4_anthropic"):
            if sid in ablation:
                out = {}
                for name, blk in ablation[sid].items():
                    mc = blk["marginal_counts"]
                    out[name] = mc.get("2", mc.get(2, 0))
                return out
        return {}

    s2 = _s2_counts()
    direct = ", ".join(f"`{n}` ({s2.get(n,0)} flags)"
                       for n in datasets if dsmeta[n]["kind"] == "malicious_direct")
    indirect_bits = [(n, s2.get(n, 0), dsmeta[n]["n"])
                     for n in datasets if dsmeta[n]["kind"] == "malicious_indirect"]
    L.append(
        "**Stage 2's contribution to injection recall is category-dependent — an "
        "honest, important nuance.** Stage 2 targets PII/credentials, *not* "
        "injection. On **direct injection** it behaves exactly as designed and adds "
        f"~0 recall — it flags essentially nothing there ({direct or 'n/a'}), because "
        "injection text rarely contains PII.")
    if indirect_bits:
        n, cnt, tot = indirect_bits[0]
        L.append(
            f"On **indirect injection** (`{n}`), however, Stage 2 flags **{cnt}/{tot}** "
            "payloads and accounts for most of the deterministic core's recall there. "
            "That is *not* injection detection working: it is Stage 2 firing on the "
            "PII/credentials embedded in the data-exfiltration payloads (health "
            "records, account numbers, emails). We report this rather than hide it — "
            "it shows (a) Stage 2 is orthogonal to injection detection for direct "
            "attacks, as claimed, and (b) a multi-category pipeline can still catch "
            "data-stealing indirect payloads via a *different* stage than a pure "
            "injection detector would. For the genuine injection-detection signal, "
            "read the **Stage 3 → Stage 4** deltas.")
    L.append(
        "This is what distinguishes Aegis (multi-category content security) from "
        "single-purpose injection detectors — and the ablation is what makes the "
        "case empirically.\n")
    stage_label = {"stage_1": "Stage 1", "stage_1_2": "+ Stage 2",
                   "stage_1_2_3": "+ Stage 3", "stage_1_2_3_4": "+ Stage 4"}
    for sysid, per_ds in ablation.items():
        L.append(f"### `{sysid}`\n")
        for name in datasets:
            block = per_ds.get(name)
            if not block:
                continue
            d = dsmeta[name]
            L.append(f"**`{name}`** ({d['kind']}, N={d['n']})\n")
            L.append("| Stages | Recall | FPR | Precision | F1 |")
            L.append("|---|--:|--:|--:|--:|")
            for row in block["rows"]:
                L.append(f"| {stage_label.get(row['stages'], row['stages'])} | "
                         f"{f3(row['recall'])} | {f3(row['fpr'])} | "
                         f"{f3(row['precision'])} | {f3(row['f1'])} |")
            mc = block["marginal_counts"]
            L.append("")
            L.append(f"_Items flagged per stage (any flag): S1={mc.get('1',mc.get(1,0))}, "
                     f"S2={mc.get('2',mc.get(2,0))}, S3={mc.get('3',mc.get(3,0))}, "
                     f"S4={mc.get('4',mc.get(4,0))}._\n")

    # ---- Latency ----
    L.append("## Latency comparison\n")
    L.append("Median per-item latency (lower is better). Deterministic stages 1–3 "
             "are orders of magnitude faster than LLM-based detectors.\n")
    L.append("| System | " + " | ".join(f"`{n}`" for n in datasets) + " |")
    L.append("|---|" + "|".join("--:" for _ in datasets) + "|")
    for s in systems:
        if sysmeta[s].get("status") != "ok":
            continue
        cells = []
        for name in datasets:
            r = results.get(s, {}).get(name)
            cells.append(lat(r["median_latency_ms"]) if r and r.get("median_latency_ms") is not None else "—")
        L.append(f"| `{s}` | " + " | ".join(cells) + " |")
    L.append("")
    L.append("> Note: API-system latencies are measured on live calls during the "
             "first run; cached re-runs are not representative of live latency.\n")

    # ---- Error analysis pointer + headline counts ----
    L.append("## Error analysis\n")
    L.append("Full dump (categorized false negatives + sampled false positives) in "
             "[`benchmarks/injection/results/error_analysis.md`]"
             "(../../benchmarks/injection/results/error_analysis.md).\n")
    for s in ("aegis_stages_1_3", "aegis_stages_1_4_openai", "aegis_stages_1_4_anthropic"):
        if s not in results:
            continue
        tot_fn = sum(r["confusion"]["fn"] for n, r in results[s].items()
                     if isinstance(r, dict) and "confusion" in r and n in MALICIOUS)
        tot_fp = sum(r["confusion"]["fp"] for n, r in results[s].items()
                     if isinstance(r, dict) and "confusion" in r and n not in MALICIOUS)
        fp_word = "item" if tot_fp == 1 else "items"
        L.append(f"- `{s}`: {tot_fn} missed injections (FN) across malicious sets; "
                 f"{tot_fp} benign {fp_word} over-flagged (FP) across benign sets.")
    L.append("")

    # ---- Limitations ----
    L.append("## Limitations\n")
    L.append(
        "- **Rule-based stages may overfit known patterns.** Stages 1–3 are "
        "deterministic regex/heuristics; novel phrasings and encoding tricks "
        "(base64, homoglyphs, indirection) can evade them — see the error analysis.\n"
        "- **Dataset coverage.** `deepset` is direct injection; `InjecAgent` is a "
        "250-case indirect sample; benign corpora are public text + synthetic "
        "memory entries. Real-world memory content may differ. CIs quantify "
        "sampling uncertainty but not distribution shift.\n"
        "- **Forced Stage 4.** Stage 4 is forced on every item for measurement; in "
        "production it is gated, so production latency/cost differ from the "
        "`aegis_stages_1_4_*` rows here.\n"
        "- **Stage-4 fenced-JSON bug — found here and fixed.** This benchmark "
        "surfaced a real production bug: `InjectionClassifier` did a bare "
        "`json.loads()` on the adapter's output, so models that wrap JSON in "
        "markdown fences (observed with Claude Haiku 4.5: ```` ```json … ``` ````) "
        "made the parse fail and the classifier silently fell back to regex-only — "
        "Stage 4 *did nothing* for such models (OpenAI avoided it via "
        "`response_format=json_object`). Fixed in `server/content_security.py` "
        "(`_parse_classifier_json` strips fences and falls back to the outermost "
        "`{…}`), with a regression test in `tests/test_content_security.py`. The "
        "`aegis_stages_1_4_anthropic` rows reflect Stage 4 actually running.\n"
        "- **API latencies.** Anthropic-system latencies are taken from the live run; "
        "metric values for the Anthropic systems come from a cache-served re-run "
        "(same responses). Latencies are representative of live calls (including "
        "rate-limit backoff on this account's tier).\n"
        "- **Self-assessment, not third-party audit.** This benchmark is authored "
        "by the Aegis maintainers. Results are reproducible (pinned revisions, "
        "seeds, cached LLM responses) but have not been independently audited.\n"
        "- **LLM nondeterminism.** Stage 4 and `llm_judge_*` depend on hosted "
        "models that may change; responses are cached for reproducibility of *this* "
        "run, keyed by prompt hash.\n")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(L), encoding="utf-8")
    print(f"[write] {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
