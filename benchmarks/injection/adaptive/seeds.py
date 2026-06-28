"""Select attack seeds: malicious payloads a TARGET system currently flags True.

Evasion is only meaningful against a payload the target already catches — evading
something it already misses isn't evasion. This generalizes the precursor probe's
``seed_picker`` (which was hard-wired to Stage 3) to *any* target system, because:

  - Attack 1 (rule-evasion) seeds against the free, deterministic ``aegis_stages_1_3``.
  - Attack 2 (classifier-oracle) seeds against the paid ``aegis_stages_1_4_*``.

The malicious-only guard (``label is True``) is load-bearing on mixed-label
``deepset``: without it a Stage-N false positive on a benign row would become an
evasion seed and contaminate the experiment. ``injecagent`` is all-malicious.

Seeds are drawn from a deterministic, stratified shuffle of the malicious pool and
the target is queried in that fixed order until ``target`` seeds are collected (or
``max_probe`` queries are spent — a cost cap that matters when the target is the
paid Stage-4 classifier). The :class:`probe.seed_picker.Seed` dataclass is reused
verbatim.
"""

from __future__ import annotations

import random

from .. import datasets as ds_mod
from ..probe.seed_picker import Seed, _even_split
from . import config


def _malicious_pool(name: str) -> list[str]:
    """Malicious (``label is True``) texts from dataset ``name`` (full set, no subsample)."""
    loader = ds_mod.LOADERS[name]
    dataset = loader()
    if dataset.status != "ok":
        return []
    return [text for text, label in dataset.items if label is True]


def _stratified_candidates(rng: random.Random) -> list[tuple[str, str]]:
    """Deterministic interleave of ``(dataset_name, text)`` across seed sources.

    Each source pool is shuffled with the seeded RNG, then the sources are
    round-robin interleaved so the candidate order is balanced across direct
    (deepset) and indirect (injecagent) styles before the oracle filter runs.
    """
    shuffled: dict[str, list[str]] = {}
    for name in config.SEED_SOURCE_DATASETS:
        pool = _malicious_pool(name)
        rng.shuffle(pool)
        shuffled[name] = pool
    out: list[tuple[str, str]] = []
    i = 0
    while any(i < len(p) for p in shuffled.values()):
        for name in config.SEED_SOURCE_DATASETS:
            if i < len(shuffled[name]):
                out.append((name, shuffled[name][i]))
        i += 1
    return out


def pick_seeds(target: int, oracle, max_probe: int | None = None) -> list[Seed]:
    """Return up to ``target`` seeds the ``oracle`` system flags True.

    ``oracle`` exposes ``predict(text) -> bool`` (e.g. ``AegisStages13`` or an
    ``AegisStages14``). ``max_probe`` caps how many candidates are queried (cost
    guard for the paid Stage-4 target); ``None`` means "scan until ``target`` are
    found or the pool is exhausted" — safe for the free deterministic Stage 3.

    Determinism: candidate order is a seeded stratified shuffle, and the oracle is
    queried in that fixed order, so the same seeds come back across re-runs.
    """
    rng = random.Random(config.SEED)
    candidates = _stratified_candidates(rng)

    # Balance the eventual selection across sources by tracking per-source quotas,
    # but fall back to whatever the oracle catches if a source runs thin.
    quotas = dict(zip(
        config.SEED_SOURCE_DATASETS,
        _even_split(target, len(config.SEED_SOURCE_DATASETS)),
    ))
    picked: list[Seed] = []
    per_source: dict[str, int] = {n: 0 for n in config.SEED_SOURCE_DATASETS}
    probes = 0
    for name, text in candidates:
        if len(picked) >= target:
            break
        if max_probe is not None and probes >= max_probe:
            break
        # Honour the per-source quota on the first pass; a later top-up pass would
        # over-query the paid oracle, so instead allow overflow once the *other*
        # source is exhausted (tracked implicitly: we just stop at ``target``).
        if per_source[name] >= quotas[name] and len(picked) < target:
            # Only skip if some other source still has quota headroom available.
            if any(per_source[o] < quotas[o] for o in config.SEED_SOURCE_DATASETS if o != name):
                continue
        probes += 1
        try:
            flagged = oracle.predict(text)
        except Exception:  # noqa: BLE001 — a flaky probe call just skips this candidate
            continue
        if flagged:
            picked.append(Seed(seed_id=f"{name}#{len(picked)}", source_dataset=name,
                               orig_index=len(picked), orig_text=text))
            per_source[name] += 1
    return picked[:target]
