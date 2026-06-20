# `aegis inspect` — follow-up issues (out of scope for `fix/static-analyzer-taint`)

These were surfaced by the two cold-reviewer audits of `/aegis:inspect` but deliberately left out of
the static-analyzer correctness fix (receiver+method sinks + bounded cross-file taint). Track and
schedule separately.

## Findings UX
- **Emit `aegis.guard.write(...)` fix-diffs in findings.** Each real flow finding currently links to a
  generic `guard.protect` / `guard.write` snippet. Generate a concrete, paste-able diff anchored to the
  finding's `file:line` and the sink call instead of boilerplate.
- **Stop labeling `suggested_policies.yml` as "derived" when `flows == 0`.** The policy block is a fixed
  opinionated default (`aegis_memory/inspect/policies.py`). When no flows are found it should be labeled
  a **default template**, not "generated from findings", until it is actually derived from real flows.

## Risk score
- **The risk-score paradox.** The heuristic memory-risk score can move in unintuitive directions and
  sits next to the benchmarked scanner. Either make it a meaningful, defensible measure or shrink it to
  an unmistakably cosmetic indicator, and surface the *real* benchmark number (`benchmarks/results.json`)
  distinctly. (Partially mitigated here: the static map is now explicitly labeled heuristic/preliminary
  and separated from the benchmarked scanner, but the score's semantics still need work.)

## Onboarding / distribution
- **`aegis: command not found` (README step 1).** The quickstart's first command fails when the console
  script isn't on `PATH`. Fix the PATH/entry-point guidance (and/or document `python -m aegis_memory.cli`)
  so step 1 doesn't block a first run.

## Static analyzer — next increments
- **SARIF output** so findings drop into code-scanning / CI annotations.
- **Suppression / allowlist** (`# aegis: ignore`, a config allowlist) for accepted sinks.
- **CI exit codes** (non-zero on new critical flows) for gating.
- **Signed, no-egress attestation + SBOM** for the local/keyless run, to back the "local & keyless" claim.
- **Taint engine depth.** The current interprocedural resolver is bounded and name-based
  (`aegis_memory/inspect/interproc.py`: `MAX_HOPS`, `MAX_FUNCS`, no type/alias resolution, no container
  aliasing). Candidate upgrades: import-alias resolution, basic type binding for receivers, and
  container element tracking — each weighed against the "no general solver" constraint.
