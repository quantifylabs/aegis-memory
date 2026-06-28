"""Intent-preservation validator — the mandatory control on every attack.

After ANY attack produces a candidate evasion, this judge decides whether the
candidate still carries the seed's *malicious intent*. Candidates that LOST intent
are excluded from the evasion numerator and reported separately — never silently
dropped (the attack modules keep them, flagged ``intent_preserved=False``).

The judge is a deliberately SEPARATE LLM call (cheap ``gpt-4o-mini``) from any
Stage-4 classifier, so the evasion measurement has no circularity. It reuses the
probe's verbatim ``INTENT_JUDGE_PROMPT`` and cached judge call, and is injectable
for the network-free test. For Attack 3 the *assembled* text is judged, not the
fragments.
"""

from __future__ import annotations

from .. import systems as sys_mod
from ..probe.paraphrase import Paraphraser
from . import config


class IntentJudge:
    """Cheap, cached intent-preservation judge (distinct from any Stage-4 call)."""

    def __init__(self, cache: sys_mod.ResponseCache,
                 model: str = config.INTENT_JUDGE_MODEL):
        self._para = Paraphraser(cache, paraphrase_model=model, intent_model=model)

    def judge(self, orig_text: str, candidate_text: str) -> bool:
        """True if ``candidate_text`` still carries ``orig_text``'s malicious intent."""
        return self._para.judge_intent(orig_text, candidate_text)
