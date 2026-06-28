"""Attack 2 — classifier-oracle evasion against the Stage-4 LLM classifier.

DataSentinel-style detector-evasion loop. For each seed (a payload the target
``aegis_stages_1_4_*`` currently flags True), run up to ``QUERY_BUDGET`` rounds of:

    generate candidate (cheap MUTATION_MODEL)  ->
    query the target Stage-4 classifier (the REAL, billed cost)  ->
    keep if benign AND intent-preserved, else refine and try again.

The query index at which the first intent-preserving evasion is found is recorded
per seed (``queries_to_evade``), or ``None`` if not evaded within budget — this
gives the evasion-vs-budget curve. Stage 4 is temperature-pinned to 0 (Phase 0
§F), so the oracle signal is stable across rounds.

Cost discipline: exactly one paid target query per round (≤ budget per seed); the
mutation + intent calls run on the cheap cached model. Baselines are NOT searched
directly — the orchestrator transfers the found samples to them (1 call each).
"""

from __future__ import annotations

from .attack_rule_evasion import EvasiveSample
from ..datasets import Dataset
from . import config
from .intent import IntentJudge
from .mutate import Mutator
from .seeds import Seed


def run_attack(seeds: list[Seed], target, mutator: Mutator, judge: IntentJudge,
               tier: str, budget: int = config.QUERY_BUDGET,
               progress=None) -> list[EvasiveSample]:
    """Run the oracle loop over ``seeds`` against ``target`` (an ``AegisStages14``).

    ``target.predict(text) -> bool`` is the billed Stage-4 query. Returns one
    :class:`EvasiveSample` per seed with ``queries_to_evade`` set on success (1-based
    round index) or ``None`` if the budget is exhausted. Dependencies are injected
    so the test can drive the loop with a stub target + stub mutator.
    """
    samples: list[EvasiveSample] = []
    for i, seed in enumerate(seeds):
        if progress is not None:
            progress(i, len(seeds))
        current = seed.orig_text
        chain: list[str] = []
        result: EvasiveSample | None = None
        last_cand = seed.orig_text
        err_note = ""
        for r in range(budget):
            tag = f"a2_{tier}_{seed.seed_id}_r{r}".replace("#", "_")
            chain.append(tag)
            # A hard failure after SDK retries (e.g. a sustained 429/quota error)
            # must not crash a multi-hour sweep: degrade to "abort this seed" and
            # move on. Completed calls are already cached, so a re-run resumes.
            try:
                variants = mutator.variants(current, 1, tag)
                cand = (variants[0] if variants else "").strip()
                if not cand:
                    continue
                last_cand = cand
                queries = r + 1
                evaded = not target.predict(cand)  # one billed Stage-4 query
                if not evaded:
                    current = cand  # refine the rejected candidate next round
                    continue
                preserved = judge.judge(seed.orig_text, cand)
            except Exception as e:  # noqa: BLE001 — resilience for the long sweep
                err_note = f"aborted_on_error: {type(e).__name__}"
                break
            if preserved:
                result = EvasiveSample(
                    seed.seed_id, seed.source_dataset, seed.orig_text, cand,
                    evaded=True, intent_preserved=True, transform_chain=list(chain),
                    iterations_used=queries, queries_to_evade=queries)
                break
            # Evaded the classifier but lost intent: not a valid evasion; keep
            # refining toward an intent-preserving bypass within the remaining budget.
            current = cand
        if result is None:
            result = EvasiveSample(
                seed.seed_id, seed.source_dataset, seed.orig_text, last_cand,
                evaded=False, intent_preserved=False, transform_chain=list(chain),
                iterations_used=budget, queries_to_evade=None,
                notes=err_note or "not_evaded_within_budget")
        samples.append(result)
    return samples


def budget_curve(samples: list[EvasiveSample],
                 points: list[int] = config.BUDGET_CURVE_POINTS) -> dict[str, float | None]:
    """Evasion rate (intent-preserving) at each query budget.

    For budget ``b``: numerator = seeds first evaded (intent-preserved) within ``b``
    queries; denominator = all attacked seeds. Returns ``{str(b): rate}``.
    """
    n = len(samples)
    out: dict[str, float | None] = {}
    for b in points:
        if n == 0:
            out[str(b)] = None
            continue
        evaded = sum(1 for s in samples
                     if s.intent_preserved and s.queries_to_evade is not None
                     and s.queries_to_evade <= b)
        out[str(b)] = evaded / n
    return out


def to_corpus(samples: list[EvasiveSample], tier: str, target_id: str) -> Dataset:
    """Malicious-only :class:`Dataset` of intent-preserved evasions found in budget.

    These are the samples transferred to baselines (1 call each) for transfer
    evasion, and re-evaluated against the Aegis systems for the evasion table.
    """
    items = [(s.evasive_text, True) for s in samples
             if s.evaded and s.intent_preserved]
    return Dataset(
        name=f"adaptive_attack2_{tier}_{target_id}", kind="malicious_direct", items=items,
        revision="adaptive-v1", source="adaptive:classifier_oracle",
        notes=(f"Attack 2 (classifier-oracle vs {target_id}), tier={tier}: "
               f"{len(items)} intent-preserved Stage-4 evasions within budget."),
    )
