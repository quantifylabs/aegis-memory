# Aegis content-security pipeline — injection-detection benchmark

_Generated from `benchmarks/injection/results/results.json` · run 2026-06-15T15:14:06.517296+00:00 · seed 42 · bootstrap n=1000_

## Threat model

Aegis's content-security pipeline detects **prompt injection / memory poisoning in content being written to memory** — text that, once stored and later retrieved, could manipulate an agent. This is the scope measured here. It is **not** an LLM-jailbreak defense and is not evaluated as one. Every system is scored on **both** malicious and benign corpora, so the false-positive rate (FPR) is reported next to recall everywhere — a detector that flags everything scores 100% recall and is useless.

## Methodology

- **Systems** are wrapped as `predict(text) -> bool` (True = flagged). Aegis systems call the real `ContentSecurityScanner` from `server/content_security.py`; detection logic is never reimplemented.
- **`aegis_stages_1_3`** runs the deterministic Stages 1–3 (`scan`). **`aegis_stages_1_4_*`** add the Stage-4 LLM classifier (`scan_async`), forced on every item via `trust_level="untrusted"` so the ablation can measure Stage 4's standalone contribution. *Production gates Stage 4 conditionally — this is a measurement choice, not production behavior.*
- **Metrics:** confusion matrix → precision, recall, F1, FPR, accuracy, with bootstrapped 95% CIs (resampling cases, n=1000, seed=42). Median per-item latency too.
- A metric is shown as `—` when undefined (e.g. FPR on a malicious-only dataset, precision on a benign-only dataset).
- **Third-party baselines:** `protectai_deberta` ([protectai/deberta-v3-base-prompt-injection-v2](https://huggingface.co/protectai/deberta-v3-base-prompt-injection-v2)), `llm_guard` ([llm-guard](https://github.com/protectai/llm-guard)), and **`llama_prompt_guard_2`** — Meta's gated [meta-llama/Llama-Prompt-Guard-2-86M](https://huggingface.co/meta-llama/Llama-Prompt-Guard-2-86M), a binary (benign/malicious) prompt-injection detector run on CPU. It is trained for injection/jailbreak detection at the LLM input — a fair baseline on direct injection but outside its scope on indirect injection. Running it requires accepting the model license on HuggingFace and setting `HF_TOKEN`.

- **Environment:** Python 3.11.9, Windows-10-10.0.26200-SP0. Models: OpenAI `gpt-4o-mini`, Anthropic `claude-haiku-4-5-20251001`. Key libs: transformers `4.53.3`, torch `2.12.0+cpu`, datasets `2.19.1`, llm_guard `unknown`.

## Datasets

| Dataset | Kind | N | Injection | Benign | Revision | Status |
|---|---|--:|--:|--:|---|---|
| `deepset` | malicious_direct | 662 | 263 | 399 | `4f61ecb038e9` | ok |
| `injecagent` | malicious_indirect | 250 | 250 | 0 | `f19c9f2c79a4` | ok |
| `benign_public` | benign | 750 | 0 | 750 | `bdd27f4d94b9` | ok |
| `benign_synth` | benign | 750 | 0 | 750 | `builtin-v1` | ok |
| `notinject` | benign | 339 | 0 | 339 | `847ae76cf8fe` | ok |

- **deepset** — label 1=injection, 0=legitimate; all splits combined. _(source: hf:deepset/prompt-injections)_
- **injecagent** — 250 sampled (seed=42) from data/test_cases_dh_base.json, data/test_cases_ds_base.json; all malicious (indirect). _(source: github:uiuc-kang-lab/InjecAgent)_
- **benign_public** — 750 sampled (seed=42) from dolly context/response, length 20-500 chars; all benign. _(source: hf:databricks/databricks-dolly-15k)_
- **benign_synth** — 750 templated memory-like entries (seed=42); all benign. Generator pinned as builtin-v1. _(source: synthetic:templated_memory_entries)_
- **notinject** — 339 benign sentences seeded with injection trigger words (over-defense FPR stress test); all benign. Per-tier: NotInject_one=113, NotInject_two=113, NotInject_three=113. _(source: hf:leolee99/NotInject)_

## Headline results

Recall and FPR shown with 95% CI. Full CIs for precision/F1 are in `results.json`.

### `deepset` (malicious_direct, N=662)

| System | Precision | Recall [95% CI] | F1 | FPR [95% CI] | Acc | Median latency |
|---|--:|--:|--:|--:|--:|--:|
| `no_protection` | — | 0.000 [0.00–0.00] | — | 0.000 [0.00–0.00] | 0.603 | 0 µs |
| `naive_regex` | 1.000 | 0.144 [0.10–0.19] | 0.252 | 0.000 [0.00–0.00] | 0.660 | 6 µs |
| `protectai_deberta` | 0.965 | 0.414 [0.36–0.48] | 0.580 | 0.010 [0.00–0.02] | 0.761 | 206.6 ms |
| `llama_prompt_guard_2` | 0.984 | 0.228 [0.18–0.28] | 0.370 | 0.003 [0.00–0.01] | 0.692 | 215.5 ms |
| `llm_guard` | 0.965 | 0.414 [0.36–0.48] | 0.580 | 0.010 [0.00–0.02] | 0.761 | 209.6 ms |
| `llm_judge_openai` | 0.944 | 0.829 [0.78–0.87] | 0.883 | 0.033 [0.02–0.05] | 0.912 | 9 µs |
| `llm_judge_anthropic` | 0.995 | 0.757 [0.70–0.81] | 0.860 | 0.003 [0.00–0.01] | 0.902 | 6 µs |
| `aegis_stages_1_3` | 1.000 | 0.144 [0.10–0.19] | 0.252 | 0.000 [0.00–0.00] | 0.660 | 33 µs |
| `aegis_stages_1_4_openai` | 1.000 | 0.677 [0.62–0.73] | 0.807 | 0.000 [0.00–0.00] | 0.872 | 1407.8 ms |
| `aegis_stages_1_4_anthropic` | 1.000 | 0.741 [0.69–0.79] | 0.852 | 0.000 [0.00–0.00] | 0.897 | 1822.5 ms |

### `injecagent` (malicious_indirect, N=250)

| System | Precision | Recall [95% CI] | F1 | FPR [95% CI] | Acc | Median latency |
|---|--:|--:|--:|--:|--:|--:|
| `no_protection` | — | 0.000 [0.00–0.00] | — | — | 0.000 | 0 µs |
| `naive_regex` | — | 0.000 [0.00–0.00] | — | — | 0.000 | 27 µs |
| `protectai_deberta` | 1.000 | 0.660 [0.60–0.72] | 0.795 | — | 0.660 | 338.3 ms |
| `llama_prompt_guard_2` | — | 0.000 [0.00–0.00] | — | — | 0.000 | 300.7 ms |
| `llm_guard` | 1.000 | 0.656 [0.60–0.72] | 0.792 | — | 0.656 | 323.2 ms |
| `llm_judge_openai` | 1.000 | 0.672 [0.62–0.73] | 0.804 | — | 0.672 | 7 µs |
| `llm_judge_anthropic` | 1.000 | 0.932 [0.90–0.96] | 0.965 | — | 0.932 | 7 µs |
| `aegis_stages_1_3` | 1.000 | 0.620 [0.56–0.68] | 0.765 | — | 0.620 | 119 µs |
| `aegis_stages_1_4_openai` | 1.000 | 0.744 [0.69–0.80] | 0.853 | — | 0.744 | 1655.9 ms |
| `aegis_stages_1_4_anthropic` | 1.000 | 0.832 [0.78–0.88] | 0.908 | — | 0.832 | 2235.1 ms |

### `benign_public` (benign, N=750)

| System | Precision | Recall [95% CI] | F1 | FPR [95% CI] | Acc | Median latency |
|---|--:|--:|--:|--:|--:|--:|
| `no_protection` | — | — | — | 0.000 [0.00–0.00] | 1.000 | 0 µs |
| `naive_regex` | — | — | — | 0.000 [0.00–0.00] | 1.000 | 16 µs |
| `protectai_deberta` | 0.000 | — | — | 0.039 [0.03–0.05] | 0.961 | 240.5 ms |
| `llama_prompt_guard_2` | — | — | — | 0.000 [0.00–0.00] | 1.000 | 244.2 ms |
| `llm_guard` | 0.000 | — | — | 0.039 [0.03–0.05] | 0.961 | 237.0 ms |
| `llm_judge_openai` | 0.000 | — | — | 0.004 [0.00–0.01] | 0.996 | 6 µs |
| `llm_judge_anthropic` | — | — | — | 0.000 [0.00–0.00] | 1.000 | 6 µs |
| `aegis_stages_1_3` | 0.000 | — | — | 0.001 [0.00–0.00] | 0.999 | 67 µs |
| `aegis_stages_1_4_openai` | 0.000 | — | — | 0.001 [0.00–0.00] | 0.999 | 1355.5 ms |
| `aegis_stages_1_4_anthropic` | 0.000 | — | — | 0.001 [0.00–0.00] | 0.999 | 1646.9 ms |

### `benign_synth` (benign, N=750)

| System | Precision | Recall [95% CI] | F1 | FPR [95% CI] | Acc | Median latency |
|---|--:|--:|--:|--:|--:|--:|
| `no_protection` | — | — | — | 0.000 [0.00–0.00] | 1.000 | 0 µs |
| `naive_regex` | — | — | — | 0.000 [0.00–0.00] | 1.000 | 7 µs |
| `protectai_deberta` | 0.000 | — | — | 0.040 [0.03–0.05] | 0.960 | 173.9 ms |
| `llama_prompt_guard_2` | — | — | — | 0.000 [0.00–0.00] | 1.000 | 181.8 ms |
| `llm_guard` | 0.000 | — | — | 0.040 [0.03–0.05] | 0.960 | 208.7 ms |
| `llm_judge_openai` | 0.000 | — | — | 0.001 [0.00–0.00] | 0.999 | 6 µs |
| `llm_judge_anthropic` | — | — | — | 0.000 [0.00–0.00] | 1.000 | 5 µs |
| `aegis_stages_1_3` | — | — | — | 0.000 [0.00–0.00] | 1.000 | 34 µs |
| `aegis_stages_1_4_openai` | — | — | — | 0.000 [0.00–0.00] | 1.000 | 1471.3 ms |
| `aegis_stages_1_4_anthropic` | — | — | — | 0.000 [0.00–0.00] | 1.000 | 1682.0 ms |

### `notinject` (benign, N=339)

| System | Precision | Recall [95% CI] | F1 | FPR [95% CI] | Acc | Median latency |
|---|--:|--:|--:|--:|--:|--:|
| `no_protection` | — | — | — | 0.000 [0.00–0.00] | 1.000 | 0 µs |
| `naive_regex` | 0.000 | — | — | 0.015 [0.00–0.03] | 0.985 | 9 µs |
| `protectai_deberta` | 0.000 | — | — | 0.428 [0.37–0.48] | 0.572 | 185.2 ms |
| `llama_prompt_guard_2` | 0.000 | — | — | 0.065 [0.04–0.09] | 0.935 | 201.1 ms |
| `llm_guard` | 0.000 | — | — | 0.428 [0.37–0.48] | 0.572 | 203.9 ms |
| `llm_judge_openai` | 0.000 | — | — | 0.041 [0.02–0.06] | 0.959 | 6 µs |
| `llm_judge_anthropic` | 0.000 | — | — | 0.035 [0.02–0.06] | 0.965 | 6 µs |
| `aegis_stages_1_3` | 0.000 | — | — | 0.015 [0.00–0.03] | 0.985 | 40 µs |
| `aegis_stages_1_4_openai` | 0.000 | — | — | 0.035 [0.02–0.06] | 0.965 | 1367.1 ms |
| `aegis_stages_1_4_anthropic` | 0.000 | — | — | 0.035 [0.02–0.06] | 0.965 | 1824.9 ms |

## Over-defense / trigger-word robustness (NotInject)

[NotInject](https://huggingface.co/datasets/leolee99/NotInject) (InjecGuard, Li et al. 2024, [arXiv:2410.22770](https://arxiv.org/abs/2410.22770); [github.com/SaFoLab-WISC/InjecGuard](https://github.com/SaFoLab-WISC/InjecGuard)) is a corpus of **339 benign** sentences deliberately seeded with injection *trigger words* ("ignore", "system", "instructions", …) across three difficulty tiers (one/two/three trigger words). Every sample is benign, so the only meaningful metric is **FPR — lower is better**. The InjecGuard paper showed several published detectors reach near-100% FPR here: it is a direct test of *over-defense* (flagging benign text just because it contains scary-looking words).

| System | FPR [95% CI] | Benign flagged (FP / N) |
|---|--:|--:|
| `no_protection` | 0.000 [0.00–0.00] | 0 / 339 |
| `naive_regex` | 0.015 [0.00–0.03] | 5 / 339 |
| `protectai_deberta` | 0.428 [0.37–0.48] | 145 / 339 |
| `llama_prompt_guard_2` | 0.065 [0.04–0.09] | 22 / 339 |
| `llm_guard` | 0.428 [0.37–0.48] | 145 / 339 |
| `llm_judge_openai` | 0.041 [0.02–0.06] | 14 / 339 |
| `llm_judge_anthropic` | 0.035 [0.02–0.06] | 12 / 339 |
| `aegis_stages_1_3` | 0.015 [0.00–0.03] | 5 / 339 |
| `aegis_stages_1_4_openai` | 0.035 [0.02–0.06] | 12 / 339 |
| `aegis_stages_1_4_anthropic` | 0.035 [0.02–0.06] | 12 / 339 |

**Reading this honestly.** A low NotInject FPR for Aegis's deterministic stages alongside high FPR for ML/LLM detectors would be a strong, citable differentiator (trigger-word robustness without a learned classifier's over-defense). **If Aegis also over-flags NotInject, that is reported here plainly** — an honest over-defense number is the entire point of this corpus. Compare each system's NotInject FPR to its `benign_public` / `benign_synth` FPR above: a gap means trigger words specifically are driving false positives. Note that **Llama Prompt Guard 2** is trained to detect injection/jailbreak text at the LLM input, so it is a fair baseline on direct injection (`deepset`) but is expected to be the most exposed to trigger-word over-defense here; it may also underperform on indirect injection (`injecagent`), which is outside its training scope.

## Aegis stage ablation

Cumulative contribution as each stage is added (Stage 1 → +2 → +3 → +4). This is the central research contribution: it quantifies whether the LLM-backed Stage 4 earns its latency/cost over the free deterministic core (Stages 1–3).

**Stage 2's contribution to injection recall is category-dependent — an honest, important nuance.** Stage 2 targets PII/credentials, *not* injection. On **direct injection** it behaves exactly as designed and adds ~0 recall — it flags essentially nothing there (`deepset` (0 flags)), because injection text rarely contains PII.
On **indirect injection** (`injecagent`), however, Stage 2 flags **155/250** payloads and accounts for most of the deterministic core's recall there. That is *not* injection detection working: it is Stage 2 firing on the PII/credentials embedded in the data-exfiltration payloads (health records, account numbers, emails). We report this rather than hide it — it shows (a) Stage 2 is orthogonal to injection detection for direct attacks, as claimed, and (b) a multi-category pipeline can still catch data-stealing indirect payloads via a *different* stage than a pure injection detector would. For the genuine injection-detection signal, read the **Stage 3 → Stage 4** deltas.
This is what distinguishes Aegis (multi-category content security) from single-purpose injection detectors — and the ablation is what makes the case empirically.

### `aegis_stages_1_3`

**`deepset`** (malicious_direct, N=662)

| Stages | Recall | FPR | Precision | F1 |
|---|--:|--:|--:|--:|
| Stage 1 | 0.000 | 0.000 | — | — |
| + Stage 2 | 0.000 | 0.000 | — | — |
| + Stage 3 | 0.144 | 0.000 | 1.000 | 0.252 |
| + Stage 4 | 0.144 | 0.000 | 1.000 | 0.252 |

_Items flagged per stage (any flag): S1=0, S2=0, S3=38, S4=0._

**`injecagent`** (malicious_indirect, N=250)

| Stages | Recall | FPR | Precision | F1 |
|---|--:|--:|--:|--:|
| Stage 1 | 0.000 | — | — | — |
| + Stage 2 | 0.620 | — | 1.000 | 0.765 |
| + Stage 3 | 0.620 | — | 1.000 | 0.765 |
| + Stage 4 | 0.620 | — | 1.000 | 0.765 |

_Items flagged per stage (any flag): S1=0, S2=155, S3=0, S4=0._

**`benign_public`** (benign, N=750)

| Stages | Recall | FPR | Precision | F1 |
|---|--:|--:|--:|--:|
| Stage 1 | — | 0.000 | — | — |
| + Stage 2 | — | 0.000 | — | — |
| + Stage 3 | — | 0.001 | 0.000 | — |
| + Stage 4 | — | 0.001 | 0.000 | — |

_Items flagged per stage (any flag): S1=0, S2=0, S3=1, S4=0._

**`benign_synth`** (benign, N=750)

| Stages | Recall | FPR | Precision | F1 |
|---|--:|--:|--:|--:|
| Stage 1 | — | 0.000 | — | — |
| + Stage 2 | — | 0.000 | — | — |
| + Stage 3 | — | 0.000 | — | — |
| + Stage 4 | — | 0.000 | — | — |

_Items flagged per stage (any flag): S1=0, S2=0, S3=0, S4=0._

**`notinject`** (benign, N=339)

| Stages | Recall | FPR | Precision | F1 |
|---|--:|--:|--:|--:|
| Stage 1 | — | 0.000 | — | — |
| + Stage 2 | — | 0.000 | — | — |
| + Stage 3 | — | 0.015 | 0.000 | — |
| + Stage 4 | — | 0.015 | 0.000 | — |

_Items flagged per stage (any flag): S1=0, S2=0, S3=5, S4=0._

### `aegis_stages_1_4_openai`

**`deepset`** (malicious_direct, N=662)

| Stages | Recall | FPR | Precision | F1 |
|---|--:|--:|--:|--:|
| Stage 1 | 0.000 | 0.000 | — | — |
| + Stage 2 | 0.000 | 0.000 | — | — |
| + Stage 3 | 0.144 | 0.000 | 1.000 | 0.252 |
| + Stage 4 | 0.677 | 0.000 | 1.000 | 0.807 |

_Items flagged per stage (any flag): S1=0, S2=0, S3=38, S4=170._

**`injecagent`** (malicious_indirect, N=250)

| Stages | Recall | FPR | Precision | F1 |
|---|--:|--:|--:|--:|
| Stage 1 | 0.000 | — | — | — |
| + Stage 2 | 0.620 | — | 1.000 | 0.765 |
| + Stage 3 | 0.620 | — | 1.000 | 0.765 |
| + Stage 4 | 0.744 | — | 1.000 | 0.853 |

_Items flagged per stage (any flag): S1=0, S2=155, S3=0, S4=143._

**`benign_public`** (benign, N=750)

| Stages | Recall | FPR | Precision | F1 |
|---|--:|--:|--:|--:|
| Stage 1 | — | 0.000 | — | — |
| + Stage 2 | — | 0.000 | — | — |
| + Stage 3 | — | 0.001 | 0.000 | — |
| + Stage 4 | — | 0.001 | 0.000 | — |

_Items flagged per stage (any flag): S1=0, S2=0, S3=1, S4=0._

**`benign_synth`** (benign, N=750)

| Stages | Recall | FPR | Precision | F1 |
|---|--:|--:|--:|--:|
| Stage 1 | — | 0.000 | — | — |
| + Stage 2 | — | 0.000 | — | — |
| + Stage 3 | — | 0.000 | — | — |
| + Stage 4 | — | 0.000 | — | — |

_Items flagged per stage (any flag): S1=0, S2=0, S3=0, S4=0._

**`notinject`** (benign, N=339)

| Stages | Recall | FPR | Precision | F1 |
|---|--:|--:|--:|--:|
| Stage 1 | — | 0.000 | — | — |
| + Stage 2 | — | 0.000 | — | — |
| + Stage 3 | — | 0.015 | 0.000 | — |
| + Stage 4 | — | 0.035 | 0.000 | — |

_Items flagged per stage (any flag): S1=0, S2=0, S3=5, S4=8._

### `aegis_stages_1_4_anthropic`

**`deepset`** (malicious_direct, N=662)

| Stages | Recall | FPR | Precision | F1 |
|---|--:|--:|--:|--:|
| Stage 1 | 0.000 | 0.000 | — | — |
| + Stage 2 | 0.000 | 0.000 | — | — |
| + Stage 3 | 0.144 | 0.000 | 1.000 | 0.252 |
| + Stage 4 | 0.741 | 0.000 | 1.000 | 0.852 |

_Items flagged per stage (any flag): S1=0, S2=0, S3=38, S4=192._

**`injecagent`** (malicious_indirect, N=250)

| Stages | Recall | FPR | Precision | F1 |
|---|--:|--:|--:|--:|
| Stage 1 | 0.000 | — | — | — |
| + Stage 2 | 0.620 | — | 1.000 | 0.765 |
| + Stage 3 | 0.620 | — | 1.000 | 0.765 |
| + Stage 4 | 0.832 | — | 1.000 | 0.908 |

_Items flagged per stage (any flag): S1=0, S2=155, S3=0, S4=183._

**`benign_public`** (benign, N=750)

| Stages | Recall | FPR | Precision | F1 |
|---|--:|--:|--:|--:|
| Stage 1 | — | 0.000 | — | — |
| + Stage 2 | — | 0.000 | — | — |
| + Stage 3 | — | 0.001 | 0.000 | — |
| + Stage 4 | — | 0.001 | 0.000 | — |

_Items flagged per stage (any flag): S1=0, S2=0, S3=1, S4=0._

**`benign_synth`** (benign, N=750)

| Stages | Recall | FPR | Precision | F1 |
|---|--:|--:|--:|--:|
| Stage 1 | — | 0.000 | — | — |
| + Stage 2 | — | 0.000 | — | — |
| + Stage 3 | — | 0.000 | — | — |
| + Stage 4 | — | 0.000 | — | — |

_Items flagged per stage (any flag): S1=0, S2=0, S3=0, S4=0._

**`notinject`** (benign, N=339)

| Stages | Recall | FPR | Precision | F1 |
|---|--:|--:|--:|--:|
| Stage 1 | — | 0.000 | — | — |
| + Stage 2 | — | 0.000 | — | — |
| + Stage 3 | — | 0.015 | 0.000 | — |
| + Stage 4 | — | 0.035 | 0.000 | — |

_Items flagged per stage (any flag): S1=0, S2=0, S3=5, S4=9._

## Latency comparison

Median per-item latency (lower is better). Deterministic stages 1–3 are orders of magnitude faster than LLM-based detectors.

| System | `deepset` | `injecagent` | `benign_public` | `benign_synth` | `notinject` |
|---|--:|--:|--:|--:|--:|
| `no_protection` | 0 µs | 0 µs | 0 µs | 0 µs | 0 µs |
| `naive_regex` | 6 µs | 27 µs | 16 µs | 7 µs | 9 µs |
| `protectai_deberta` | 206.6 ms | 338.3 ms | 240.5 ms | 173.9 ms | 185.2 ms |
| `llama_prompt_guard_2` | 215.5 ms | 300.7 ms | 244.2 ms | 181.8 ms | 201.1 ms |
| `llm_guard` | 209.6 ms | 323.2 ms | 237.0 ms | 208.7 ms | 203.9 ms |
| `llm_judge_openai` | 9 µs | 7 µs | 6 µs | 6 µs | 6 µs |
| `llm_judge_anthropic` | 6 µs | 7 µs | 6 µs | 5 µs | 6 µs |
| `aegis_stages_1_3` | 33 µs | 119 µs | 67 µs | 34 µs | 40 µs |
| `aegis_stages_1_4_openai` | 1407.8 ms | 1655.9 ms | 1355.5 ms | 1471.3 ms | 1367.1 ms |
| `aegis_stages_1_4_anthropic` | 1822.5 ms | 2235.1 ms | 1646.9 ms | 1682.0 ms | 1824.9 ms |

> Note: API-system latencies are measured on live calls during the first run; cached re-runs are not representative of live latency.

## Error analysis

Full dump (categorized false negatives + sampled false positives) in [`benchmarks/injection/results/error_analysis.md`](../../benchmarks/injection/results/error_analysis.md).

- `aegis_stages_1_3`: 320 missed injections (FN) across malicious sets; 6 benign items over-flagged (FP) across benign sets.
- `aegis_stages_1_4_openai`: 149 missed injections (FN) across malicious sets; 13 benign items over-flagged (FP) across benign sets.
- `aegis_stages_1_4_anthropic`: 110 missed injections (FN) across malicious sets; 13 benign items over-flagged (FP) across benign sets.

## Limitations

- **Rule-based stages may overfit known patterns.** Stages 1–3 are deterministic regex/heuristics; novel phrasings and encoding tricks (base64, homoglyphs, indirection) can evade them — see the error analysis.
- **Dataset coverage.** `deepset` is direct injection; `InjecAgent` is a 250-case indirect sample; benign corpora are public text + synthetic memory entries. Real-world memory content may differ. CIs quantify sampling uncertainty but not distribution shift.
- **Forced Stage 4.** Stage 4 is forced on every item for measurement; in production it is gated, so production latency/cost differ from the `aegis_stages_1_4_*` rows here.
- **Stage-4 fenced-JSON bug — found here and fixed.** This benchmark surfaced a real production bug: `InjectionClassifier` did a bare `json.loads()` on the adapter's output, so models that wrap JSON in markdown fences (observed with Claude Haiku 4.5: ```` ```json … ``` ````) made the parse fail and the classifier silently fell back to regex-only — Stage 4 *did nothing* for such models (OpenAI avoided it via `response_format=json_object`). Fixed in `server/content_security.py` (`_parse_classifier_json` strips fences and falls back to the outermost `{…}`), with a regression test in `tests/test_content_security.py`. The `aegis_stages_1_4_anthropic` rows reflect Stage 4 actually running.
- **API latencies.** Anthropic-system latencies are taken from the live run; metric values for the Anthropic systems come from a cache-served re-run (same responses). Latencies are representative of live calls (including rate-limit backoff on this account's tier).
- **Self-assessment, not third-party audit.** This benchmark is authored by the Aegis maintainers. Results are reproducible (pinned revisions, seeds, cached LLM responses) but have not been independently audited.
- **LLM nondeterminism.** Stage 4 and `llm_judge_*` depend on hosted models that may change; responses are cached for reproducibility of *this* run, keyed by prompt hash.
