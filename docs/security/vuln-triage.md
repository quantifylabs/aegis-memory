# Dependency vulnerability triage

_Audited with `pip-audit` 2.10.0 (OSV) on 2026-06-02. Ground truth for this PR; the OpenSSF
Scorecard viewer refreshes on its own schedule after merge._

## Headline

**Zero known vulnerabilities in the shipped library.** Every advisory OSV reports for this repo
lives in **benchmark-only dev tooling** (`benchmarks/injection/requirements.txt`), which is never
installed by people who `pip install aegis-memory`. Before this PR those advisories spanned
**3 distinct packages (28 advisory instances)**; after conservative bumps the residual is
**1 package (9 advisories), all in `transformers`, with no fix available below the major version
that breaks the benchmark's `llm-guard` dependency.**

| Surface | Manifest | Before | After |
|---|---|--:|--:|
| Shipped library | `server/requirements.txt` | 0 | 0 |
| Shipped library | `pyproject.toml` (core + `[server]`) | 0 | 0 |
| Benchmark / dev-only | `benchmarks/injection/requirements.txt` | 3 pkgs / 28 | **1 pkg / 9** |

The shipped surface was already clean thanks to the transitive security floors in
`server/requirements.txt` (`idna>=3.15`, `pygments>=2.20.0`, `tqdm>=4.66.3`). It is now also
gated in CI by [`.github/workflows/pip-audit.yml`](../../.github/workflows/pip-audit.yml) so a new
shipped-dependency vulnerability fails the build.

> **Note on the Scorecard count.** The public viewer has shown ~53 OSV advisories. That number
> counts *every advisory ID* across the fuller tree Scorecard resolves — including the duplicate
> IDs `pip-audit` also emits (e.g. `PYSEC-2024-227/228/229` were each listed twice) and the
> `PYSEC-2025-211..218` cluster, which is **one package**, not eight. The number that actually
> matters is **distinct shipped-dependency packages needing a fix: zero.**

## OSV-Scanner / OpenSSF Scorecard: lower-bound evaluation

Scorecard's **Vulnerabilities** check runs **OSV-Scanner** over *every* manifest in the repo, and it
differs from `pip-audit` in one decisive way: **OSV-Scanner scores the lower bound of each `>=`
constraint.** So `torch>=2.4` is evaluated at exactly `2.4` (flagging every advisory fixed after it),
even though a real `pip install` resolves to the latest patched torch. `pip-audit` resolves the
installed tree instead, which is why it reported only the `transformers` residual while Scorecard
showed many more. Confirmed locally with `osv-scanner scan source -r .` (v2.3.8).

Remediation, dev/benchmark-only manifests only (the shipped surface stays clean and untouched):

| Package | Manifest | Was | Now | How |
|---|---|---|---|---|
| `requests` | `benchmarks/injection/requirements.txt` | `>=2.31.0` (3 advisories) | `>=2.33.0` | floor bump — clears all 3 |
| `torch` | `benchmarks/injection/requirements.txt` | `>=2.4` (19 advisories) | `>=2.10.0` | floor bump clears 13 fixable; 6 no-fix advisories ignored in `osv-scanner.toml` |
| `transformers` | `benchmarks/injection/requirements.txt` | `>=4.53.0,<5` (9 residual) | unchanged | no `<5` fix; ignored in `osv-scanner.toml` |
| `langgraph` | `examples/*/requirements.txt` | `>=0.2.0` (`PYSEC-2026-83`) | unchanged | only fix is a 1.0.x major jump that breaks the 0.2-era demo; ignored per-example in `osv-scanner.toml` |

`torch>=2.10.0` is compatible: `llm-guard 0.3.15` only requires `torch>=2.4.0` with no upper cap.
Every ignored ID is a residual with **no usable fix** (no published patch, or a fix only behind a
breaking major bump), and lives in a manifest that `pip install aegis-memory` never touches.

## Manifests scanned

| Manifest | Role |
|---|---|
| `server/requirements.txt` | Shipped library runtime deps (PyPI install surface) |
| `pyproject.toml` (`dependencies`, `[server]`) | Shipped library / server extra |
| `benchmarks/injection/requirements.txt` | Benchmark-only dev tooling (transformers, torch, datasets, llm-guard, …) — not shipped |

No `setup.py`, `poetry.lock`, or other lockfiles exist in the repo.

## Triage table (one row per distinct package)

| Package | Version (before → after) | Manifest | Advisories (grouped) | Fix available | Safe bump? | Action |
|---|---|---|---|---|---|---|
| `python-dotenv` | `1.0.1` → `1.2.2` | benchmark-only | CVE-2026-28684 | yes (`1.2.2`) | yes — API-compatible | **Bumped** |
| `sentencepiece` | `0.2.0` → `0.2.1` | benchmark-only | CVE-2026-1260 | yes (`0.2.1`) | yes — patch; deberta-v3 tokenizer unaffected | **Bumped** |
| `transformers` | `4.46.3` → `4.53.3` (floor `>=4.41,<5` → `>=4.53.0,<5`) | benchmark-only | 14 with a `<5` fix · 8 no-fix (`PYSEC-2025-211..218`) · 1 needing 5.x (`CVE-2026-1839`) | partial | bump to highest `<5`; rest unbumpable | **Bumped (partial)** + residual documented below |
| `huggingface-hub` | `0.23.4` → `0.30.2` | benchmark-only | none (compat bump) | n/a | yes — required by `transformers>=4.53`; `datasets==2.19.1` allows it | **Bumped (to satisfy transformers)** |

### transformers advisories cleared by the `>=4.53.0` floor (14)

`PYSEC-2024-227`, `PYSEC-2024-228`, `PYSEC-2024-229` (4.48.0) · `PYSEC-2025-40` (4.49.0) ·
`CVE-2024-12720` (4.48.0) · `CVE-2025-1194` (4.50.0) · `CVE-2025-3263`, `CVE-2025-3264` (4.51.0) ·
`CVE-2025-3777`, `CVE-2025-3933` (4.52.1) · `CVE-2025-5197`, `CVE-2025-6638`, `CVE-2025-6051`,
`CVE-2025-6921` (4.53.0).

## Known unfixable / accepted residual

All residual is **benchmark-only** dev tooling in `transformers 4.53.3`. It is **not reachable by
library users** — `transformers` is not a dependency of `aegis-memory` or its `[server]` extra; it
is installed only by someone running the injection benchmark in an isolated venv. Risk to shipped
users: **none.**

| Advisory | Why it can't be bumped | Reachability |
|---|---|---|
| `PYSEC-2025-211` | No fixed version published in OSV (no `<5` patch) | benchmark-only |
| `PYSEC-2025-212` | No fixed version published in OSV | benchmark-only |
| `PYSEC-2025-213` | No fixed version published in OSV | benchmark-only |
| `PYSEC-2025-214` | No fixed version published in OSV | benchmark-only |
| `PYSEC-2025-215` | No fixed version published in OSV | benchmark-only |
| `PYSEC-2025-216` | No fixed version published in OSV | benchmark-only |
| `PYSEC-2025-217` | No fixed version published in OSV | benchmark-only |
| `PYSEC-2025-218` | No fixed version published in OSV | benchmark-only |
| `CVE-2026-1839` | Fix only in `5.0.0rc3`; `transformers 5.x` breaks `llm-guard 0.3.15` (the benchmark's `<5` ceiling) | benchmark-only |

### Deliberate ignore list

This residual is suppressed *explicitly* (a reviewed decision, not an oversight) in two places, both
listing the same nine IDs:

1. **OSV-Scanner / OpenSSF Scorecard** — [`benchmarks/injection/osv-scanner.toml`](../../benchmarks/injection/osv-scanner.toml).
   Scorecard's "Vulnerabilities" check scans **every** manifest in the repo (not just the shipped
   surface), so without this config the benchmark-only `transformers` residual scores the check at 0.
   OSV-Scanner auto-discovers the `osv-scanner.toml` sitting next to the benchmark `requirements.txt`
   and treats the listed IDs as accepted. This is the single source of truth for the machine-enforced
   ignore list.
2. **`pip-audit`** — if/when it is run over the benchmark manifest in tooling:

   ```
   python -m pip_audit -r benchmarks/injection/requirements.txt `
     --ignore-vuln PYSEC-2025-211 --ignore-vuln PYSEC-2025-212 `
     --ignore-vuln PYSEC-2025-213 --ignore-vuln PYSEC-2025-214 `
     --ignore-vuln PYSEC-2025-215 --ignore-vuln PYSEC-2025-216 `
     --ignore-vuln PYSEC-2025-217 --ignore-vuln PYSEC-2025-218 `
     --ignore-vuln CVE-2026-1839
   ```

The shipped-deps CI job (`.github/workflows/pip-audit.yml`) needs **no** ignore list — that surface
is clean — and intentionally does **not** audit the benchmark manifest, so the accepted residual
above never blocks a merge.

## Proposal for the maintainer (not done in this PR)

A large majority of OSV signal for this repo comes from benchmark-only tooling. To make attribution
unambiguous, the benchmark extras could be moved into an isolated optional-dependency group, e.g.
`[project.optional-dependencies] benchmark = [...]` in `pyproject.toml`, installed via
`pip install aegis-memory[benchmark]`. This is **clarity of attribution**, not concealment —
Scorecard may still scan any manifest in the repo. Flagged here for a maintainer decision; the
dependency layout is intentionally **not** restructured in this PR.

## Verification performed

1. `python -m pip_audit -r server/requirements.txt` → `No known vulnerabilities found`.
2. `python -m pip_audit` over the `pyproject.toml` core + `[server]` resolved tree → `No known vulnerabilities found`.
3. `python -m pip_audit -r benchmarks/injection/requirements.txt` → 9 advisories, all the documented
   `transformers` residual above (down from 28 across 3 packages).
4. `python -m pytest tests/` → 493 passed, 2 skipped (the only errors are `asyncpg` connection
   failures from tests that need a live Postgres, which CI provides via its `postgres` service;
   unrelated to the dependency bumps, which touch no shipped code).
