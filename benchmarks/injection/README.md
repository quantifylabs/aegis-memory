# Aegis injection-detection benchmark

A reproducible, **honest** benchmark that evaluates the Aegis four-stage content-security
pipeline (`server/content_security.py`) as a prompt-injection / memory-poisoning **detector**,
against established baselines, with full confusion-matrix metrics and a per-stage ablation.

This measures Aegis in its actual threat model: **detecting injection/poisoning in content being
written to memory**. It is *not* an LLM-jailbreak-defense benchmark. The headline numbers,
ablation, latency comparison, and limitations live in
[`docs/security/benchmark.md`](../../docs/security/benchmark.md).

## What it measures

Every system is wrapped as `predict(text) -> bool` and scored on **both** malicious and benign
corpora, reported as a full confusion matrix → **precision, recall, F1, FPR, accuracy**, plus
**median per-item latency** and **bootstrapped 95% CIs** (n=1000, seed=42).

**Systems:** `no_protection`, `naive_regex`, `protectai_deberta`, `llama_prompt_guard_2`,
`llm_guard`, `llm_judge_openai`, `llm_judge_anthropic`, `aegis_stages_1_3`,
`aegis_stages_1_4_openai`, `aegis_stages_1_4_anthropic`.

**Datasets:** `deepset/prompt-injections` (direct), `InjecAgent` (indirect, 250 sampled),
`benign_public` (dolly, 750), `benign_synth` (750 templated memory entries),
`notinject` (NotInject, 339 benign sentences seeded with injection trigger words —
over-defense FPR stress test).

## Setup

```bash
# from the repo root (aegis-memory-main/)
python -m venv .venv-bench && source .venv-bench/bin/activate   # Windows: .venv-bench\Scripts\Activate.ps1
pip install -r benchmarks/injection/requirements.txt
```

`torch`/`transformers` are large (CPU wheels, a few minutes). If `llm-guard` cannot co-resolve
with the pinned `transformers`/`torch`, install it in a separate venv or skip it — the benchmark
marks `llm_guard` as `not_run` and proceeds.

### API keys

`llm_judge_*` and Aegis `aegis_stages_1_4_*` call paid APIs. Keys are read from the environment
or `aegis-memory-main/.env` **only** (never hardcoded):

```
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
```

If a key is absent, that system is reported `not_run` (the run continues). Responses are cached
under `cache/` keyed by `(system_id, model_id, sha256(prompt))`, so **re-runs never re-bill**.

### Gated model: `llama_prompt_guard_2`

`llama_prompt_guard_2` uses Meta's gated [`meta-llama/Llama-Prompt-Guard-2-86M`](https://huggingface.co/meta-llama/Llama-Prompt-Guard-2-86M).
To run it you must **accept the model license** on HuggingFace and set `HF_TOKEN` (or
`HUGGING_FACE_HUB_TOKEN`) in the environment / `.env`. Without an accepted license or token, the
system is reported `not_run` and the benchmark proceeds. It runs locally on CPU (no API cost).

## Run

```bash
# Smoke test (20 items/dataset) — validates wiring end to end:
python benchmarks/injection/run_benchmark.py --limit 20

# Full run:
python benchmarks/injection/run_benchmark.py

# Subsets:
python benchmarks/injection/run_benchmark.py --systems aegis_stages_1_3,naive_regex
python benchmarks/injection/run_benchmark.py --datasets deepset,benign_synth
```

### Expected runtime (CPU-only laptop, full corpora)

| Stage | Cost |
|---|---|
| `no_protection`, `naive_regex`, `aegis_stages_1_3` | seconds (deterministic) |
| `protectai_deberta`, `llm_guard` | a few minutes (CPU inference) |
| `llm_judge_*`, `aegis_stages_1_4_*` | API-bound; ~$1–2 total once, then cache-served |

## Outputs

- `results/results.json` — full machine-readable results: every system × dataset, confusion
  matrices, P/R/F1/FPR/accuracy, latencies, bootstrap CIs, the Aegis stage ablation, dataset
  revisions, model versions, seed, timestamp, cache stats.
- `results/error_analysis.md` — false negatives (missed injections, categorized) + a sample of
  false positives (benign flagged).
- `cache/` — LLM response cache (git-ignored).

## Files

| File | Purpose |
|---|---|
| `datasets.py` | 5 dataset loaders, pinned revisions, graceful missing-source handling |
| `systems.py` | `predict(text)->bool` adapters, response cache, per-stage attribution |
| `metrics.py` | confusion matrix, P/R/F1/FPR/accuracy, bootstrap CIs, stage ablation |
| `run_benchmark.py` | orchestrator: loads `.env`, runs systems × datasets, writes results |
| `_paths.py` | puts `server/` + repo root on `sys.path` (mirrors `tests/conftest.py`) |

## Reproducibility notes

- All subsampling uses **seed 42**; exact counts and resolved dataset revisions are recorded in
  `results.json`.
- `aegis_stages_1_4_*` forces Stage 4 on every item via `trust_level="untrusted"` so the ablation
  can measure Stage 4's standalone contribution. **Production gates Stage 4 conditionally** — this
  is a measurement choice, stated in `results.json["meta"]` and the writeup.
- Detection logic is **never reimplemented**: Aegis systems call the real
  `ContentSecurityScanner.scan` / `.scan_async` from `server/content_security.py`.
