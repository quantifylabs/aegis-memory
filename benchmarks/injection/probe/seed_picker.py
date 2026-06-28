"""Select probe seeds: payloads that Stage 3 currently flags True.

Evasion is only meaningful against a payload Stage 3 already catches — evading
something Stage 3 already misses isn't evasion. The static ``results/results.json``
stores only aggregate confusion counts (no per-item predictions), so we re-predict
the seed-source datasets with ``AegisStages13`` alone (free, deterministic) and
collect the True-flagged items in memory, per the spec's documented fallback.

Seeds are sampled deterministically (``random.Random(SEED)``), stratified across
``SEED_SOURCE_DATASETS`` so both direct (deepset) and indirect (injecagent)
injection styles are represented.
"""

from __future__ import annotations

import random
from dataclasses import asdict, dataclass

from .. import datasets as ds_mod
from .. import systems as sys_mod
from . import config


@dataclass
class Seed:
    seed_id: str               # stable id, e.g. "deepset#41"
    source_dataset: str
    orig_index: int            # index within the True-flagged pool for that dataset
    orig_text: str
    label: bool = True

    def to_dict(self) -> dict:
        return asdict(self)


def _stage3_true_pool(name: str, stage3: sys_mod.AegisStages13) -> list[str]:
    """Texts in dataset ``name`` that are *malicious* AND Stage 3 flags True.

    deepset is a mixed-label set (``label 1=injection, 0=legitimate``), so the
    ``label is True`` guard is load-bearing: without it a Stage-3 false positive
    on a benign row would be paraphrased and counted as an evasion candidate,
    contaminating the experiment. injecagent is all-malicious, so the guard is a
    no-op there. (Evading something on a benign row isn't evasion.)
    """
    loader = ds_mod.LOADERS[name]
    dataset = loader()  # full dataset; Stage-3 prediction is free, so don't subsample here
    if dataset.status != "ok":
        return []
    out: list[str] = []
    for text, label in dataset.items:
        if label is True and stage3.predict(text):
            out.append(text)
    return out


def _even_split(total: int, n_buckets: int) -> list[int]:
    """Distribute ``total`` as evenly as possible across ``n_buckets`` (front-loaded)."""
    base, extra = divmod(total, n_buckets)
    return [base + (1 if i < extra else 0) for i in range(n_buckets)]


def pick_seeds(n_seeds: int | None = None) -> list[Seed]:
    """Return ``n_seeds`` Stage-3-flagged seeds, stratified across source datasets.

    ``n_seeds`` defaults to :data:`config.N_SEEDS`; the ``--limit`` smoke flag
    passes a smaller value. The dataset loaders are NOT subsampled — the full
    sets are scanned so the True-flagged pool is the real one.
    """
    target = config.N_SEEDS if n_seeds is None else n_seeds

    stage3 = sys_mod.AegisStages13()
    stage3.warmup()

    pools = {name: _stage3_true_pool(name, stage3) for name in config.SEED_SOURCE_DATASETS}

    rng = random.Random(config.SEED)
    # Even target split across sources, then redistribute any shortfall from a
    # thin source onto the others so we still reach ``target`` when possible.
    quotas = dict(zip(config.SEED_SOURCE_DATASETS, _even_split(target, len(config.SEED_SOURCE_DATASETS))))
    picked: list[Seed] = []
    leftover_capacity = True
    # Two passes: first honour quotas, then top up from whatever pools have slack.
    for topup in (False, True):
        for name in config.SEED_SOURCE_DATASETS:
            pool = pools.get(name, [])
            already = {s.orig_text for s in picked if s.source_dataset == name}
            available = [t for t in pool if t not in already]
            if not available:
                continue
            if topup:
                want = target - len(picked)
            else:
                want = min(quotas[name], len(available))
            want = max(0, min(want, len(available)))
            if want == 0:
                continue
            chosen = rng.sample(available, want)
            for t in chosen:
                idx = pool.index(t)
                picked.append(Seed(seed_id=f"{name}#{idx}", source_dataset=name,
                                   orig_index=idx, orig_text=t))
            if len(picked) >= target:
                leftover_capacity = False
                break
        if not leftover_capacity:
            break

    return picked[:target]
