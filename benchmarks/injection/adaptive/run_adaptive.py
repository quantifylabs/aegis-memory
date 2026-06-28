"""Orchestrator for the Phase 2 adaptive attack harness.

Generates adaptive corpora for the three attacks x both tiers (honouring the
frozen pre-registered config), evaluates every corpus against the requested
systems via the EXISTING ``run_benchmark.run_system_on_dataset`` path (so
``evasion = 1 - recall`` comes from the same metrics + bootstrap CIs as the static
benchmark), and writes a SEPARATE ``adaptive_results.json`` + provenance-rich
corpora. It NEVER writes the static ``results/results.json``.

Usage::

    # smoke first (pennies): tiny N + budget, cheap eval systems only
    python -m benchmarks.injection.adaptive.run_adaptive --limit 5 \
        --systems no_protection,naive_regex,llm_judge_openai,aegis_stages_1_3,aegis_stages_1_4_openai

    # real run (frozen constants; full billed sweep — separate approval):
    python -m benchmarks.injection.adaptive.run_adaptive

Tier semantics:
  - ``white_box`` — the attacker optimizes against the actual target oracle
    (Attack 1/3 use Stage-3 feedback; Attack 2 queries the paid Stage-4 target).
  - ``grey_box`` — the attacker has no target feedback: Attack 1/3 mutate/split
    blindly; Attack 2 searches a free Stage-3 surrogate and the found samples are
    *transferred* to Stage 4. Evasion is then measured by the harness.
"""

from __future__ import annotations

# Allow direct execution as well as ``python -m`` (mirror run_benchmark's bootstrap).
if __package__ in (None, ""):
    import pathlib as _pl
    import sys as _sys

    _here = _pl.Path(__file__).resolve().parent
    _sys.path[:] = [p for p in _sys.path if not (p and _pl.Path(p).resolve() == _here)]
    _sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[3]))
    __package__ = "benchmarks.injection.adaptive"

import argparse
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

from .. import metrics as metrics_mod
from .. import run_benchmark as rb_mod
from .. import systems as sys_mod
from . import attack_composition as a3
from . import attack_oracle as a2
from . import attack_rule_evasion as a1
from . import config
from .intent import IntentJudge
from .mutate import Mutator
from .seeds import pick_seeds

HERE = Path(__file__).resolve().parent
RESULTS_DIR = HERE / "results"
CORPORA_DIR = RESULTS_DIR / "corpora"
CACHE_DIR = rb_mod.CACHE_DIR  # share the static benchmark's cache so re-runs hit it


# --------------------------------------------------------------------------
# Evaluation — reuse the canonical run_system_on_dataset / metrics path
# --------------------------------------------------------------------------
def evaluate_corpus(corpus, systems: list) -> dict:
    """Evaluate ``corpus`` against each (warmed) system; ``evasion = 1 - recall``.

    Reuses ``run_benchmark.run_system_on_dataset`` verbatim, so per-item failures
    are excluded from BOTH the metric and the denominator (an errored Stage-4 query
    neither inflates nor deflates evasion) and the recall CI comes from the shared
    ``bootstrap_cis`` (n=1000, seed=42). Returns ``{system_id: {...}}``.
    """
    out: dict[str, dict] = {}
    if corpus.n == 0:
        return {s.id: {"status": "empty_corpus"} for s in systems}
    for system in systems:
        res, y_true, _stages, _fn, _fp, n_err = rb_mod.run_system_on_dataset(system, corpus)
        if res is None:
            out[system.id] = {"status": "not_run", "reason": f"all {n_err} items errored"}
            continue
        recall = res["recall"]
        evasion = None if recall is None else 1.0 - recall
        rec_ci = (res.get("ci95") or {}).get("recall")
        evasion_ci = None if rec_ci is None else [1.0 - rec_ci[1], 1.0 - rec_ci[0]]
        out[system.id] = {
            "status": "ok", "n": res["n"], "n_errors": res["n_errors"],
            "recall": recall, "evasion_rate": evasion, "evasion_ci95": evasion_ci,
        }
    return out


# --------------------------------------------------------------------------
# Per-attack runners (each returns a JSON-ready block + the corpus + samples)
# --------------------------------------------------------------------------
def _intent_counts(samples, evaded_attr="evaded") -> dict:
    """Intent-exclusion bookkeeping reported per attack/tier (never silent-dropped)."""
    evaded = [s for s in samples if getattr(s, evaded_attr)]
    preserved = [s for s in evaded if s.intent_preserved]
    return {
        "n_samples": len(samples),
        "n_evaded_target": len(evaded),
        "n_intent_preserved": len(preserved),
        "n_excluded_intent_lost": len(evaded) - len(preserved),
    }


def run_attack1(tier, stage3, mutator, judge, eval_systems, n) -> tuple[dict, object, list]:
    seeds = pick_seeds(n, stage3, max_probe=None)  # Stage 3 is free: scan freely
    samples = a1.run_attack(seeds, stage3, mutator, judge, tier,
                            blind=(tier == "grey_box"))
    corpus = a1.to_corpus(samples, tier)
    per_system = evaluate_corpus(corpus, eval_systems)
    # Hand-off: every corpus item evaded Stage 3 by construction, so a Stage-4
    # system's RECALL on this corpus IS the fraction of Stage-3 evaders it catches.
    handoff = {}
    for s4 in config.STAGE4_SYSTEMS:
        row = per_system.get(s4, {})
        handoff[s4] = {
            "status": row.get("status", "not_run"),
            "stage4_caught_fraction": row.get("recall"),
            "stage4_evasion_rate": row.get("evasion_rate"),
            "n_evaluated": row.get("n"),
            "n_errors": row.get("n_errors"),
        }
    block = {
        "tier": tier, "n_seeds": len(seeds),
        "intent": _intent_counts(samples),
        "stage3_evader_corpus_n": corpus.n,
        "per_system_evasion": per_system,
        "handoff": handoff,
    }
    return block, corpus, samples


def run_attack2(tier, stage3, stage4_targets, mutator, judge, eval_systems, n, budget):
    """Attack 2 across the Stage-4 targets. Returns a list of per-target blocks."""
    blocks = []
    corpora = []
    samples_by_key = {}
    for target in stage4_targets:
        if tier == "white_box":
            search_target, max_probe = target, max(n * 4, n + 5)  # paid: cap seed probing
        else:  # grey_box: search the FREE Stage-3 surrogate, transfer to Stage 4
            search_target, max_probe = stage3, None
        seeds = pick_seeds(n, search_target, max_probe=max_probe)
        samples = a2.run_attack(seeds, search_target, mutator, judge, tier, budget=budget)
        corpus = a2.to_corpus(samples, tier, target.id)
        per_system = evaluate_corpus(corpus, eval_systems)  # transfer evasion across systems
        block = {
            "tier": tier, "target": target.id,
            "search_oracle": search_target.id,
            "n_seeds": len(seeds), "budget": budget,
            "intent": _intent_counts(samples),
            "queries_to_evade": [s.queries_to_evade for s in samples],
            "budget_curve": a2.budget_curve(samples),
            "evasion_corpus_n": corpus.n,
            "per_system_transfer_evasion": per_system,
        }
        blocks.append(block)
        corpora.append(corpus)
        samples_by_key[f"{tier}:{target.id}"] = samples
    return blocks, corpora, samples_by_key


def run_attack3(tier, stage3, judge, eval_systems, n) -> tuple[dict, object, list]:
    seeds = pick_seeds(n, stage3, max_probe=None)
    cases = a3.run_attack(seeds, stage3, judge, tier, blind=(tier == "grey_box"), n=n)
    corpus = a3.to_corpus(cases, tier)
    per_system = evaluate_corpus(corpus, eval_systems)
    block = {
        "tier": tier, "n_seeds": len(seeds),
        "summary": a3.summarize(cases),
        "assembled_corpus_n": corpus.n,
        "per_system_assembled_evasion": per_system,
        "note": "ILLUSTRATIVE / smaller-by-design (v1 frontier study).",
    }
    return block, corpus, cases


# --------------------------------------------------------------------------
# Output helpers
# --------------------------------------------------------------------------
def _write_corpus(corpus, samples) -> None:
    CORPORA_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "name": corpus.name, "kind": corpus.kind, "n": corpus.n,
        "source": corpus.source, "notes": corpus.notes,
        "items": [t for t, _ in corpus.items],
        "samples": [s.to_dict() for s in samples],
    }
    (CORPORA_DIR / f"{corpus.name}.json").write_text(json.dumps(payload, indent=2),
                                                     encoding="utf-8")


def _pct(x) -> str:
    return "n/a" if x is None else f"{100 * x:.1f}%"


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Aegis Phase 2 adaptive attack harness")
    ap.add_argument("--limit", type=int, default=None,
                    help="smoke override: N per attack/tier AND a smaller oracle budget")
    ap.add_argument("--systems", type=str, default=None,
                    help="comma-separated system ids to EVALUATE against (default: all 10)")
    ap.add_argument("--out", type=str, default=str(RESULTS_DIR))
    args = ap.parse_args(argv)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    env_status = rb_mod._load_dotenv()

    n = args.limit if args.limit is not None else config.N_PER_ATTACK_PER_TIER
    n3 = args.limit if args.limit is not None else config.ATTACK3_N
    budget = (config.QUERY_BUDGET if args.limit is None
              else min(config.QUERY_BUDGET, max(3, args.limit)))

    cfg = config.active_config(args.limit)
    print("[adaptive] PRE-REGISTERED active config:")
    for k, v in cfg.items():
        print(f"           {k} = {v}")
    print(f"[adaptive] oracle budget this run = {budget}")
    print(f"[env] {env_status}")

    cache = sys_mod.ResponseCache(CACHE_DIR)
    requested = ({s.strip() for s in args.systems.split(",")} if args.systems
                 else set(config.ALL_SYSTEM_IDS))

    # Build the static registry once; warm the systems we need.
    all_systems = sys_mod.build_systems(cache)
    by_id = {s.id: s for s in all_systems}

    def _warm(system) -> bool:
        ok, reason = system.available()
        if not ok:
            print(f"[skip] {system.id}: {reason}")
            return False
        try:
            system.warmup()
        except Exception as e:  # noqa: BLE001
            print(f"[skip] {system.id}: warmup failed: {e}")
            return False
        return True

    # Stage 3 is keyless/free and required by Attacks 1 & 3 regardless of --systems.
    stage3 = by_id[config.STAGE3_SYSTEM]
    if not _warm(stage3):
        print("[fatal] Stage 3 unavailable; cannot run the harness.")
        return 1

    # Eval systems = requested ∩ available (warmed).
    eval_systems = []
    for sid in config.ALL_SYSTEM_IDS:
        if sid not in requested:
            continue
        sysobj = by_id[sid]
        if sysobj is stage3 or _warm(sysobj):
            eval_systems.append(sysobj)

    # Attack-2 search targets = Stage-4 systems that are requested AND available.
    stage4_targets = [by_id[sid] for sid in config.STAGE4_SYSTEMS
                      if sid in requested and by_id[sid] in eval_systems]

    mutator = Mutator(cache)
    judge = IntentJudge(cache)

    results: dict = {"attack1": {}, "attack2": {}, "attack3": {}}
    corpora_written: list[str] = []

    for tier in config.TIERS:
        print(f"\n===== TIER: {tier} =====")

        # ---- Attack 1: rule-evasion -> Stage 3 ----
        print("[attack1] rule-evasion vs Stage 3")
        b1, c1, s1 = run_attack1(tier, stage3, mutator, judge, eval_systems, n)
        results["attack1"][tier] = b1
        _write_corpus(c1, s1); corpora_written.append(c1.name)
        cache.flush()
        ic = b1["intent"]
        print(f"          seeds={b1['n_seeds']} evaders={ic['n_evaded_target']} "
              f"intent_kept={ic['n_intent_preserved']} excluded={ic['n_excluded_intent_lost']} "
              f"corpus={c1.n}")
        for s4, hd in b1["handoff"].items():
            print(f"          hand-off {s4}: Stage-4 caught {_pct(hd['stage4_caught_fraction'])} "
                  f"of Stage-3 evaders (n={hd['n_evaluated']})")

        # ---- Attack 2: classifier-oracle -> Stage 4 ----
        print("[attack2] classifier-oracle vs Stage 4")
        b2_list, c2_list, _s2map = run_attack2(tier, stage3, stage4_targets, mutator,
                                               judge, eval_systems, n, budget)
        results["attack2"][tier] = b2_list
        for blk, corp in zip(b2_list, c2_list):
            samples = _s2map_get(_s2map, tier, blk["target"])
            _write_corpus(corp, samples); corpora_written.append(corp.name)
            print(f"          target={blk['target']} via {blk['search_oracle']} "
                  f"evasions={blk['evasion_corpus_n']}/{blk['n_seeds']} "
                  f"budget_curve={blk['budget_curve']}")
        cache.flush()

        # ---- Attack 3: composition (illustrative) ----
        print("[attack3] composition / payload-splitting (illustrative)")
        b3, c3, s3cases = run_attack3(tier, stage3, judge, eval_systems, n3)
        results["attack3"][tier] = b3
        _write_corpus(c3, s3cases); corpora_written.append(c3.name)
        print(f"          {b3['summary']}")
        cache.flush()

    cache.flush()

    payload = {
        "meta": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "seed": config.SEED,
            "n_bootstrap": metrics_mod.N_BOOTSTRAP,
            "limit": args.limit,
            "oracle_budget": budget,
            "python": platform.python_version(),
            "platform": platform.platform(),
            "models": {"mutation": config.MUTATION_MODEL,
                       "intent_judge": config.INTENT_JUDGE_MODEL,
                       "openai_stage4": sys_mod.OPENAI_MODEL,
                       "anthropic_stage4": sys_mod.ANTHROPIC_MODEL},
            "env": env_status,
            "eval_systems": [s.id for s in eval_systems],
            "stage4_targets": [s.id for s in stage4_targets],
            "note": ("Adaptive robustness harness (separate from static results.json). "
                     "evasion = 1 - recall on the adaptive corpus via the existing "
                     "metrics path. Stage-4 classifiers temperature-pinned to 0; "
                     "mutation samples at "
                     f"{config.MUTATION_TEMPERATURE} (reproducibility via response cache)."),
        },
        "config": cfg,
        "results": results,
        "corpora_written": corpora_written,
        "cache_stats": {"hits": cache.hits, "misses": cache.misses},
    }
    out_json = out_dir / "adaptive_results.json"
    out_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\n[write] {out_json}")
    print(f"[write] {len(corpora_written)} corpora under {CORPORA_DIR}")
    print(f"[cache] hits={cache.hits} misses={cache.misses}  "
          f"(misses ~= billed LLM calls this run)")
    return 0


def _s2map_get(s2map, tier, target_id):
    return s2map.get(f"{tier}:{target_id}", [])


if __name__ == "__main__":
    sys.exit(main())
