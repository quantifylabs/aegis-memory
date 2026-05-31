# Aegis content-security pipeline — injection-detection benchmark

_Generated from `benchmarks/injection/results/results.json` · run 2026-05-31T12:06:32.801214+00:00 · seed 42 · bootstrap n=1000_

## Threat model

Aegis's content-security pipeline detects **prompt injection / memory poisoning in content being written to memory** — text that, once stored and later retrieved, could manipulate an agent. This is the scope measured here. It is **not** an LLM-jailbreak defense and is not evaluated as one. Every system is scored on **both** malicious and benign corpora, so the false-positive rate (FPR) is reported next to recall everywhere — a detector that flags everything scores 100% recall and is useless.

## Methodology

- **Systems** are wrapped as `predict(text) -> bool` (True = flagged). Aegis systems call the real `ContentSecurityScanner` from `server/content_security.py`; detection logic is never reimplemented.
- **`aegis_stages_1_3`** runs the deterministic Stages 1–3 (`scan`). **`aegis_stages_1_4_*`** add the Stage-4 LLM classifier (`scan_async`), forced on every item via `trust_level="untrusted"` so the ablation can measure Stage 4's standalone contribution. *Production gates Stage 4 conditionally — this is a measurement choice, not production behavior.*
- **Metrics:** confusion matrix → precision, recall, F1, FPR, accuracy, with bootstrapped 95% CIs (resampling cases, n=1000, seed=42). Median per-item latency too.
- A metric is shown as `—` when undefined (e.g. FPR on a malicious-only dataset, precision on a benign-only dataset).

- **Environment:** Python 3.11.9, Windows-10-10.0.26200-SP0. Models: OpenAI `gpt-4o-mini`, Anthropic `claude-haiku-4-5-20251001`. Key libs: transformers `4.46.3`, torch `2.12.0+cpu`, datasets `2.19.1`, llm_guard `unknown`.

## Datasets

| Dataset | Kind | N | Injection | Benign | Revision | Status |
|---|---|--:|--:|--:|---|---|
| `deepset` | malicious_direct | 662 | 263 | 399 | `4f61ecb038e9` | ok |
| `injecagent` | malicious_indirect | 250 | 250 | 0 | `623f1bf3ad8e` | ok |
| `benign_public` | benign | 750 | 0 | 750 | `bdd27f4d94b9` | ok |
| `benign_synth` | benign | 750 | 0 | 750 | `builtin-v1` | ok |

- **deepset** — label 1=injection, 0=legitimate; all splits combined. _(source: hf:deepset/prompt-injections)_
- **injecagent** — 250 sampled (seed=42) from data/test_cases_dh_base.json, data/test_cases_ds_base.json; all malicious (indirect). _(source: github:uiuc-kang-lab/InjecAgent)_
- **benign_public** — 750 sampled (seed=42) from dolly context/response, length 20-500 chars; all benign. _(source: hf:databricks/databricks-dolly-15k)_
- **benign_synth** — 750 templated memory-like entries (seed=42); all benign. Generator pinned as builtin-v1. _(source: synthetic:templated_memory_entries)_

## Headline results

Recall and FPR shown with 95% CI. Full CIs for precision/F1 are in `results.json`.

### `deepset` (malicious_direct, N=662)

| System | Precision | Recall [95% CI] | F1 | FPR [95% CI] | Acc | Median latency |
|---|--:|--:|--:|--:|--:|--:|
| `no_protection` | — | 0.000 [0.00–0.00] | — | 0.000 [0.00–0.00] | 0.603 | 0 µs |
| `naive_regex` | 1.000 | 0.144 [0.10–0.19] | 0.252 | 0.000 [0.00–0.00] | 0.660 | 6 µs |
| `protectai_deberta` | 0.965 | 0.414 [0.36–0.48] | 0.580 | 0.010 [0.00–0.02] | 0.761 | 224.9 ms |
| `llm_guard` | 0.965 | 0.414 [0.36–0.48] | 0.580 | 0.010 [0.00–0.02] | 0.761 | 201.2 ms |
| `llm_judge_openai` | 0.944 | 0.829 [0.78–0.87] | 0.883 | 0.033 [0.02–0.05] | 0.912 | 589.7 ms |
| `llm_judge_anthropic` | 0.995 | 0.757 [0.70–0.81] | 0.860 | 0.003 [0.00–0.01] | 0.902 | 3407.9 ms |
| `aegis_stages_1_3` | 1.000 | 0.144 [0.10–0.19] | 0.252 | 0.000 [0.00–0.00] | 0.660 | 46 µs |
| `aegis_stages_1_4_openai` | 1.000 | 0.669 [0.61–0.73] | 0.802 | 0.000 [0.00–0.00] | 0.869 | 1225.0 ms |
| `aegis_stages_1_4_anthropic` | 1.000 | 0.745 [0.69–0.79] | 0.854 | 0.000 [0.00–0.00] | 0.899 | 3109.9 ms |

### `injecagent` (malicious_indirect, N=250)

| System | Precision | Recall [95% CI] | F1 | FPR [95% CI] | Acc | Median latency |
|---|--:|--:|--:|--:|--:|--:|
| `no_protection` | — | 0.000 [0.00–0.00] | — | — | 0.000 | 0 µs |
| `naive_regex` | — | 0.000 [0.00–0.00] | — | — | 0.000 | 25 µs |
| `protectai_deberta` | 1.000 | 0.660 [0.60–0.72] | 0.795 | — | 0.660 | 320.2 ms |
| `llm_guard` | 1.000 | 0.656 [0.60–0.72] | 0.792 | — | 0.656 | 326.4 ms |
| `llm_judge_openai` | 1.000 | 0.672 [0.62–0.73] | 0.804 | — | 0.672 | 579.8 ms |
| `llm_judge_anthropic` | 1.000 | 0.932 [0.90–0.96] | 0.965 | — | 0.932 | 3224.3 ms |
| `aegis_stages_1_3` | 1.000 | 0.620 [0.56–0.68] | 0.765 | — | 0.620 | 144 µs |
| `aegis_stages_1_4_openai` | 1.000 | 0.748 [0.69–0.80] | 0.856 | — | 0.748 | 1286.2 ms |
| `aegis_stages_1_4_anthropic` | 1.000 | 0.828 [0.78–0.87] | 0.906 | — | 0.828 | 3241.6 ms |

### `benign_public` (benign, N=750)

| System | Precision | Recall [95% CI] | F1 | FPR [95% CI] | Acc | Median latency |
|---|--:|--:|--:|--:|--:|--:|
| `no_protection` | — | — | — | 0.000 [0.00–0.00] | 1.000 | 0 µs |
| `naive_regex` | — | — | — | 0.000 [0.00–0.00] | 1.000 | 20 µs |
| `protectai_deberta` | 0.000 | — | — | 0.039 [0.03–0.05] | 0.961 | 239.8 ms |
| `llm_guard` | 0.000 | — | — | 0.039 [0.03–0.05] | 0.961 | 234.7 ms |
| `llm_judge_openai` | 0.000 | — | — | 0.004 [0.00–0.01] | 0.996 | 583.2 ms |
| `llm_judge_anthropic` | — | — | — | 0.000 [0.00–0.00] | 1.000 | 3437.8 ms |
| `aegis_stages_1_3` | 0.000 | — | — | 0.001 [0.00–0.00] | 0.999 | 160 µs |
| `aegis_stages_1_4_openai` | 0.000 | — | — | 0.001 [0.00–0.00] | 0.999 | 1181.5 ms |
| `aegis_stages_1_4_anthropic` | 0.000 | — | — | 0.001 [0.00–0.00] | 0.999 | 3105.2 ms |

### `benign_synth` (benign, N=750)

| System | Precision | Recall [95% CI] | F1 | FPR [95% CI] | Acc | Median latency |
|---|--:|--:|--:|--:|--:|--:|
| `no_protection` | — | — | — | 0.000 [0.00–0.00] | 1.000 | 0 µs |
| `naive_regex` | — | — | — | 0.000 [0.00–0.00] | 1.000 | 7 µs |
| `protectai_deberta` | 0.000 | — | — | 0.040 [0.03–0.05] | 0.960 | 188.7 ms |
| `llm_guard` | 0.000 | — | — | 0.040 [0.03–0.05] | 0.960 | 176.7 ms |
| `llm_judge_openai` | 0.000 | — | — | 0.001 [0.00–0.00] | 0.999 | 588.3 ms |
| `llm_judge_anthropic` | — | — | — | 0.000 [0.00–0.00] | 1.000 | 3425.8 ms |
| `aegis_stages_1_3` | — | — | — | 0.000 [0.00–0.00] | 1.000 | 49 µs |
| `aegis_stages_1_4_openai` | — | — | — | 0.000 [0.00–0.00] | 1.000 | 1144.0 ms |
| `aegis_stages_1_4_anthropic` | — | — | — | 0.000 [0.00–0.00] | 1.000 | 3118.8 ms |

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

### `aegis_stages_1_4_openai`

**`deepset`** (malicious_direct, N=662)

| Stages | Recall | FPR | Precision | F1 |
|---|--:|--:|--:|--:|
| Stage 1 | 0.000 | 0.000 | — | — |
| + Stage 2 | 0.000 | 0.000 | — | — |
| + Stage 3 | 0.144 | 0.000 | 1.000 | 0.252 |
| + Stage 4 | 0.669 | 0.000 | 1.000 | 0.802 |

_Items flagged per stage (any flag): S1=0, S2=0, S3=38, S4=168._

**`injecagent`** (malicious_indirect, N=250)

| Stages | Recall | FPR | Precision | F1 |
|---|--:|--:|--:|--:|
| Stage 1 | 0.000 | — | — | — |
| + Stage 2 | 0.620 | — | 1.000 | 0.765 |
| + Stage 3 | 0.620 | — | 1.000 | 0.765 |
| + Stage 4 | 0.748 | — | 1.000 | 0.856 |

_Items flagged per stage (any flag): S1=0, S2=155, S3=0, S4=145._

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

### `aegis_stages_1_4_anthropic`

**`deepset`** (malicious_direct, N=662)

| Stages | Recall | FPR | Precision | F1 |
|---|--:|--:|--:|--:|
| Stage 1 | 0.000 | 0.000 | — | — |
| + Stage 2 | 0.000 | 0.000 | — | — |
| + Stage 3 | 0.144 | 0.000 | 1.000 | 0.252 |
| + Stage 4 | 0.745 | 0.000 | 1.000 | 0.854 |

_Items flagged per stage (any flag): S1=0, S2=0, S3=38, S4=193._

**`injecagent`** (malicious_indirect, N=250)

| Stages | Recall | FPR | Precision | F1 |
|---|--:|--:|--:|--:|
| Stage 1 | 0.000 | — | — | — |
| + Stage 2 | 0.620 | — | 1.000 | 0.765 |
| + Stage 3 | 0.620 | — | 1.000 | 0.765 |
| + Stage 4 | 0.828 | — | 1.000 | 0.906 |

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

## Latency comparison

Median per-item latency (lower is better). Deterministic stages 1–3 are orders of magnitude faster than LLM-based detectors.

| System | `deepset` | `injecagent` | `benign_public` | `benign_synth` |
|---|--:|--:|--:|--:|
| `no_protection` | 0 µs | 0 µs | 0 µs | 0 µs |
| `naive_regex` | 6 µs | 25 µs | 20 µs | 7 µs |
| `protectai_deberta` | 224.9 ms | 320.2 ms | 239.8 ms | 188.7 ms |
| `llm_guard` | 201.2 ms | 326.4 ms | 234.7 ms | 176.7 ms |
| `llm_judge_openai` | 589.7 ms | 579.8 ms | 583.2 ms | 588.3 ms |
| `llm_judge_anthropic` | 3407.9 ms | 3224.3 ms | 3437.8 ms | 3425.8 ms |
| `aegis_stages_1_3` | 46 µs | 144 µs | 160 µs | 49 µs |
| `aegis_stages_1_4_openai` | 1225.0 ms | 1286.2 ms | 1181.5 ms | 1144.0 ms |
| `aegis_stages_1_4_anthropic` | 3109.9 ms | 3241.6 ms | 3105.2 ms | 3118.8 ms |

> Note: API-system latencies are measured on live calls during the first run; cached re-runs are not representative of live latency.

## Error analysis

Full dump (categorized false negatives + sampled false positives) in [`benchmarks/injection/results/error_analysis.md`](../../benchmarks/injection/results/error_analysis.md).

- `aegis_stages_1_3`: 320 missed injections (FN) across malicious sets; 1 benign item over-flagged (FP) across benign sets.
- `aegis_stages_1_4_openai`: 150 missed injections (FN) across malicious sets; 1 benign item over-flagged (FP) across benign sets.
- `aegis_stages_1_4_anthropic`: 110 missed injections (FN) across malicious sets; 1 benign item over-flagged (FP) across benign sets.

## Limitations

- **Rule-based stages may overfit known patterns.** Stages 1–3 are deterministic regex/heuristics; novel phrasings and encoding tricks (base64, homoglyphs, indirection) can evade them — see the error analysis.
- **Dataset coverage.** `deepset` is direct injection; `InjecAgent` is a 250-case indirect sample; benign corpora are public text + synthetic memory entries. Real-world memory content may differ. CIs quantify sampling uncertainty but not distribution shift.
- **Forced Stage 4.** Stage 4 is forced on every item for measurement; in production it is gated, so production latency/cost differ from the `aegis_stages_1_4_*` rows here.
- **Stage-4 fenced-JSON bug — found here and fixed.** This benchmark surfaced a real production bug: `InjectionClassifier` did a bare `json.loads()` on the adapter's output, so models that wrap JSON in markdown fences (observed with Claude Haiku 4.5: ```` ```json … ``` ````) made the parse fail and the classifier silently fell back to regex-only — Stage 4 *did nothing* for such models (OpenAI avoided it via `response_format=json_object`). Fixed in `server/content_security.py` (`_parse_classifier_json` strips fences and falls back to the outermost `{…}`), with a regression test in `tests/test_content_security.py`. The `aegis_stages_1_4_anthropic` rows reflect Stage 4 actually running.
- **API latencies.** Anthropic-system latencies are taken from the live run; metric values for the Anthropic systems come from a cache-served re-run (same responses). Latencies are representative of live calls (including rate-limit backoff on this account's tier).
- **Self-assessment, not third-party audit.** This benchmark is authored by the Aegis maintainers. Results are reproducible (pinned revisions, seeds, cached LLM responses) but have not been independently audited.
- **LLM nondeterminism.** Stage 4 and `llm_judge_*` depend on hosted models that may change; responses are cached for reproducibility of *this* run, keyed by prompt hash.
