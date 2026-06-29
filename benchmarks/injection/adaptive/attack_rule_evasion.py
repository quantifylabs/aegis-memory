"""Attack 1 — rule-evasion against the deterministic Stage 3 (free oracle).

AutoDAN-style iterated natural-language mutation. For each seed (a payload Stage 3
currently flags True), generate a bounded population of paraphrases, score each by
the **free, deterministic** Stage-3 oracle (``AegisStages13.predict``), and judge
intent only on the ones that actually evade Stage 3 (so the cheap intent calls are
spent only where they matter). Fitness = ``Stage-3 says benign`` AND ``intent
preserved``. If no candidate in a generation succeeds, the most-promising survivor
(one that evaded Stage 3 even if it lost intent, else the first candidate) seeds
the next generation — a tractable iterated-paraphrase search, not a full GA.

Stage 3 is free, so the loop iterates without spend; only the mutation + intent
calls cost money (cheap model, cached). The headline is the **hand-off**: of the
Stage-3 evaders this attack produces, what fraction does Stage 4 catch — computed
downstream by running the emitted corpus through ``aegis_stages_1_4_*`` and the
reused ``probe.compute_handoff`` arithmetic.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from ..datasets import Dataset
from . import config
from .intent import IntentJudge
from .mutate import Mutator
from .seeds import Seed


@dataclass
class EvasiveSample:
    """One attack attempt against one seed, with full provenance.

    Shared by Attack 1 and Attack 2. ``evaded`` is whether the target oracle was
    bypassed; ``intent_preserved`` is the separate intent judge's verdict. A sample
    counts toward the evasion numerator only if BOTH are true.
    """

    seed_id: str
    source_dataset: str
    orig_text: str
    evasive_text: str
    evaded: bool                 # target oracle bypassed (Stage 3 / Stage 4)
    intent_preserved: bool       # separate intent judge said YES
    transform_chain: list[str] = field(default_factory=list)  # cache tags applied, in order
    iterations_used: int = 0     # mutation generations / oracle rounds consumed
    queries_to_evade: int | None = None  # Attack 2: query index of first success
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def run_attack(seeds: list[Seed], stage3, mutator: Mutator, judge: IntentJudge,
               tier: str, blind: bool = False,
               population: int = config.ATTACK1_POPULATION,
               generations: int = config.ATTACK1_GENERATIONS,
               progress=None) -> list[EvasiveSample]:
    """Run rule-evasion over ``seeds`` and return one :class:`EvasiveSample` each.

    ``stage3`` exposes ``predict(text) -> bool`` (the free Stage-3 oracle).
    Tier semantics:

    - ``blind=False`` (white_box): the search *optimizes against* Stage 3 — it
      iterates across generations, carrying forward the most-promising survivor
      until an intent-preserving evasion is found or the generation budget runs out.
    - ``blind=True`` (grey_box): the attacker cannot consult the stage during the
      attack, so a single generation of blind paraphrases is produced and the first
      intent-preserving variant is taken; Stage 3 is then queried *only to measure*
      whether that blind variant happened to evade (not to guide the search).
      This is a single committed blind shot per seed, not population selection.

    Dependencies are injected so the test can stub them.
    """
    samples: list[EvasiveSample] = []
    gen_budget = 1 if blind else generations
    for i, seed in enumerate(seeds):
        if progress is not None:
            progress(i, len(seeds))
        current = seed.orig_text
        chain: list[str] = []
        best: EvasiveSample | None = None
        success: EvasiveSample | None = None
        err_note = ""
        for gen in range(gen_budget):
            tag = f"a1_{tier}_{seed.seed_id}_g{gen}".replace("#", "_")
            chain.append(tag)
            # A hard mutation/intent failure after SDK retries must not crash the
            # sweep: abort this seed's search and fall back to its best attempt.
            try:
                variants = mutator.variants(current, population, tag)
            except Exception as e:  # noqa: BLE001 — resilience for the long sweep
                err_note = f"aborted_on_error: {type(e).__name__}"
                break
            promising = None  # an evaded-but-intent-lost candidate to carry forward
            try:
                for cand in variants:
                    if not cand:
                        continue
                    if blind:
                        # Grey-box: pick by intent first (no stage feedback), then
                        # measure evasion only for reporting. Commit to the first
                        # intent-preserving variant; do not scan for an evader.
                        preserved = judge.judge(seed.orig_text, cand)
                        if not preserved:
                            if best is None:
                                best = EvasiveSample(seed.seed_id, seed.source_dataset,
                                                     seed.orig_text, cand, evaded=False,
                                                     intent_preserved=False,
                                                     transform_chain=list(chain),
                                                     iterations_used=gen + 1)
                            continue
                        evaded = not stage3.predict(cand)
                        sample = EvasiveSample(seed.seed_id, seed.source_dataset,
                                               seed.orig_text, cand, evaded=evaded,
                                               intent_preserved=True,
                                               transform_chain=list(chain),
                                               iterations_used=gen + 1)
                        success = sample
                        break
                    evaded = not stage3.predict(cand)  # Stage 3 benign == evaded
                    if not evaded:
                        if best is None:
                            best = EvasiveSample(seed.seed_id, seed.source_dataset,
                                                 seed.orig_text, cand, evaded=False,
                                                 intent_preserved=False,
                                                 transform_chain=list(chain),
                                                 iterations_used=gen + 1)
                        continue
                    preserved = judge.judge(seed.orig_text, cand)
                    sample = EvasiveSample(seed.seed_id, seed.source_dataset,
                                           seed.orig_text, cand, evaded=True,
                                           intent_preserved=preserved,
                                           transform_chain=list(chain),
                                           iterations_used=gen + 1)
                    if preserved:
                        success = sample
                        break
                    # Evaded but lost intent — keep as the best fallback + carry forward.
                    if promising is None:
                        promising = cand
                    if best is None or not best.evaded:
                        best = sample
            except Exception as e:  # noqa: BLE001 — resilience for the long sweep
                err_note = f"aborted_on_error: {type(e).__name__}"
                break
            if success is not None:
                break
            current = promising if promising is not None else current
        samples.append(success or best or EvasiveSample(
            seed.seed_id, seed.source_dataset, seed.orig_text, seed.orig_text,
            evaded=False, intent_preserved=False, transform_chain=list(chain),
            iterations_used=gen_budget, notes=err_note or "no_candidate_generated"))
    return samples


def to_corpus(samples: list[EvasiveSample], tier: str) -> Dataset:
    """Build the malicious-only :class:`Dataset` of intent-preserved evasive samples.

    Only samples that BOTH evaded Stage 3 AND preserved intent enter the corpus
    (every item is malicious -> ``label=True``); intent-lost or non-evading samples
    are excluded here and counted separately by the orchestrator.
    """
    items = [(s.evasive_text, True) for s in samples if s.evaded and s.intent_preserved]
    return Dataset(
        name=f"adaptive_attack1_{tier}", kind="malicious_direct", items=items,
        revision="adaptive-v1", source="adaptive:rule_evasion",
        notes=(f"Attack 1 (rule-evasion vs Stage 3), tier={tier}: "
               f"{len(items)} intent-preserved Stage-3 evaders."),
    )
