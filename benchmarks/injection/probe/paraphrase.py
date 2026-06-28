"""Generate paraphrases of seed payloads and judge intent preservation.

Both the paraphrase calls and the intent-judge call route through the shared
``ResponseCache`` (collision-safe ``(system_id, model_id, sha256(prompt))`` keys),
so fresh prompts miss by design on run 1 and hit on run 2.

The intent judge is a deliberately *separate* LLM call from any Stage-4
classifier (no circularity): a candidate that fails the intent check is excluded
from the evasion numerator but never silently dropped — it stays in the candidate
list flagged ``intent_preserved=False`` and is reported.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from .. import systems as sys_mod
from . import config
from .seed_picker import Seed


@dataclass
class Candidate:
    seed_id: str
    source_dataset: str
    orig_text: str
    variant_idx: int
    paraphrase_text: str
    intent_preserved: bool

    def to_dict(self) -> dict:
        return asdict(self)


class Paraphraser:
    """Cheap gpt-4o-mini paraphraser + intent-preservation judge.

    Real OpenAI calls mirror :meth:`systems.LLMJudge._raw`: a sync ``OpenAI()``
    client with the prompt cached verbatim around it. The class is injectable so
    tests can substitute a stub with canned variants/verdicts (no network).
    """

    INTENT_JUDGE_ID = "probe_intent_judge"

    def __init__(self, cache: sys_mod.ResponseCache,
                 paraphrase_model: str = config.PARAPHRASE_MODEL,
                 intent_model: str = config.INTENT_JUDGE_MODEL,
                 temperature: float = config.PARAPHRASE_TEMPERATURE):
        self._cache = cache
        self._paraphrase_model = paraphrase_model
        self._intent_model = intent_model
        self._temperature = temperature

    # --- low-level OpenAI completion (cached) ------------------------------
    def _complete(self, system_id: str, model: str, prompt: str,
                  temperature: float, max_tokens: int) -> str:
        cached = self._cache.get(system_id, model, prompt)
        if cached is not None:
            return cached
        from openai import OpenAI

        # Configure SDK-level retries with exponential backoff (the default is 2)
        # so a long adaptive sweep rides out transient 429s instead of failing a
        # cheap mutation/intent call. Mirrors the async clients in systems.py.
        client = OpenAI(max_retries=sys_mod.MAX_RETRIES)  # reads OPENAI_API_KEY
        resp = client.chat.completions.create(
            model=model, temperature=temperature, max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.choices[0].message.content or ""
        self._cache.set(system_id, model, prompt, raw)
        return raw

    # --- public API --------------------------------------------------------
    def generate(self, seed_text: str, k: int) -> list[str]:
        """Return ``k`` paraphrases of ``seed_text``.

        The prompt body is committed verbatim (only ``{seed_text}`` is filled).
        To give each of the K variants its own cacheable, reproducible slot, the
        per-variant cache namespace is ``probe_paraphrase_v{i}`` (the prompt text
        is identical across variants; only the cache namespace differs).
        """
        prompt = config.PARAPHRASE_PROMPT.format(seed_text=seed_text)
        out: list[str] = []
        for i in range(k):
            raw = self._complete(f"probe_paraphrase_v{i}", self._paraphrase_model,
                                 prompt, self._temperature, max_tokens=512)
            out.append(raw.strip())
        return out

    def judge_intent(self, seed_text: str, paraphrase_text: str) -> bool:
        """True if the paraphrase still carries the original malicious intent."""
        prompt = config.INTENT_JUDGE_PROMPT.format(
            seed_text=seed_text, paraphrase_text=paraphrase_text)
        raw = self._complete(self.INTENT_JUDGE_ID, self._intent_model,
                             prompt, temperature=0, max_tokens=4)
        return raw.strip().upper().startswith("YES")


def build_candidates(seeds: list[Seed], paraphraser: Paraphraser,
                     k: int = config.N_PARAPHRASES_PER_SEED) -> list[Candidate]:
    """Generate K paraphrases per seed and attach an intent-preservation verdict.

    Candidates whose intent check returns NO are kept (``intent_preserved=False``)
    so the probe can report the exclusion count; they are dropped only from the
    evasion numerator downstream, never silently.
    """
    candidates: list[Candidate] = []
    for seed in seeds:
        variants = paraphraser.generate(seed.orig_text, k)
        for i, paraphrase_text in enumerate(variants):
            preserved = paraphraser.judge_intent(seed.orig_text, paraphrase_text)
            candidates.append(Candidate(
                seed_id=seed.seed_id,
                source_dataset=seed.source_dataset,
                orig_text=seed.orig_text,
                variant_idx=i,
                paraphrase_text=paraphrase_text,
                intent_preserved=preserved,
            ))
    return candidates
