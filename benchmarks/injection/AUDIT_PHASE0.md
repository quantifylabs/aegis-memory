# Phase 0 — Injection Benchmark Methodology Audit

**Verdict: static benchmark certified sound. 1 latent correctness fix applied (verified no-op on
published numbers); 2 honesty-caveats documented for the maintainer; 0 issues that move a published
number.**

This audit certifies the static benchmark in `benchmarks/injection/` before an adaptive-attack eval
is built on top of it. Methodology was inspected across areas A–H, and the offline-runnable probes
were executed against real code/data. Credentialed systems (`llm_judge_*`, `aegis_stages_1_4_*`,
`llama_prompt_guard_2`) were audited statically; their behavioral probe is deferred (needs API keys /
gated-model token) and noted as such.

Scope: audit + one correctness fix that provably does not move numbers. No adaptive attacks, no new
datasets/systems, no changes to detection logic in `server/content_security.py`.

---

## Findings table

| Area | Check | Status | Severity | Moves published numbers? | Action |
|---|---|---|---|---|---|
| A | `predict→bool` contract: True = flagged/unsafe, False = allowed — consistent across all 10 systems (incl. `llm_guard`'s intentional `not is_valid` inversion, systems.py:295) | **PASS** | — | no | none |
| A | `llama_prompt_guard_2` maps positive class via model's own `config.id2label[1]` (systems.py:262) | **PASS** | — | no | none |
| A | `protectai_deberta` used a hard-coded `== "INJECTION"` string (was systems.py:201) — same fragility class as the PG2 label-mapping bug | **ISSUE→FIXED** | correctness/robustness | **no** (probe: `id2label = {0:'SAFE', 1:'INJECTION'}`, so index-1 == the old string) | Hardened to resolve from `id2label[1]` like llama; regression test added |
| A | Stage-4 fenced-JSON handled (content_security.py:127–144); a parse/API failure returns `None` → silently counted **benign**, logged (`logger.warning`) but not surfaced as a benchmark error | **AMBIGUOUS** | honesty-caveat | no | Document; consider surfacing parse failures as `n_errors` in Phase 2 |
| A | `llm_judge_*` parse: non-`YES`-prefixed reply → benign (systems.py:383). By design; deterministic at temp=0 | **PASS (note)** | nit | no | Document |
| B | recall = TP/(TP+FN) over attacks; FPR = FP/(FP+TN) over benign; precision/F1/accuracy correct (metrics.py:37–49); confusion logic correct (metrics.py:19–30) | **PASS** | — | no | none |
| C | deepset native label read as `int(label)==1` (not inverted); InjecAgent all-True; benign_public/benign_synth/notinject all-False; N = 662/250/750/750/339; every loader fetches with the *resolved* SHA (`revision=resolved` / SHA embedded in raw URL), covered by existing tests | **PASS** | — | no | none |
| D | Cumulative ablation S1→+S2→+S3→+S4 (metrics.py:114–143); Stage-1-vs-Stage-2 disambiguation via `matched_pattern` prefix despite shared `DetectionType.SSN` (systems.py:460–475); Stage-2 PII nuance is **measured**: marginal_counts S2 = 0 on direct (deepset) and 155/250 on indirect (injecagent), attributed to Stage 2 not injection detection | **PASS** | — | no | none |
| E | Bootstrap n=1000, seed=42, per-item case resampling, percentile CIs (metrics.py:64–90, `np.random.default_rng(seed)`); InjecAgent 250-subsample uses `random.Random(SEED=42)` deterministically | **PASS** | — | no | none |
| F | `llm_judge_*` pin `temperature=0` (systems.py:365,405). **Stage-4 does NOT pin temperature**: `AegisStages14.warmup` constructs `OpenAIAdapter`/`AnthropicAdapter` without a `temperature` arg, so they use the adapter default `temperature=0.1` (extractors.py:267,325) | **ISSUE** | honesty-caveat (Phase-2-critical) | no (static numbers are cache-served) | Flag for maintainer: pin Stage-4 `temperature=0` **and** re-run Stage-4 cells together in Phase 2 |
| G | Latency: deterministic core timed on real `perf_counter` per item (systems.py:128–139); API systems show µs on cache-served cells and ~3.5 s live on NotInject Anthropic (rate-limit backoff, not per-item cost). `render_report.py` already caveats this (lines 287–288, 330–333) | **PASS** | honesty-caveat | no | Recommend paper report deterministic-core latency only; exclude/caveat API latency |
| H | Cache key = file `{system_id}__{model_id}` + `sha256(prompt)` (systems.py:64–95) — fully content-addressed | **PASS** | — | no | none |

---

## Probe results (executed)

Run via `.venv-bench` (transformers 4.53.3) / repo `python` using a throwaway probe harness
(not committed; results recorded below and reproducible from the cited code paths).

- **§A predict contract (offline systems):** all PASS — `injection → True`, `benign → False` for
  `naive_regex`, `llm_guard`, `aegis_stages_1_3`, `protectai_deberta`.
  Deferred (needs credentials): `llama_prompt_guard_2` (HF_TOKEN, gated), `llm_judge_openai/anthropic`
  and `aegis_stages_1_4_openai/anthropic` (OPENAI/ANTHROPIC keys). These were audited statically and
  are clean by inspection (llama uses id2label; judges/Stage-4 parse paths reviewed above).
- **§A protectai id2label gate:** `id2label = {0: 'SAFE', 1: 'INJECTION'}` → index-1 == `'INJECTION'`.
  Confirms the hardening fix produces the **identical** positive label as the old hard-coded string →
  **verified no-op on published numbers.**
- **§B hand-recompute (`naive_regex × NotInject`):** recomputed `n=339, tp=0, fp=5, tn=334, fn=0` —
  **exact match** to `results.json` `results.naive_regex.notinject.confusion`. End-to-end agreement of
  loader + predict + confusion.
- **§H cache-collision:** fabricated unseen prompt's sha256 absent from all 4 cache files
  (10,993 total entries). A new adaptive sample cannot be served a stale cached verdict.

---

## Fix applied (no-op on numbers)

`benchmarks/injection/systems.py` — `ProtectAIDeberta`: resolve the injection class from the model's
own `config.id2label[1]` at `warmup()` and compare `predict` against it, instead of the hard-coded
`str(out["label"]).upper() == "INJECTION"`. Mirrors `LlamaPromptGuard2`. Verified no-op because the
pinned revision's `id2label[1]` is already `"INJECTION"`. Hardens against a future revision renaming
the label to a generic `LABEL_1` (which would otherwise silently produce a fake 0% FPR — the PG2 bug
class).

Regression tests: `tests/test_injection_benchmark_systems.py`
- protectai resolves positive class via `id2label`, fires on a generic `LABEL_1`, and stays benign on
  `LABEL_0` (the failure mode the old string match would have missed);
- cache is content-addressed by `(system_id, model_id, sha256(prompt))` — new prompt / different
  system / different model all MISS (the §H invariant for the adaptive eval).

---

## Flagged for maintainer (NOT changed here)

1. **Stage-4 temperature not pinned (§F).** Adapters default to `temperature=0.1`. This understates
   determinism and weakens the oracle assumption the adaptive eval relies on. Recommended: pin Stage-4
   `temperature=0` and re-run the Stage-4 cells (`aegis_stages_1_4_*`) in a maintainer-approved re-run
   — do **not** change the code without re-running, or code and cached numbers would disagree.
2. **Stage-4 parse/API failure → silent benign (§A).** Logged but not counted as `n_errors`.
   Consider surfacing as errors so a degraded run is visible. Honesty-caveat; doesn't move current
   numbers.
3. **Latency reporting (§G).** For the paper: report deterministic-core latency on real timing;
   exclude API-system latency from headline latency claims or report it as live-call latency with the
   rate-limit-backoff caveat (the report already notes this).

No fix in this PR moves a published number (0% FPR, 1.5%/42.8% NotInject over-defense, ablation
deltas all unchanged). No re-run was triggered.
