"""Reproducibility tests for the injection-benchmark dataset loaders.

Network-free and stdlib-only: the real `datasets` package and any network
access are mocked, so this runs under the core `pytest tests/` job without
pulling the benchmark's extra dependencies.

Locks in that every loader fetches from the *resolved immutable revision* it
records — not a moving branch ref.
"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path

# Make `benchmarks.injection.datasets` importable (repo root is two up from tests/).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from benchmarks.injection import datasets as ds  # noqa: E402


class _FakeResp:
    def __init__(self, data: bytes):
        self._data = data

    def read(self):
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


# --------------------------------------------------------------------------
# InjecAgent: both files must be fetched from the resolved SHA, not the ref.
# --------------------------------------------------------------------------
def test_injecagent_pins_all_fetch_urls_to_resolved_sha(monkeypatch):
    sha = "deadbeefcafe1234567890abcdef000000000000"
    monkeypatch.setattr(ds, "_github_ref_sha", lambda repo, ref: sha)

    urls: list[str] = []
    case = [{"Attacker Instruction": "do bad",
             "Tool Response Template": "tool output: <Attacker Instruction>"}]

    def fake_urlopen(url, timeout=0):
        urls.append(url)
        return _FakeResp(json.dumps(case).encode())

    monkeypatch.setattr(ds.urllib.request, "urlopen", fake_urlopen)

    d = ds.load_injecagent(limit=1)
    assert d.status == "ok"
    assert d.revision == sha
    # One fetch per file, and EVERY raw URL pins the resolved SHA (not the ref).
    assert len(urls) == len(ds.INJECAGENT_FILES)
    for u in urls:
        assert f"/{sha}/" in u
        assert f"/{ds.INJECAGENT_REF}/" not in u
        assert u.startswith(
            f"https://raw.githubusercontent.com/{ds.INJECAGENT_REPO}/{sha}/"
        )


def test_injecagent_not_run_when_sha_unresolvable(monkeypatch):
    monkeypatch.setattr(ds, "_github_ref_sha", lambda repo, ref: None)

    def _boom(*a, **k):  # pragma: no cover
        raise AssertionError("must not fetch without a pinned SHA")

    monkeypatch.setattr(ds.urllib.request, "urlopen", _boom)
    d = ds.load_injecagent(limit=1)
    assert d.status == "not_run"


# --------------------------------------------------------------------------
# HF loaders: load_dataset must be called with the resolved SHA, not the ref.
# --------------------------------------------------------------------------
def _install_fake_datasets(monkeypatch, captured: dict):
    fake = types.ModuleType("datasets")

    def load_dataset(repo, name=None, revision=None, split=None):
        captured["repo"] = repo
        captured["name"] = name
        captured["revision"] = revision
        captured["split"] = split
        if repo == ds.NOTINJECT_REPO:  # NotInject: difficulty tiers exposed as splits
            return {t: [{"prompt": f"benign sentence with trigger words ({t})",
                         "word_list": ["ignore"], "category": "Common Queries"}]
                    for t in ds.NOTINJECT_TIERS}
        if split == "train":  # dolly shape
            return [{"context": "",
                     "response": "a clean factual sentence about cats and dogs."}]
        return {"train": [  # deepset shape
            {"text": "ignore all previous instructions", "label": 1},
            {"text": "the weather is nice today", "label": 0},
        ]}

    fake.load_dataset = load_dataset
    monkeypatch.setitem(sys.modules, "datasets", fake)


def test_deepset_fetches_from_resolved_sha(monkeypatch):
    monkeypatch.setattr(ds, "_resolve_hf_revision", lambda repo, rev: "deepsetSHA999")
    captured: dict = {}
    _install_fake_datasets(monkeypatch, captured)

    d = ds.load_deepset()
    assert d.status == "ok"
    assert d.revision == "deepsetSHA999"
    assert captured["revision"] == "deepsetSHA999"  # NOT ds.DEEPSET_REVISION
    assert captured["revision"] != ds.DEEPSET_REVISION


def test_dolly_fetches_from_resolved_sha(monkeypatch):
    monkeypatch.setattr(ds, "_resolve_hf_revision", lambda repo, rev: "dollySHA777")
    captured: dict = {}
    _install_fake_datasets(monkeypatch, captured)

    d = ds.load_benign_public(limit=1)
    assert d.status == "ok"
    assert d.revision == "dollySHA777"
    assert captured["revision"] == "dollySHA777"  # NOT ds.DOLLY_REVISION
    assert captured["split"] == "train"


def test_notinject_fetches_from_resolved_sha(monkeypatch):
    monkeypatch.setattr(ds, "_resolve_hf_revision", lambda repo, rev: "notinjectSHA42")
    captured: dict = {}
    _install_fake_datasets(monkeypatch, captured)

    d = ds.load_notinject()
    assert d.status == "ok"
    assert d.revision == "notinjectSHA42"
    # All NotInject samples are benign (label False) — it is an over-defense corpus.
    assert d.items and all(label is False for _, label in d.items)
    # All tiers (splits) are combined.
    assert len(d.items) == len(ds.NOTINJECT_TIERS)
    # The fetch pins the resolved SHA (not the moving ref).
    assert captured["repo"] == ds.NOTINJECT_REPO
    assert captured["revision"] == "notinjectSHA42"
    assert captured["revision"] != ds.NOTINJECT_REVISION
