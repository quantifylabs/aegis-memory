# `aegis inspect` — follow-up issues (out of scope for `fix/static-analyzer-taint`)

> **Tracked in:** taint depth [#78](https://github.com/quantifylabs/aegis-memory/issues/78) · findings UX [#79](https://github.com/quantifylabs/aegis-memory/issues/79) · risk score [#80](https://github.com/quantifylabs/aegis-memory/issues/80) · onboarding/PATH [#81](https://github.com/quantifylabs/aegis-memory/issues/81) · CI/output (SARIF/allowlist/exit codes/SBOM) [#82](https://github.com/quantifylabs/aegis-memory/issues/82). This file is the detailed spec; follow the issues for status.

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
- ✅ **SARIF output** so findings drop into code-scanning / CI annotations — shipped:
  `aegis-out/findings.sarif` (`aegis_memory/inspect/sarif.py`), written on every run.
- ✅ **Suppression / allowlist** — shipped: an inline `# aegis: ignore` on (or directly above) a
  sink call drops its findings (`analyzer.py` `_suppressed_lines`/`_site_suppressed`). A config-file
  allowlist is still open.
- **CI exit codes** (non-zero on new critical flows) for gating. (`--ci --max-risk` exists today;
  a *new-flow* gate vs. a baseline is the remaining piece.)
- **Signed, no-egress attestation + SBOM** for the local/keyless run, to back the "local & keyless" claim.

## Detection honesty (fixed)
- ✅ **Blanket sanitizer flag → sink-tied.** A `scanner.scan(...)` of an *unrelated* value no longer
  marks every write in the function `screened` (the old `has_sanitizer_call` scope flag). Screening
  is now tied to the written value's own untrusted leaf (`taint.py` `_value_screened` /
  `scanned_value_names`). Regression: `test_unrelated_scan_does_not_screen_a_raw_write`.
- ✅ **Substring heuristics tightened.** `_writes_shared_scope` keys off the scope/namespace argument
  (not any string literal); `_scan_read_paths` matches identifier tokens, not `ast.dump` text (so a
  literal containing "source" no longer suppresses a provenance finding); the provenance finding now
  names the real receiver/framework instead of a hardcoded LangGraph `store.get`.
- **Taint engine depth.** The current interprocedural resolver is bounded and name-based
  (`aegis_memory/inspect/interproc.py`: `MAX_HOPS`, `MAX_FUNCS`, no type/alias resolution, no container
  aliasing). Candidate upgrades: import-alias resolution, basic type binding for receivers, and
  container element tracking — each weighed against the "no general solver" constraint.
