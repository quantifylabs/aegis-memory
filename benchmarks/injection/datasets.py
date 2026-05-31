"""Dataset loaders for the injection benchmark.

Each loader returns a :class:`Dataset` with items of ``(text, label)`` where
``label is True`` means *injection / malicious*. Loaders pin a dataset
revision, record the exact count, and degrade gracefully: if a source is
unreachable, the loader returns a ``Dataset`` with ``status="not_run"`` and the
benchmark continues (it never fails the whole run).

Datasets
--------
- ``deepset``         deepset/prompt-injections (HF) — direct injection, labeled.
- ``injecagent``      InjecAgent (GitHub) — indirect injection, 250 sampled.
- ``benign_public``   databricks-dolly-15k (HF) — 750 sampled, for FPR.
- ``benign_synth``    templated memory-like entries — 750, for FPR.
"""

from __future__ import annotations

import json
import random
import urllib.request
from dataclasses import dataclass, field

SEED = 42

# --- Pinned sources -------------------------------------------------------
DEEPSET_REPO = "deepset/prompt-injections"
DEEPSET_REVISION = "main"  # resolved to a commit sha at load time and recorded

DOLLY_REPO = "databricks/databricks-dolly-15k"
DOLLY_REVISION = "main"  # resolved to a commit sha at load time and recorded

# InjecAgent test cases (indirect prompt injection in tool-using agents).
INJECAGENT_REPO = "uiuc-kang-lab/InjecAgent"
INJECAGENT_REF = "main"  # resolved to a commit sha at load time and recorded
INJECAGENT_FILES = [
    "data/test_cases_dh_base.json",  # direct-harm attacks
    "data/test_cases_ds_base.json",  # data-stealing attacks
]

BENIGN_PUBLIC_N = 750
BENIGN_SYNTH_N = 750
INJECAGENT_N = 250

MIN_LEN, MAX_LEN = 20, 500  # memory-like snippet length window


@dataclass
class Dataset:
    name: str
    kind: str  # "malicious_direct" | "malicious_indirect" | "benign"
    items: list[tuple[str, bool]] = field(default_factory=list)
    revision: str = ""
    source: str = ""
    notes: str = ""
    status: str = "ok"  # "ok" | "not_run"
    error: str | None = None

    @property
    def n(self) -> int:
        return len(self.items)

    @property
    def n_pos(self) -> int:
        return sum(1 for _, y in self.items if y)

    @property
    def n_neg(self) -> int:
        return sum(1 for _, y in self.items if not y)


def _not_run(name: str, kind: str, source: str, err: Exception | str) -> Dataset:
    return Dataset(name=name, kind=kind, source=source, status="not_run", error=str(err))


def _resolve_hf_revision(repo_id: str, revision: str) -> str:
    """Resolve a HF dataset ref to an immutable commit sha (best-effort)."""
    try:
        from huggingface_hub import HfApi

        info = HfApi().dataset_info(repo_id, revision=revision)
        return info.sha or revision
    except Exception:
        return revision


# --------------------------------------------------------------------------
# Malicious — direct: deepset/prompt-injections
# --------------------------------------------------------------------------
def load_deepset(limit: int | None = None) -> Dataset:
    name, kind = "deepset", "malicious_direct"
    source = f"hf:{DEEPSET_REPO}"
    try:
        from datasets import load_dataset

        resolved = _resolve_hf_revision(DEEPSET_REPO, DEEPSET_REVISION)
        # Fetch from the resolved immutable commit so the download matches the
        # revision recorded in results.json (not the moving branch ref).
        ds = load_dataset(DEEPSET_REPO, revision=resolved)
        rows: list[tuple[str, bool]] = []
        for split in ds:  # combine all splits (train + test)
            for row in ds[split]:
                text = (row.get("text") or "").strip()
                if not text:
                    continue
                rows.append((text, int(row["label"]) == 1))
        if limit is not None and limit < len(rows):
            rng = random.Random(SEED)
            rows = rng.sample(rows, limit)
        return Dataset(
            name=name, kind=kind, items=rows, revision=resolved, source=source,
            notes="label 1=injection, 0=legitimate; all splits combined.",
        )
    except Exception as e:  # noqa: BLE001 — graceful skip is the contract
        return _not_run(name, kind, source, e)


# --------------------------------------------------------------------------
# Malicious — indirect: InjecAgent (best-effort GitHub fetch)
# --------------------------------------------------------------------------
def _github_ref_sha(repo: str, ref: str) -> str | None:
    """Resolve a git ref (branch/tag/SHA) to an immutable commit SHA."""
    try:
        url = f"https://api.github.com/repos/{repo}/commits/{ref}"
        req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode()).get("sha")
    except Exception:
        return None


def load_injecagent(limit: int | None = None) -> Dataset:
    name, kind = "injecagent", "malicious_indirect"
    source = f"github:{INJECAGENT_REPO}"
    n_target = limit if limit is not None else INJECAGENT_N
    try:
        # Resolve the ref to ONE immutable commit SHA and fetch BOTH files from
        # it, so every download is pinned and matches the recorded revision
        # (the old code fetched from the moving ref but recorded only one SHA).
        resolved = _github_ref_sha(INJECAGENT_REPO, INJECAGENT_REF)
        if not resolved:
            raise RuntimeError(
                f"could not resolve {INJECAGENT_REPO}@{INJECAGENT_REF} to a commit SHA"
            )
        cases: list[str] = []
        for path in INJECAGENT_FILES:
            raw_url = f"https://raw.githubusercontent.com/{INJECAGENT_REPO}/{resolved}/{path}"
            with urllib.request.urlopen(raw_url, timeout=30) as r:
                payload = json.loads(r.read().decode())
            for case in payload:
                # Build the indirect-injection *content* a tool would return and
                # that Aegis would scan before writing to memory: the attacker
                # instruction embedded in the (templated) tool response.
                attacker = (case.get("Attacker Instruction") or "").strip()
                tool_resp = (case.get("Tool Response Template") or "").strip()
                text = (tool_resp.replace("<Attacker Instruction>", attacker).strip()
                        or attacker)
                if text:
                    cases.append(text)
        if not cases:
            raise ValueError("InjecAgent fetch returned no parseable cases")
        rng = random.Random(SEED)
        if n_target < len(cases):
            cases = rng.sample(cases, n_target)
        items = [(t, True) for t in cases]
        return Dataset(
            name=name, kind=kind, items=items, revision=resolved, source=source,
            notes=(f"{INJECAGENT_N} sampled (seed={SEED}) from "
                   f"{', '.join(INJECAGENT_FILES)}; all malicious (indirect)."),
        )
    except Exception as e:  # noqa: BLE001
        return _not_run(name, kind, source, e)


# --------------------------------------------------------------------------
# Benign — public: databricks-dolly-15k
# --------------------------------------------------------------------------
def load_benign_public(limit: int | None = None) -> Dataset:
    name, kind = "benign_public", "benign"
    source = f"hf:{DOLLY_REPO}"
    n_target = limit if limit is not None else BENIGN_PUBLIC_N
    try:
        from datasets import load_dataset

        resolved = _resolve_hf_revision(DOLLY_REPO, DOLLY_REVISION)
        # Fetch from the resolved immutable commit so the download matches the
        # revision recorded in results.json (not the moving branch ref).
        ds = load_dataset(DOLLY_REPO, revision=resolved, split="train")
        pool: list[str] = []
        for row in ds:
            # Prefer 'context' (passage-like, memory-ish), else 'response'.
            for field_name in ("context", "response"):
                text = (row.get(field_name) or "").strip()
                if MIN_LEN <= len(text) <= MAX_LEN:
                    pool.append(text)
                    break
        rng = random.Random(SEED)
        rng.shuffle(pool)
        chosen = pool[:n_target]
        items = [(t, False) for t in chosen]
        return Dataset(
            name=name, kind=kind, items=items, revision=resolved, source=source,
            notes=(f"{BENIGN_PUBLIC_N} sampled (seed={SEED}) from dolly "
                   f"context/response, length {MIN_LEN}-{MAX_LEN} chars; all benign."),
        )
    except Exception as e:  # noqa: BLE001
        return _not_run(name, kind, source, e)


# --------------------------------------------------------------------------
# Benign — synthetic: templated memory-like entries
# --------------------------------------------------------------------------
_SYNTH_TEMPLATES = [
    "User prefers {a} over {b} for {ctx}.",
    "Meeting notes: discussed {topic}; next step is to {action} by {when}.",
    "The customer's account was created on {date} under the {tier} plan.",
    "Reminder: {person} asked to follow up about {topic} next {when}.",
    "Project {proj} is currently {status}; owner is {person}.",
    "Decision: we will use {a} for {ctx} because it is {reason}.",
    "{person} reported that the {topic} issue was resolved after {action}.",
    "Preference: send weekly summaries on {when} in {a} format.",
    "Fact: the {proj} dashboard refreshes every {n} minutes.",
    "Context: {person} is based in {place} and works on {topic}.",
    "Summary of {date} standup: {topic} on track, {proj} needs {action}.",
    "Note: the onboarding doc for {proj} lives in the {place} workspace.",
]
_SLOTS = {
    "a": ["email", "Slack", "dark mode", "Postgres", "JSON", "Python", "the API"],
    "b": ["phone calls", "Teams", "light mode", "MySQL", "CSV", "Go", "the CLI"],
    "ctx": ["notifications", "storage", "reporting", "deployments", "analytics"],
    "topic": ["billing", "retrieval latency", "the Q3 roadmap", "data export",
              "the migration", "access control", "the new dashboard"],
    "action": ["review the PR", "update the config", "email the team",
               "rerun the pipeline", "schedule a call", "archive old records"],
    "when": ["Monday", "Friday", "next week", "end of month", "tomorrow"],
    "date": ["2024-01-12", "2024-03-04", "2023-11-30", "2024-06-18"],
    "tier": ["free", "pro", "enterprise", "trial"],
    "person": ["Alice", "Bob", "Priya", "Diego", "the on-call engineer", "the PM"],
    "proj": ["Aegis", "Atlas", "Nimbus", "the billing service", "Orion"],
    "status": ["on track", "blocked on review", "in QA", "shipped", "paused"],
    "reason": ["faster", "cheaper", "already supported", "more reliable"],
    "place": ["Berlin", "the EU", "the shared", "Austin", "the internal"],
    "n": ["5", "10", "15", "30", "60"],
}


def load_benign_synth(limit: int | None = None) -> Dataset:
    name, kind = "benign_synth", "benign"
    source = "synthetic:templated_memory_entries"
    n_target = limit if limit is not None else BENIGN_SYNTH_N
    rng = random.Random(SEED)
    seen: set[str] = set()
    items: list[tuple[str, bool]] = []
    attempts = 0
    while len(items) < n_target and attempts < n_target * 50:
        attempts += 1
        tmpl = rng.choice(_SYNTH_TEMPLATES)
        text = tmpl.format(**{k: rng.choice(v) for k, v in _SLOTS.items()})
        if text not in seen:
            seen.add(text)
            items.append((text, False))
    return Dataset(
        name=name, kind=kind, items=items, revision="builtin-v1", source=source,
        notes=(f"{len(items)} templated memory-like entries (seed={SEED}); "
               "all benign. Generator pinned as builtin-v1."),
    )


LOADERS = {
    "deepset": load_deepset,
    "injecagent": load_injecagent,
    "benign_public": load_benign_public,
    "benign_synth": load_benign_synth,
}


def load_all(limit: int | None = None) -> dict[str, Dataset]:
    """Load every dataset. ``limit`` (smoke mode) caps items per dataset."""
    return {name: loader(limit=limit) for name, loader in LOADERS.items()}
