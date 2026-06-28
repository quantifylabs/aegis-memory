"""Cheap-model mutation operator for the adaptive attacks.

Wraps the precursor probe's cached :class:`probe.paraphrase.Paraphraser` (an
``OPENAI`` ``gpt-4o-mini`` paraphraser routed through the shared ``ResponseCache``)
into a small mutation API used by both attack loops:

  - :meth:`Mutator.variants` — generate ``n`` natural-language paraphrases of a
    text (AutoDAN-style surface mutation that preserves malicious intent). A
    ``tag`` (generation index for Attack 1, round index for Attack 2) namespaces
    each variant's cache slot so re-runs are reproducible and never re-billed.

Only mutation (this module) and the intent judge (:mod:`intent`) hit the cheap
model. The expensive target classifier is queried only by the Attack-2 oracle.
The class is injectable, so the network-free test substitutes a stub with canned
variants.
"""

from __future__ import annotations

from .. import systems as sys_mod
from ..probe.paraphrase import Paraphraser
from . import config


class Mutator:
    """Generate intent-preserving surface mutations via the cached cheap model."""

    def __init__(self, cache: sys_mod.ResponseCache,
                 model: str = config.MUTATION_MODEL,
                 temperature: float = config.MUTATION_TEMPERATURE):
        self._model = model
        self._temperature = temperature
        # Reuse the probe's proven cached completion path (same OpenAI client +
        # verbatim PARAPHRASE_PROMPT); intent judging lives in intent.py.
        self._para = Paraphraser(cache, paraphrase_model=model,
                                 intent_model=config.INTENT_JUDGE_MODEL,
                                 temperature=temperature)

    def variants(self, text: str, n: int, tag: str) -> list[str]:
        """Return ``n`` paraphrases of ``text``.

        ``tag`` discriminates the per-variant cache namespace
        (``adaptive_mutate_{tag}_v{i}``) so each (generation/round, variant) pair
        gets its own reproducible, cacheable slot. The prompt body is the frozen
        ``PARAPHRASE_PROMPT`` (only ``{seed_text}`` is filled).
        """
        prompt = config.PARAPHRASE_PROMPT.format(seed_text=text)
        out: list[str] = []
        for i in range(n):
            raw = self._para._complete(
                f"adaptive_mutate_{tag}_v{i}", self._model, prompt,
                self._temperature, max_tokens=512,
            )
            out.append(raw.strip())
        return out
