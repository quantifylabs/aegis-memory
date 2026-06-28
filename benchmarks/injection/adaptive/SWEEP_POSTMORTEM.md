# Postmortem — adaptive full-sweep execution failure

_Date: 2026-06-28 · Author: Claude Code session · Component:
`benchmarks/injection/adaptive/` (Phase 2 adaptive attack harness)_

## Executive summary

The adaptive attack harness was built, unit-tested, and **smoke-validated end to
end** (all three attacks, both tiers) at trivial cost. The maintainer then asked
for the **full pre-registered sweep** (N=250/tier, query budget 30, all 10 systems
incl. Anthropic Stage-4) to produce real numbers for the docs and PR.

The full sweep **never completed**. After a long investigation the conclusion is
that this was **not a harness bug** — the harness runs correctly and resumes from
cache efficiently. The full run was blocked by a combination of three things:

1. **A fundamental runtime/​environment mismatch** — the full sweep is ~18–20h of
   *sequential* API work, while this execution environment **kills long-running
   background tasks unpredictably** (observed 2 min – 77 min) and reaps the whole
   process tree. No long job can finish inside a single survival window here.
2. **A visibility gap in the harness** (since fixed) — there was no per-seed
   progress output and mutation cache writes are buffered, so a *working* long run
   was indistinguishable from a *frozen* one. This caused the operator (me) to
   **misdiagnose a healthy run as hung and kill it repeatedly** — several of the
   "failures" were self-inflicted.
3. **Intermittent network stalls during model warmup** (since worked around) — the
   HuggingFace Hub calls made while warming the 3 heavy ML baselines occasionally
   hung; bounded/eliminated with offline mode + connect timeouts.

The smoke run passed for two simple reasons the full run could not satisfy: it
**finished within a survival window** (~3–5 min) and was **small enough that the
visibility gap never mattered**.

The investigation produced four real hardening/visibility improvements, all
committed (see [Fixes shipped](#fixes-shipped)). No detection logic, static
dataset, or static result was changed.

---

## Background

- **Harness**: three adaptive attacks (rule-evasion → Stage 3; classifier-oracle →
  Stage 4; composition) that reuse the static benchmark machinery; evasion =
  `1 − recall` via the existing metrics path. Writes a separate
  `adaptive_results.json`; never touches the static `results.json`.
- **Smoke run** (validated, cheap):
  `run_adaptive --limit 5 --systems no_protection,naive_regex,llm_judge_openai,aegis_stages_1_3,aegis_stages_1_4_openai`
  → completed `EXIT=0` in ~5 min, 212 cheap `gpt-4o-mini` calls, all 3 attacks ×
  2 tiers, wrote `adaptive_results.json` + 6 corpora.
- **All-systems validation** (`--limit 2`, all 10 systems) → completed `EXIT=0` in
  **188s**, exercising Anthropic Stage-4 + the ML baselines + the transfer path.
- **Full run** (`run_adaptive`, no `--limit`): frozen config N=250/tier (only ~163
  payloads per the deterministic Stage-3-flagged pool actually qualify as seeds),
  budget 30, all 10 systems. **Never completed.**

---

## Incident timeline & counter-efforts

Background task IDs and outcomes (all to `scratchpad/full_sweep.log`):

| # | Task | Change under test | Outcome |
|---|------|-------------------|---------|
| 1 | `bce7h3dji` | first full run | env-killed ~20s in |
| 2 | `b01cyl4nk` | relaunch | operator-killed — *appeared* hung in warmup |
| 3 | `bkshtlbe7` | `HF_HUB_OFFLINE=1` + `-u` | operator-killed — *appeared* hung after dataset load |
| 4 | `bo3us5qsi` | seed-pool disk cache | operator-killed — *appeared* hung at `[attack1]` |
| 5 | `bvw5k13pp` | connect-timeout on clients | operator-killed — *appeared* hung at `[attack1]` |
| 6 | `b4bmwqqsv` | **per-seed progress logging** | **env-killed at ~77 min** — visibly healthy, reached Attack-1 seed 120/163 |
| 7 | `bypq8ppta` | resume-from-cache | env-killed at ~2 min (during warmup) |
| 8 | `bwzrm9ldy` | self-restarting wrapper | env-killed (whole tree reaped) |

### Phase A — "frozen in warmup"
The first full runs froze with the log stuck right after the ProtectAI model
initialised, the process at ~0 CPU / ~10 MB resident.

- **Hypothesis**: a stale HuggingFace `datasets` file-lock, then a hung HF Hub
  network call during heavy-model warmup.
- **Counter-efforts**: checked for stale `.lock` files (none); ran with
  `HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1` so warmup loads the already-cached
  models from disk with no network resolution; added `PYTHONUNBUFFERED=1`/`-u` for
  live output. Warmup then completed reliably.

### Phase B — "frozen at `[attack1]`, zero cache writes"
Every run then froze immediately after printing `[attack1]`: no further console
output, **0 cache files written**, process at ~0 CPU.

- **Hypotheses chased**: repeated dataset re-fetches in `pick_seeds` (the loader is
  called ~10× across attacks/tiers); a hung DNS/connect on the first OpenAI call
  (the process had **no TCP connections** and a trimmed working set — classic
  blocked-syscall signature).
- **Counter-efforts**:
  - **Seed-pool disk cache** — load each malicious pool once and persist it, so the
    sweep never re-hits HF/GitHub for seeds (commit `3bbf6af`).
  - **Connect-bounded HTTP timeout** (15s connect / 120s read) on every
    OpenAI/Anthropic client, so a stalled connect fails fast and the existing 8×
    backoff retries ride it out (commit `58593d0`).
  - **Direct isolation tests** — and this is where the real cause surfaced:
    - a standalone OpenAI call returned in **2.5s** (network was *fine*);
    - warming all 10 systems then one mutation call worked in **4.4s**;
    - `pick_seeds(250)` returned 163 seeds in **0.09s**, and the first
      `variants(6)` mutation took **18.2s** — *all working*.

- **Actual root cause (Phase B)**: the run **was never frozen**. The Attack-1
  search is sequential — ~163 seeds × up to 18 mutation calls each (~38s/seed) ≈
  **~1.8h for one attack/tier** — and it produced **no intermediate output**.
  Worse, mutation responses are cached under a **unique per-(seed,generation,variant)
  cache key**, so each lands in its own 1-entry file and **never trips the
  cache's "flush every 50 entries" rule** — nothing hits disk until the
  block-level flush at the *end* of the attack. From the outside this is
  indistinguishable from a hang: log static, no disk writes, low CPU (the process
  is in network I/O wait, which Windows pages out to a small resident set). **I
  repeatedly killed a healthy run.**

- **Fix**: per-seed progress logging (`seed i/total (elapsed)`) plus a cache flush
  every 10 seeds, so progress is visible *and* persisted (commit `266aa64`). With
  this, the next run was visibly healthy — Attack-1 advanced to seed 120/163 over
  ~77 min, flushing hundreds of cache files.

### Phase C — environment reaps long background tasks
Run `b4bmwqqsv`, now clearly healthy, was **killed by the environment at ~77 min**
while the operator was idle (not at any wakeup boundary). Subsequent relaunches
were killed at ~2 min and within minutes. A **self-restarting bash wrapper** was
tried so a killed Python child would auto-resume from cache without operator
intervention — but the environment **reaped the entire process tree**, killing the
wrapper too.

- **Root cause (Phase C)**: the execution environment terminates long-running
  background tasks unpredictably (2–77 min observed) and reaps the whole tree.
  This is outside the harness's control. Cache-resume mitigates it — a relaunch
  fast-forwarded through 120 cached seeds in **~10s** — but completing ~18–20h of
  sequential work this way would require *dozens* of manual relaunch cycles.

---

## Why the smoke run passed but the full run did not

This is the crux, and the answer is **not** "different code paths." The smoke and
full runs execute the same code. The differences are entirely **scale** and
**duration**:

| Factor | Smoke (`--limit 5`, 5 cheap systems) | Full (N≈163, budget 30, 10 systems) |
|---|---|---|
| Total work | ~212 cheap calls | ~tens of thousands of calls (~18–20h sequential) |
| Completes inside a survival window? | **Yes** (~5 min) | **No** (far exceeds any 2–77 min window) |
| Warmup | fast, no heavy/Anthropic models | 3 heavy HF models → intermittent network stalls |
| Visibility gap matters? | **No** — finishes before it could look "hung" | **Yes** — looks frozen for ~1.8h/attack with no output |
| Outcome | `EXIT=0` | interrupted every time |

1. **Survival window.** The decisive factor. The environment kills background
   tasks within minutes-to-~an-hour. A ~5-minute smoke run finishes comfortably
   inside that window; an ~18–20h sweep cannot, no matter how robust the code.
2. **The visibility gap was scale-sensitive.** On the smoke run the whole pipeline
   completed before the absence of progress output or buffered cache writes could
   ever look like a hang. On the full run, each attack spends ~1–2h in a silent,
   disk-quiet, low-CPU state — which looks exactly like a freeze and triggered
   repeated (wrong) kills. This is why the *same working code* "passed" small and
   "failed" large.
3. **Warmup fragility scaled with system count.** Smoke restricted `--systems` to
   5 cheap ones (no heavy ML models, no Anthropic), so warmup was quick and
   network-light. The full run warms all 10 — including 3 HuggingFace models whose
   Hub calls intermittently hung.

In short: **the full run "failed" because it is long, and this environment cannot
keep a long task alive — amplified by a visibility gap that made a working run
look dead.** The smoke run "passed" because it was short and small enough that
neither problem could bite.

---

## Fixes shipped (committed to `feat/adaptive-attack-harness`)

These came out of the investigation and are genuine robustness/visibility
improvements, independent of the environment problem:

| Commit | Fix |
|---|---|
| `418695a` | Rate-limit resilience: 8× SDK retries on the mutation/intent client + per-seed crash guards (a hard failure aborts one seed, not the sweep). |
| `3bbf6af` | Seed pools cached to disk (one-shot dataset load; no repeated HF/GitHub fetches in the hot path). |
| `58593d0` | Connect-bounded HTTP timeout (15s) on every API client, so a stalled connect fails fast and retries instead of freezing. |
| `266aa64` | **Per-seed progress logging + periodic cache flush** — the fix for the misdiagnosis; a long run is now observably alive and persists progress every 10 seeds. |

Operational settings that proved necessary for the full run:
`HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONUNBUFFERED=1` and Python `-u`.

All 18 network-free unit tests remain green. The static `results.json` is
byte-unchanged throughout.

---

## State at end of investigation

- **Banked in the shared response cache**: ~18,882 cached LLM responses across
  2,033 files (includes the static benchmark's cached Stage-4 responses plus
  adaptive work). Attack-1 white_box reached seed ~120/163; Attack-1 grey_box,
  Attack-2 both tiers, and Attack-3 are only partially or not started.
- **No full `adaptive_results.json`** for the real sweep was produced (the smoke
  one under `adaptive/results/` is gitignored and not representative).
- The docs (`CHANGELOG.md`, `docs/security/benchmark.md`) still carry the honest
  **"full adaptive numbers pending a separate approved sweep"** notes.

---

## Recommendations

1. **Run the full sweep on infrastructure that does not reap long tasks** (a CI job
   with a multi-hour budget, a dedicated VM, or `nohup`/`tmux` on a stable host).
   The harness + cache-resume make this turnkey; budget ~$5–10 and ~18–20h.
2. **Optionally parallelise the Attack-2 oracle across seeds.** Each seed's search
   is independent; bounding concurrency to the provider rate limits would cut the
   dominant cost from ~hours to well under an hour and shrink the exposure window.
3. **Enable Anthropic prompt-caching on the Stage-4 system prompt** (a library
   adapter change, noted as a follow-up in the original task) — ~90% input-cost
   reduction on the repeated oracle queries.
4. **Until then, ship the harness PR on its current (smoke-validated) scope**, with
   the docs' "pending sweep" notes intact — which matches the original task's
   stated handoff (harness now; billed sweep separately).

---

## Lessons

- **Long, silent, I/O-bound runs need a heartbeat.** The single most expensive
  mistake here was operating a working run as if it were hung because it produced
  no output and no disk activity. Progress logging + periodic flush should be
  table stakes for any multi-hour batch job. (Now fixed.)
- **Validate at the scale you'll run at, or make scale-out observable.** A green
  smoke run did not surface the visibility gap because the gap only manifests at
  scale. The fix is not "bigger smoke tests" but "make the long run observable."
- **Distinguish `0 CPU + 0 disk + no sockets` (blocked/working in I/O) from a true
  hang.** Here it was repeatedly read as a freeze; isolation tests (standalone API
  call, timed `pick_seeds`, timed first mutation) were what finally proved the code
  was healthy and the environment was the constraint.
