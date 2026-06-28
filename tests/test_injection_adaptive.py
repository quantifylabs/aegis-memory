"""Network-free tests for the Phase 2 adaptive attack harness.

Drives the harness's attack loops + evaluation with stubbed mutation / intent /
systems so the whole pipeline runs without any LLM call. Locks in:

  - Attack 1 produces intent-preserved Stage-3 evaders, and intent-lost candidates
    are EXCLUDED from the corpus but reported (never silently dropped);
  - ``evaluate_corpus`` evasion equals ``1 - recall`` off the existing metrics path,
    and an errored item is excluded from BOTH the metric and the denominator;
  - Attack 2 records queries-to-evade and the budget curve is correct;
  - Attack 3's split bookkeeping (per-write vs assembled).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from benchmarks.injection import datasets as ds_mod  # noqa: E402
from benchmarks.injection import systems as sys_mod  # noqa: E402
from benchmarks.injection.adaptive import (  # noqa: E402
    attack_composition as a3,
    attack_oracle as a2,
    attack_rule_evasion as a1,
    run_adaptive,
)
from benchmarks.injection.adaptive.seeds import Seed  # noqa: E402


# --------------------------------------------------------------------------
# Stubs (no network)
# --------------------------------------------------------------------------
class FlagOnSubstr(sys_mod.System):
    """Flags any text containing one of ``needles``; raises on ``errors_on``."""

    def __init__(self, sid, needles, errors_on=None):
        self.id = sid
        self._needles = needles
        self._err = errors_on

    def available(self):
        return True, ""

    def warmup(self):
        return None

    def predict(self, text: str) -> bool:
        if self._err and self._err in text:
            raise RuntimeError("simulated per-item failure")
        return any(nd in text for nd in self._needles)


class StubMutator:
    """Deterministic variants. ``defang`` is stripped so variants evade a needle."""

    def __init__(self, needle="MAL", evade_at_round=0):
        self._needle = needle
        self._evade_at = evade_at_round

    def variants(self, text: str, n: int, tag: str) -> list[str]:
        out = []
        for i in range(n):
            # Round index is the trailing "_r{N}" / "_g{N}" in the tag; evade once
            # we've reached the configured round so Attack 2 query counting is testable.
            reached = any(f"r{r}" in tag for r in range(self._evade_at, 999)) or "g" in tag
            cand = text.replace(self._needle, "clean") if reached else f"{text}_try{i}"
            out.append(f"{cand}#{tag}#{i}")
        return out


class StubJudge:
    """Intent judge: NO only for candidates whose text contains ``no_marker``."""

    def __init__(self, no_marker=None):
        self._no = no_marker

    def judge(self, orig_text: str, candidate_text: str) -> bool:
        return not (self._no and self._no in candidate_text)


# --------------------------------------------------------------------------
# Attack 1
# --------------------------------------------------------------------------
def _seed(sid="deepset#0", text="MAL payload here"):
    return Seed(seed_id=sid, source_dataset="deepset", orig_index=0, orig_text=text)


def test_attack1_produces_intent_preserved_evaders():
    stage3 = FlagOnSubstr("aegis_stages_1_3", needles=["MAL"])
    mutator = StubMutator(needle="MAL")          # variants drop "MAL" -> evade stage3
    judge = StubJudge()                          # all intent-preserved
    seeds = [_seed("deepset#0"), _seed("deepset#1", "MAL second payload")]

    samples = a1.run_attack(seeds, stage3, mutator, judge, tier="white_box")
    assert len(samples) == 2
    assert all(s.evaded and s.intent_preserved for s in samples)

    corpus = a1.to_corpus(samples, "white_box")
    assert corpus.n == 2
    assert all(label is True for _, label in corpus.items)
    assert all("MAL" not in t for t, _ in corpus.items)  # every corpus item evades stage3


def test_attack1_intent_lost_excluded_but_reported():
    stage3 = FlagOnSubstr("aegis_stages_1_3", needles=["MAL"])
    mutator = StubMutator(needle="MAL")
    judge = StubJudge(no_marker="clean")         # every evading variant loses intent
    seeds = [_seed("deepset#0")]

    samples = a1.run_attack(seeds, stage3, mutator, judge, tier="white_box")
    counts = run_adaptive._intent_counts(samples)
    # The candidate evaded Stage 3 but the judge ruled intent lost -> excluded from
    # the corpus, still counted/reported.
    assert counts["n_evaded_target"] == 1
    assert counts["n_intent_preserved"] == 0
    assert counts["n_excluded_intent_lost"] == 1
    assert a1.to_corpus(samples, "white_box").n == 0


# --------------------------------------------------------------------------
# evaluate_corpus: evasion == 1 - recall, errors excluded both sides
# --------------------------------------------------------------------------
def _corpus(texts):
    return ds_mod.Dataset(name="t", kind="malicious_direct", status="ok",
                          items=[(t, True) for t in texts])


def test_evaluate_corpus_evasion_equals_one_minus_recall():
    corpus = _corpus(["e1", "e2", "e3", "e4"])
    # System catches only e1 -> recall 0.25, evasion 0.75.
    sysobj = FlagOnSubstr("sys", needles=["e1"])
    res = run_adaptive.evaluate_corpus(corpus, [sysobj])["sys"]
    assert res["status"] == "ok"
    assert res["n"] == 4
    assert res["recall"] == 0.25
    assert res["evasion_rate"] == 0.75


def test_evaluate_corpus_excludes_errored_from_denominator():
    corpus = _corpus(["c_hit", "c_err", "c_miss"])
    # Catches c_hit, ERRORS on c_err, misses c_miss -> evaluated n=2, recall 0.5.
    sysobj = FlagOnSubstr("sys", needles=["c_hit"], errors_on="c_err")
    res = run_adaptive.evaluate_corpus(corpus, [sysobj])["sys"]
    assert res["n"] == 2 and res["n_errors"] == 1
    assert res["recall"] == 0.5 and res["evasion_rate"] == 0.5


def test_evaluate_corpus_empty():
    res = run_adaptive.evaluate_corpus(_corpus([]), [FlagOnSubstr("sys", [])])
    assert res["sys"]["status"] == "empty_corpus"


# --------------------------------------------------------------------------
# Attack 2: queries-to-evade + budget curve
# --------------------------------------------------------------------------
def test_attack2_records_queries_to_evade():
    # Target flags anything containing "MAL"; mutator evades from round 2 onward.
    target = FlagOnSubstr("aegis_stages_1_4_openai", needles=["MAL"])
    mutator = StubMutator(needle="MAL", evade_at_round=2)
    judge = StubJudge()
    seeds = [_seed("deepset#0")]
    samples = a2.run_attack(seeds, target, mutator, judge, tier="white_box", budget=10)
    s = samples[0]
    assert s.evaded and s.intent_preserved
    assert s.queries_to_evade == 3  # rounds r0,r1 caught; r2 (1-based -> 3) evades


def test_attack2_budget_curve_arithmetic():
    from benchmarks.injection.adaptive.attack_rule_evasion import EvasiveSample
    samples = [
        EvasiveSample("s0", "deepset", "o", "e", evaded=True, intent_preserved=True,
                      queries_to_evade=3),
        EvasiveSample("s1", "deepset", "o", "e", evaded=True, intent_preserved=True,
                      queries_to_evade=12),
        EvasiveSample("s2", "deepset", "o", "e", evaded=False, intent_preserved=False,
                      queries_to_evade=None),
        EvasiveSample("s3", "deepset", "o", "e", evaded=True, intent_preserved=True,
                      queries_to_evade=7),
    ]
    curve = a2.budget_curve(samples, points=[5, 10, 20, 30])
    assert curve["5"] == 1 / 4    # only s0 (q=3) within 5
    assert curve["10"] == 2 / 4   # s0 (3), s3 (7)
    assert curve["20"] == 3 / 4   # + s1 (12); s2 never evaded
    assert curve["30"] == 3 / 4


def test_attack2_not_evaded_within_budget():
    target = FlagOnSubstr("aegis_stages_1_4_openai", needles=["MAL"])
    mutator = StubMutator(needle="MAL", evade_at_round=999)  # never strips MAL
    judge = StubJudge()
    samples = a2.run_attack([_seed("deepset#0")], target, mutator, judge,
                            tier="white_box", budget=4)
    assert samples[0].queries_to_evade is None
    assert not samples[0].evaded
    assert a2.to_corpus(samples, "white_box", target.id).n == 0


# --------------------------------------------------------------------------
# Attack 3: composition bookkeeping
# --------------------------------------------------------------------------
def test_attack3_split_evades_when_no_fragment_flagged():
    # Stage 3 flags a fragment only if it contains the full bigram "ignore all".
    stage3 = FlagOnSubstr("aegis_stages_1_3", needles=["ignore all"])
    judge = StubJudge()  # assembled intent preserved
    # 6 words -> 2-way split is 3+3, so the "ignore all" bigram straddles the
    # fragment boundary ("aa bb ignore" | "all cc dd") and neither half is flagged.
    seed = _seed("deepset#0", text="aa bb ignore all cc dd")
    cases = a3.run_attack([seed], stage3, judge, tier="white_box", n=1)
    assert len(cases) == 1
    c = cases[0]
    # A 2-way split breaks the "ignore all" bigram across fragments -> none flagged.
    assert not any(c.per_fragment_flagged)
    assert c.assembled_intent_preserved
    assert c.split_evades
    summ = a3.summarize(cases)
    assert summ["cases_split_evades"] == 1
    assert summ["split_evasion_rate"] == 1.0
