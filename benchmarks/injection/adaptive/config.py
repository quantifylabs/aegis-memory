"""PRE-REGISTERED frozen constants for the Phase 2 adaptive attack harness.

These are committed verbatim and must NOT vary across the real run (see
``TASK_adaptive_harness.md`` §config.py). A ``--limit`` smoke flag MAY override
``N_PER_ATTACK_PER_TIER`` down to a tiny value for dev, but the real run uses the
frozen constants. The prompt templates are part of the registration: changing
their wording changes what the harness measures, so they live here next to the
numeric constants.

The mutation / intent-judge prompts are imported from the precursor ``probe``
package so the wording is shared verbatim between the directional probe and this
harness (reuse, not a second copy that can silently drift).
"""

from __future__ import annotations

from ..probe.config import INTENT_JUDGE_PROMPT, PARAPHRASE_PROMPT  # noqa: F401 (re-exported verbatim)

# --- Frozen numeric constants ---------------------------------------------
SEED = 42                              # numpy + random + dataset subsampling
N_PER_ATTACK_PER_TIER = 250            # samples per attack per tier (real run)
QUERY_BUDGET = 30                      # Attack 2 oracle cap (queries per seed)
BUDGET_CURVE_POINTS = [5, 10, 20, 30]  # report Attack-2 evasion rate at each
TIERS = ["white_box", "grey_box"]
ATTACK3_N = 50                         # illustrative; smaller by design

# Attack 1 population search (bounded — iterated paraphrase, not a full GA).
ATTACK1_POPULATION = 6                 # candidates generated per seed per generation
ATTACK1_GENERATIONS = 3                # refinement generations before giving up

# --- Models (cheap generation; only the oracle hits the paid target) -------
MUTATION_MODEL = "gpt-4o-mini"         # CHEAP — generation / paraphrase
INTENT_JUDGE_MODEL = "gpt-4o-mini"     # cheap; a DIFFERENT call from any Stage-4 classifier
MUTATION_TEMPERATURE = 1.0             # variety across variants (cache gives reproducibility)

# --- Systems ---------------------------------------------------------------
# The free deterministic core (Attack 1's oracle + the hand-off numerator's
# left-hand side) and the paid Stage-4 classifiers (Attack 2's target).
STAGE3_SYSTEM = "aegis_stages_1_3"
STAGE4_SYSTEMS = ["aegis_stages_1_4_openai", "aegis_stages_1_4_anthropic"]

# Every system the adaptive corpora are evaluated against (the full 10). Reused
# from the static registry via ``build_systems`` in the orchestrator; this list
# only fixes the print/report order and the baseline transfer set.
ALL_SYSTEM_IDS = [
    "no_protection", "naive_regex", "protectai_deberta", "llama_prompt_guard_2",
    "llm_guard", "llm_judge_openai", "llm_judge_anthropic",
    "aegis_stages_1_3", "aegis_stages_1_4_openai", "aegis_stages_1_4_anthropic",
]
# Baselines that receive *transferred* Attack-2 samples (1 call each) rather than
# a full per-baseline oracle search (standard, defensible, far cheaper).
BASELINE_TRANSFER_SYSTEMS = [s for s in ALL_SYSTEM_IDS if s not in STAGE4_SYSTEMS]

SEED_SOURCE_DATASETS = ["deepset", "injecagent"]  # malicious sets seeds are pulled from


def active_config(limit: int | None) -> dict:
    """The pre-registration snapshot, printed at run start and stored in results."""
    n = limit if limit is not None else N_PER_ATTACK_PER_TIER
    return {
        "SEED": SEED,
        "N_PER_ATTACK_PER_TIER": n,
        "N_frozen": N_PER_ATTACK_PER_TIER,
        "limit": limit,
        "QUERY_BUDGET": QUERY_BUDGET,
        "BUDGET_CURVE_POINTS": BUDGET_CURVE_POINTS,
        "TIERS": TIERS,
        "ATTACK3_N": limit if limit is not None else ATTACK3_N,
        "ATTACK1_POPULATION": ATTACK1_POPULATION,
        "ATTACK1_GENERATIONS": ATTACK1_GENERATIONS,
        "MUTATION_MODEL": MUTATION_MODEL,
        "INTENT_JUDGE_MODEL": INTENT_JUDGE_MODEL,
        "MUTATION_TEMPERATURE": MUTATION_TEMPERATURE,
        "STAGE3_SYSTEM": STAGE3_SYSTEM,
        "STAGE4_SYSTEMS": STAGE4_SYSTEMS,
        "SEED_SOURCE_DATASETS": SEED_SOURCE_DATASETS,
    }
