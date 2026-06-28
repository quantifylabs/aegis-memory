"""Network-free tests for the adaptive paraphrase probe (Phase 1.5).

Drives the probe's core functions with stubbed paraphraser + stubbed systems so
the whole pipeline runs without any LLM call. Locks in:

  - intent-preservation EXCLUDES-and-reports (never silently drops),
  - per-system evasion-rate equals ``1 - recall`` off the existing metrics path,
  - the Stage-3 -> Stage-4 hand-off arithmetic on a hand-built fixture.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make `benchmarks.injection.*` importable (repo root is one up from tests/).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from benchmarks.injection import systems as sys_mod  # noqa: E402
from benchmarks.injection.probe import config, run_probe  # noqa: E402
from benchmarks.injection.probe.paraphrase import Candidate, build_candidates  # noqa: E402
from benchmarks.injection.probe.seed_picker import Seed  # noqa: E402


# --------------------------------------------------------------------------
# Stubs
# --------------------------------------------------------------------------
class StubSystem(sys_mod.System):
    """Deterministic system: flags exactly the texts in ``caught``.

    Texts in ``errors_on`` raise inside ``predict``; the base ``evaluate_batch``
    converts that to a ``None`` prediction (per-item failure), which is how a
    real Stage-4 timeout/429/parse-error surfaces.
    """

    def __init__(self, sid: str, caught: set[str], errors_on: set[str] | None = None):
        self.id = sid
        self._caught = caught
        self._errors_on = errors_on or set()

    def available(self):
        return True, ""

    def warmup(self):
        return None

    def predict(self, text: str) -> bool:
        if text in self._errors_on:
            raise RuntimeError("simulated per-item failure")
        return text in self._caught


class StubParaphraser:
    """Canned variants + intent verdicts, no network.

    ``no_for`` is a set of paraphrase texts the intent judge rules NO on.
    """

    def __init__(self, no_for: set[str] | None = None):
        self._no_for = no_for or set()

    def generate(self, seed_text: str, k: int) -> list[str]:
        return [f"{seed_text}::para{i}" for i in range(k)]

    def judge_intent(self, seed_text: str, paraphrase_text: str) -> bool:
        return paraphrase_text not in self._no_for


def _candidate(seed_id, text, preserved=True, variant_idx=0):
    return Candidate(seed_id=seed_id, source_dataset="deepset", orig_text="orig",
                     variant_idx=variant_idx, paraphrase_text=text,
                     intent_preserved=preserved)


# --------------------------------------------------------------------------
# build_candidates: intent exclusion is reported, not silently dropped
# --------------------------------------------------------------------------
def test_build_candidates_excludes_but_keeps_failed_intent():
    seeds = [Seed(seed_id="deepset#0", source_dataset="deepset", orig_index=0,
                  orig_text="payload A")]
    # The judge rules NO on variant 1 only.
    para = StubParaphraser(no_for={"payload A::para1"})
    cands = build_candidates(seeds, para, k=3)

    assert len(cands) == 3, "every variant is kept, even excluded ones"
    preserved = [c for c in cands if c.intent_preserved]
    excluded = [c for c in cands if not c.intent_preserved]
    assert len(preserved) == 2 and len(excluded) == 1
    assert excluded[0].paraphrase_text == "payload A::para1"


# --------------------------------------------------------------------------
# evaluate_candidates: evasion == 1 - recall, only preserved candidates count
# --------------------------------------------------------------------------
def _fixture_candidates():
    # 4 intent-preserved + 1 excluded (must be ignored by evaluation).
    return [
        _candidate("s1", "c1", preserved=True),
        _candidate("s2", "c2", preserved=True),
        _candidate("s3", "c3", preserved=True),
        _candidate("s4", "c4", preserved=True),
        _candidate("s5", "c5_excluded", preserved=False),
    ]


def _fixture_systems():
    # Stage 3 catches only c1 -> evaders are c2, c3, c4.
    s3 = StubSystem(config.STAGE3_SYSTEM, caught={"c1"})
    # Stage-4 OpenAI catches c1, c2, c3 (catches 2/3 of the evaders: c2, c3).
    s4o = StubSystem("aegis_stages_1_4_openai", caught={"c1", "c2", "c3"})
    # Stage-4 Anthropic catches c1, c3, c4 (catches 2/3 of the evaders: c3, c4).
    s4a = StubSystem("aegis_stages_1_4_anthropic", caught={"c1", "c3", "c4"})
    # External baseline catches nothing.
    lg = StubSystem("llm_guard", caught=set())
    return [s3, s4o, s4a, lg]


def test_evaluate_candidates_evasion_equals_one_minus_recall():
    cands = _fixture_candidates()
    per_system = run_probe.evaluate_candidates(cands, _fixture_systems())

    s3 = per_system[config.STAGE3_SYSTEM]
    assert s3["status"] == "ok"
    assert s3["n"] == 4, "the excluded candidate is not evaluated"
    assert s3["recall"] == 0.25          # tp=1 (c1), fn=3
    assert s3["evasion_rate"] == 0.75    # exactly 1 - recall
    # c1 caught, c2/c3/c4 evaded.
    assert per_system[config.STAGE3_SYSTEM]["predictions"]["s1::v0"] is True
    assert per_system[config.STAGE3_SYSTEM]["predictions"]["s2::v0"] is False

    lg = per_system["llm_guard"]
    assert lg["evasion_rate"] == 1.0     # caught nothing


# --------------------------------------------------------------------------
# compute_handoff: Stage-3 evaders -> Stage-4 catch fractions
# --------------------------------------------------------------------------
def test_handoff_arithmetic():
    cands = _fixture_candidates()
    per_system = run_probe.evaluate_candidates(cands, _fixture_systems())
    handoff = run_probe.compute_handoff(cands, per_system)

    assert handoff["stage3_evader_count"] == 3
    s4o = handoff["by_stage4"]["aegis_stages_1_4_openai"]
    s4a = handoff["by_stage4"]["aegis_stages_1_4_anthropic"]
    assert (s4o["caught"], s4o["total"]) == (2, 3)
    assert abs(s4o["fraction"] - 2 / 3) < 1e-9
    assert (s4a["caught"], s4a["total"]) == (2, 3)
    assert abs(s4a["fraction"] - 2 / 3) < 1e-9


def test_handoff_empty_evader_set_is_none_not_crash():
    # Stage 3 catches everything -> no evaders, fraction is None (not 0/0).
    cands = [_candidate("s1", "c1"), _candidate("s2", "c2")]
    systems = [
        StubSystem(config.STAGE3_SYSTEM, caught={"c1", "c2"}),
        StubSystem("aegis_stages_1_4_openai", caught={"c1", "c2"}),
        StubSystem("aegis_stages_1_4_anthropic", caught={"c1", "c2"}),
        StubSystem("llm_guard", caught=set()),
    ]
    per_system = run_probe.evaluate_candidates(cands, systems)
    handoff = run_probe.compute_handoff(cands, per_system)
    assert handoff["stage3_evader_count"] == 0
    assert handoff["by_stage4"]["aegis_stages_1_4_openai"]["fraction"] is None


# --------------------------------------------------------------------------
# render_summary smoke: produces the decision table without crashing
# --------------------------------------------------------------------------
def test_render_summary_contains_headline():
    cands = _fixture_candidates()
    per_system = run_probe.evaluate_candidates(cands, _fixture_systems())
    handoff = run_probe.compute_handoff(cands, per_system)
    meta = {"timestamp": "2026-06-28T00:00:00+00:00"}
    counts = {"n_seeds": 4, "n_paraphrases": 5, "n_intent_preserved": 4, "n_excluded": 1}
    md = run_probe.render_summary(meta, counts, per_system, handoff)

    assert "adaptive paraphrase probe" in md
    assert "The hand-off (decision headline)" in md
    assert "Excluded: 1" in md
    assert "aegis_stages_1_3" in md


# --------------------------------------------------------------------------
# Regression: an errored Stage-4 item must NOT be counted as a catch
# --------------------------------------------------------------------------
def test_errored_evader_excluded_from_handoff_both_sides():
    # Stage 3 misses c2 and c3 -> evaders {c2, c3}. Stage-4 OpenAI ERRORS on c2
    # and catches c3. The errored evader must be excluded from BOTH the numerator
    # AND the denominator: 1/1 = 100% over what was actually evaluated, not 1/2
    # (the old fn-set bug counted it caught) and not 0/2 (denominator left it in).
    cands = [_candidate("s1", "c1"), _candidate("s2", "c2"), _candidate("s3", "c3")]
    systems = [
        StubSystem(config.STAGE3_SYSTEM, caught={"c1"}),                       # evaders: {c2, c3}
        StubSystem("aegis_stages_1_4_openai", caught={"c3"}, errors_on={"c2"}),
        StubSystem("aegis_stages_1_4_anthropic", caught={"c2", "c3"}),          # catches both
        StubSystem("llm_guard", caught=set()),
    ]
    per_system = run_probe.evaluate_candidates(cands, systems)

    s4o = per_system["aegis_stages_1_4_openai"]
    assert s4o["n_errors"] == 1
    assert s4o["predictions"]["s2::v0"] is None       # errored -> None, not True
    assert s4o["n"] == 2                              # c1 + c3 evaluated; c2 errored

    handoff = run_probe.compute_handoff(cands, per_system)
    assert handoff["stage3_evader_count"] == 2
    o = handoff["by_stage4"]["aegis_stages_1_4_openai"]
    assert (o["caught"], o["total"]) == (1, 1)        # c2 dropped from denominator
    assert o["evaders_errored"] == 1
    assert o["fraction"] == 1.0
    # Anthropic evaluated both evaders and caught both.
    a = handoff["by_stage4"]["aegis_stages_1_4_anthropic"]
    assert (a["caught"], a["total"], a["evaders_errored"]) == (2, 2, 0)
    assert a["fraction"] == 1.0


# --------------------------------------------------------------------------
# Regression: seed pool filters to malicious labels (mixed-label deepset)
# --------------------------------------------------------------------------
def test_stage3_true_pool_filters_to_malicious_labels(monkeypatch):
    from benchmarks.injection import datasets as ds_mod
    from benchmarks.injection.probe import seed_picker

    # A mixed-label dataset where Stage 3 flags BOTH rows (a benign false positive).
    fake = ds_mod.Dataset(
        name="fake", kind="malicious_direct", status="ok",
        items=[("malicious injection payload", True), ("perfectly benign row", False)],
    )
    monkeypatch.setitem(ds_mod.LOADERS, "fake", lambda limit=None: fake)

    class _Stage3FlagsEverything:
        def predict(self, text: str) -> bool:
            return True  # incl. the benign row (the over-flag the guard must drop)

    pool = seed_picker._stage3_true_pool("fake", _Stage3FlagsEverything())
    assert pool == ["malicious injection payload"], "benign FP must not enter the seed pool"
