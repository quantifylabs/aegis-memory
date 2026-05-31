"""Orchestrator for the Aegis injection-detection benchmark.

Runs every available system over every available dataset, computes full
confusion-matrix metrics + bootstrap CIs + the Aegis stage ablation, and writes
``results/results.json`` and ``results/error_analysis.md``.

Usage::

    python benchmarks/injection/run_benchmark.py                 # full run
    python benchmarks/injection/run_benchmark.py --limit 20      # smoke
    python benchmarks/injection/run_benchmark.py --systems aegis_stages_1_3,naive_regex
    python benchmarks/injection/run_benchmark.py --datasets deepset,benign_synth

Keys are read from the environment / ``aegis-memory-main/.env`` only. Missing
keys or deps cause the affected system to be reported ``not_run`` (the run
continues). LLM responses are cached under ``cache/`` so re-runs never re-bill.
"""

from __future__ import annotations

# Allow `python benchmarks/injection/run_benchmark.py` (no package context) as
# well as `python -m benchmarks.injection.run_benchmark`.
if __package__ in (None, ""):
    import pathlib as _pl
    import sys as _sys

    # Direct execution prepends this script's dir to sys.path, which would
    # shadow the PyPI `datasets` library with our local datasets.py (and break
    # transformers/huggingface_hub internals). Remove it; import via package.
    _here = _pl.Path(__file__).resolve().parent
    _sys.path[:] = [p for p in _sys.path if not (p and _pl.Path(p).resolve() == _here)]
    _sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[2]))
    __package__ = "benchmarks.injection"

import argparse
import json
import platform
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from . import _paths  # noqa: F401 — sys.path bootstrap
from . import datasets as ds_mod
from . import metrics as metrics_mod
from . import systems as sys_mod

HERE = Path(__file__).resolve().parent
RESULTS_DIR = HERE / "results"
CACHE_DIR = HERE / "cache"


def _lib_versions() -> dict[str, str]:
    """Record actual installed versions of key libs for reproducibility."""
    import importlib

    out: dict[str, str] = {}
    for mod in ("transformers", "torch", "datasets", "openai", "anthropic", "llm_guard"):
        try:
            out[mod] = getattr(importlib.import_module(mod), "__version__", "unknown")
        except Exception:  # noqa: BLE001
            out[mod] = "not_installed"
    return out


def _load_dotenv() -> str:
    """Load aegis-memory-main/.env into os.environ. Returns a status string."""
    env_path = _paths.REPO_ROOT / ".env"
    try:
        from dotenv import load_dotenv

        if env_path.exists():
            load_dotenv(env_path)
            return f"loaded {env_path}"
        return f"no .env at {env_path}"
    except Exception as e:  # noqa: BLE001
        return f"python-dotenv unavailable ({e}); using process env only"


# --------------------------------------------------------------------------
# Error-analysis categorisation
# --------------------------------------------------------------------------
_NON_ASCII = re.compile(r"[^\x00-\x7f]")
_B64ISH = re.compile(r"[A-Za-z0-9+/]{40,}={0,2}")
_HEXISH = re.compile(r"(?:\\x[0-9a-fA-F]{2}){4,}|(?:[0-9a-fA-F]{2}\s+){8,}")


def categorize_fn(text: str, dataset_kind: str) -> str:
    if dataset_kind == "malicious_indirect":
        return "indirect_injection"
    if _B64ISH.search(text) or _HEXISH.search(text):
        return "encoding_or_obfuscation"
    non_ascii = len(_NON_ASCII.findall(text))
    if non_ascii > max(5, 0.15 * len(text)):
        return "non_english_or_unicode"
    if len(text) < 40:
        return "terse_phrasing"
    return "novel_phrasing"


# --------------------------------------------------------------------------
# Run one (system, dataset)
# --------------------------------------------------------------------------
def run_system_on_dataset(system, dataset):
    """Returns (metrics_dict, y_true, stage_records|None, fn_items, fp_items, n_err)."""
    y_true: list[bool] = []
    y_pred: list[bool] = []
    latencies: list[float] = []
    stage_records: list[dict[int, bool]] = []
    fn_items: list[str] = []
    fp_items: list[str] = []
    n_err = 0
    has_stages = False

    texts = [t for t, _ in dataset.items]
    labels = [y for _, y in dataset.items]
    try:
        batch = system.evaluate_batch(texts)
    except Exception:  # noqa: BLE001 — whole-system failure (e.g. API down)
        return None, [], None, fn_items, fp_items, len(texts)

    for (pred, dt_ms), text, label in zip(batch, texts, labels):
        if pred is None:  # per-item failure surfaced by the system
            n_err += 1
            continue
        y_true.append(label)
        y_pred.append(pred.flagged)
        latencies.append(dt_ms)
        if pred.stages is not None:
            has_stages = True
            stage_records.append(pred.stages)
        else:
            stage_records.append({})
        if label and not pred.flagged:
            fn_items.append(text)
        elif (not label) and pred.flagged:
            fp_items.append(text)

    if not y_true:  # every item errored
        return None, [], None, fn_items, fp_items, n_err

    result = metrics_mod.evaluate_run(y_true, y_pred, latencies)
    result["n_errors"] = n_err
    return result, y_true, (stage_records if has_stages else None), fn_items, fp_items, n_err


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Aegis injection-detection benchmark")
    ap.add_argument("--limit", type=int, default=None,
                    help="cap items per dataset (smoke mode)")
    ap.add_argument("--systems", type=str, default=None,
                    help="comma-separated system ids to include")
    ap.add_argument("--datasets", type=str, default=None,
                    help="comma-separated dataset names to include")
    ap.add_argument("--out", type=str, default=str(RESULTS_DIR))
    args = ap.parse_args(argv)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    env_status = _load_dotenv()

    cache = sys_mod.ResponseCache(CACHE_DIR)
    all_systems = sys_mod.build_systems(cache)
    if args.systems:
        wanted = {s.strip() for s in args.systems.split(",")}
        all_systems = [s for s in all_systems if s.id in wanted]

    datasets = ds_mod.load_all(limit=args.limit)
    if args.datasets:
        wanted_ds = {s.strip() for s in args.datasets.split(",")}
        datasets = {k: v for k, v in datasets.items() if k in wanted_ds}

    print(f"[env] {env_status}")
    ds_summary = ", ".join(
        f"{n}:{d.n if d.status == 'ok' else d.status}" for n, d in datasets.items()
    )
    print(f"[datasets] {ds_summary}")

    # ---- dataset metadata ----
    ds_meta = {}
    for name, d in datasets.items():
        ds_meta[name] = {
            "kind": d.kind, "n": d.n, "n_pos": d.n_pos, "n_neg": d.n_neg,
            "revision": d.revision, "source": d.source, "notes": d.notes,
            "status": d.status, "error": d.error,
        }

    sys_meta: dict[str, dict] = {}
    results: dict[str, dict] = {}
    ablation: dict[str, dict] = {}
    error_bank: dict[str, dict] = {}  # aegis system -> {fn:[...], fp:[...]}

    active_ds = {n: d for n, d in datasets.items() if d.status == "ok"}

    for system in all_systems:
        ok, reason = system.available()
        if not ok:
            sys_meta[system.id] = {"status": "not_run", "reason": reason}
            print(f"[skip] {system.id}: {reason}")
            continue
        try:
            system.warmup()
        except Exception as e:  # noqa: BLE001
            sys_meta[system.id] = {"status": "not_run", "reason": f"warmup failed: {e}"}
            print(f"[skip] {system.id}: warmup failed: {e}")
            continue

        sys_meta[system.id] = {"status": "ok", "reason": ""}
        results[system.id] = {}
        print(f"[run ] {system.id}")
        for name, d in active_ds.items():
            t0 = time.perf_counter()
            res, y_true, stage_records, fn_items, fp_items, n_err = run_system_on_dataset(system, d)
            took = time.perf_counter() - t0
            if res is None:
                results[system.id][name] = {"status": "not_run",
                                            "reason": f"all {n_err} items errored"}
                print(f"        {name:<14} ERRORED ({n_err})")
                continue
            results[system.id][name] = res
            r = (f"P={_fmt(res['precision'])} R={_fmt(res['recall'])} "
                 f"F1={_fmt(res['f1'])} FPR={_fmt(res['fpr'])}")
            lat = res["median_latency_ms"]
            lat_s = "n/a" if lat is None else f"{lat:.3f}ms"
            print(f"        {name:<14} n={res['n']:<5} {r}  lat={lat_s} ({took:.1f}s)")

            if stage_records is not None:
                ablation.setdefault(system.id, {})[name] = {
                    "rows": metrics_mod.stage_ablation(y_true, stage_records),
                    "marginal_counts": metrics_mod.marginal_stage_contribution(stage_records),
                }
                bank = error_bank.setdefault(system.id, {"fn": [], "fp": []})
                bank["fn"].extend({"text": t, "dataset": name, "kind": d.kind,
                                   "category": categorize_fn(t, d.kind)} for t in fn_items)
                bank["fp"].extend({"text": t, "dataset": name} for t in fp_items)

        cache.flush()

    cache.flush()

    # ---- assemble results.json ----
    payload = {
        "meta": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "seed": ds_mod.SEED,
            "n_bootstrap": metrics_mod.N_BOOTSTRAP,
            "limit": args.limit,
            "python": platform.python_version(),
            "platform": platform.platform(),
            "models": {"openai": sys_mod.OPENAI_MODEL, "anthropic": sys_mod.ANTHROPIC_MODEL},
            "lib_versions": _lib_versions(),
            "env": env_status,
            "stage4_note": ("aegis_stages_1_4 forces Stage 4 via trust_level='untrusted' "
                            "so the ablation measures its standalone contribution; "
                            "production gates Stage 4 conditionally."),
        },
        "datasets": ds_meta,
        "systems": sys_meta,
        "results": results,
        "ablation": ablation,
        "cache_stats": {"hits": cache.hits, "misses": cache.misses},
    }
    out_json = out_dir / "results.json"
    out_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\n[write] {out_json}")

    write_error_analysis(out_dir / "error_analysis.md", payload, error_bank)
    print(f"[write] {out_dir / 'error_analysis.md'}")
    print(f"[cache] hits={cache.hits} misses={cache.misses}")
    return 0


# --------------------------------------------------------------------------
# Error analysis report
# --------------------------------------------------------------------------
def _fmt(v) -> str:
    return "n/a" if v is None else f"{v:.3f}"


def write_error_analysis(path: Path, payload: dict, error_bank: dict) -> None:
    lines: list[str] = []
    lines.append("# Error analysis — Aegis injection detection\n")
    lines.append(f"_Generated {payload['meta']['timestamp']} · seed "
                 f"{payload['meta']['seed']} · n_bootstrap {payload['meta']['n_bootstrap']}_\n")
    lines.append("Honest error analysis of where Aegis misses (false negatives) and "
                 "where it over-flags benign content (false positives). "
                 "Categories are heuristic.\n")

    for sysid, bank in error_bank.items():
        fns, fps = bank["fn"], bank["fp"]
        lines.append(f"\n## {sysid}\n")
        lines.append(f"- False negatives (missed injections): **{len(fns)}**")
        lines.append(f"- False positives (benign flagged): **{len(fps)}**\n")

        # FN breakdown by category
        cats: dict[str, int] = {}
        for item in fns:
            cats[item["category"]] = cats.get(item["category"], 0) + 1
        if cats:
            lines.append("### False-negative categories\n")
            lines.append("| Category | Count |")
            lines.append("|---|---|")
            for cat, n in sorted(cats.items(), key=lambda x: -x[1]):
                lines.append(f"| {cat} | {n} |")
            lines.append("")
            lines.append("### Sample missed injections (up to 15)\n")
            for item in fns[:15]:
                snippet = item["text"].replace("\n", " ").strip()[:200]
                lines.append(f"- [{item['dataset']} · {item['category']}] {snippet}")
            lines.append("")

        if fps:
            lines.append("### Sample false positives (benign flagged, up to 15)\n")
            for item in fps[:15]:
                snippet = item["text"].replace("\n", " ").strip()[:200]
                lines.append(f"- [{item['dataset']}] {snippet}")
            lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
