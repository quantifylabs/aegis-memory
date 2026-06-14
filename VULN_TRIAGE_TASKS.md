# Task: Triage and remediate dependency vulnerabilities (Scorecard Vulnerabilities check)

Repo: `quantifylabs/aegis-memory`. The OpenSSF Scorecard **Vulnerabilities** check scores
**0 (HIGH weight)** — `scorecard.dev` reports **53 known vulnerabilities** detected via OSV
across the resolved dependency tree. This is the single biggest remaining drag on the
aggregate Scorecard (currently 7.2) and, more importantly, it is publicly visible at
`scorecard.dev/viewer/?uri=github.com/quantifylabs/aegis-memory` — an open 53-vuln count
undercuts the "security-credible" positioning the injection benchmark and forthcoming arXiv
preprint are built on. Fix the real ones, separate the noise, document the rest.

**Do not panic-bump 53 packages.** Most of these are transitive and many are benchmark/dev-only
or duplicate advisory IDs for one package. The goal is a *triaged, justified* remediation, not a
blind mass upgrade that breaks the build.

**Branch protection is on.** Feature branch → PR → CI green → squash-merge. Produce (do not run)
the PowerShell-friendly handoff commands at the end. Do NOT edit the main README.

---

## Context: what the 53 likely are (verify, don't assume)

Scorecard runs OSV against the *entire* resolved dependency tree it can reach in the repo, which
includes:
- `server/requirements.txt` — the **shipped library** dependencies. **These matter most** — they
  affect anyone installing `aegis-memory` from PyPI.
- `benchmarks/injection/requirements.txt` — **benchmark/dev-only** extras (transformers, torch,
  datasets, llm-guard, etc.). Vulnerabilities here do NOT endanger library users; they are dev
  tooling. Lower priority, and a candidate for isolation so they stop polluting the signal.
- Any other `requirements*.txt`, `pyproject.toml`, `setup.py`, or lockfiles in the repo.

Observed patterns in the Scorecard output that inform triage:
- Old IDs (PYSEC-2017/2018/2019/2021) → deep transitive deps pinned to old versions, almost
  certainly not first-order.
- Sequential clusters (PYSEC-2025-211 through -218, -203 through -209) → frequently a *single
  package* with many advisory IDs, or one ecosystem batch — likely far fewer than N distinct
  packages to fix.

So the real question is not "53 vulns" but "how many distinct *shipped-dependency* packages need
a bump, and is a safe fixed version available for each."

---

## Step 1 — Inventory and attribute (do this first, report before fixing)

1. Enumerate every dependency manifest in the repo (`server/requirements.txt`,
   `benchmarks/injection/requirements.txt`, `pyproject.toml`, any others). List them.
2. Run a **scoped** audit on the shipped deps specifically:
   ```
   python -m pip_audit -r server/requirements.txt
   ```
   (Use `python -m pip_audit` — the script dir is not on PATH in this Windows/PowerShell env.)
   Then run it separately on the benchmark extras:
   ```
   python -m pip_audit -r benchmarks/injection/requirements.txt
   ```
   And, if it exists, the project itself / any lockfile. Use `--desc` for context if helpful.
3. Produce a triage table (write it to `docs/security/vuln-triage.md`) with one row per distinct
   vulnerable package — NOT one row per advisory ID — with columns:
   - Package, current version, manifest it comes from (shipped vs benchmark-only vs transitive),
     advisory IDs (grouped), severity, fixed version available (y/n + version), bump safe? (does
     it stay within the existing version constraints / not break imports), proposed action.
4. Collapse the duplicate-ID clusters: if PYSEC-2025-211..218 are all one package, say so. Report
   the **distinct-package count**, which is the number that actually matters.

**Stop after Step 1 and surface the triage table.** Do not start bumping until the attribution
is clear — the fix strategy depends entirely on how many are shipped-deps vs benchmark-only.

---

## Step 2 — Remediate, in priority order

Apply fixes in this order, most important first:

1. **Shipped-dependency vulns with a safe fixed version** → bump the pin in
   `server/requirements.txt` to the fixed version. These are the ones that protect actual library
   users and move the Scorecard check the most. After each bump, confirm the package still imports
   and the existing test suite passes (`python -m pytest tests/`).
2. **Benchmark/dev-only vulns with a safe fix** → bump in `benchmarks/injection/requirements.txt`.
   Lower stakes (no library-user impact) but still clears Scorecard signal and is usually free.
3. **Vulns with no fix available, or where the only fix is a breaking major-version bump** → do
   NOT force the bump. Document them (see Step 3). A broken build is worse than a documented,
   un-fixable transitive advisory.
4. **Transitive vulns** where the direct parent has a newer release that pulls a patched child →
   bump the parent. Where it doesn't, document.

Constraints:
- Respect existing version ceilings / compatibility. If `aegis-memory` declares `<X` for a dep,
  don't blow past it without checking the reason.
- Bump conservatively — prefer the **minimum** version that clears the advisory, not "latest."
- Re-run `python -m pip_audit -r server/requirements.txt` after the shipped-dep bumps and confirm
  the shipped count drops to zero (or to only documented no-fix entries).
- Run `python -m pytest tests/` after bumps to confirm nothing broke.

---

## Step 3 — Document the residual (so the check and the story are both honest)

For anything that can't be safely fixed (no patch released, or breaking fix), record it explicitly
rather than leaving it silent:

- In `docs/security/vuln-triage.md`, a "Known unfixable / accepted" section: package, advisory ID,
  why it can't be bumped (no fix / breaking), whether it's reachable in the shipped library or
  benchmark-only, and the risk assessment (e.g. "benchmark-only dev dependency, not shipped to
  PyPI users").
- If `pip-audit` is wired into CI or you want it to be, add an ignore list with justifications
  (e.g. `pip-audit --ignore-vuln <ID>` documented inline) so the residual is a *deliberate,
  reviewed* decision, not an oversight. Do not silently ignore — every ignore needs a one-line
  reason in the triage doc.
- Cross-reference `SECURITY.md` if it should point to this triage doc.

---

## Step 4 — (Optional, flag don't auto-do) Isolate benchmark deps from the security signal

If a large share of the 53 turn out to be benchmark-only, consider moving the benchmark extras out
of a top-level scanned `requirements.txt` into an isolated optional-dependency group (e.g. a
`[project.optional-dependencies] benchmark = [...]` group in `pyproject.toml`, or keeping them in
`benchmarks/injection/requirements.txt` clearly separated). Note: Scorecard may still scan files in
the repo, so this is about *clarity of attribution*, not necessarily hiding them from OSV. **Propose
this in the triage doc and let the maintainer decide** — do not restructure dependency layout
unilaterally in this PR.

---

## Verification

1. `python -m pip_audit -r server/requirements.txt` → zero vulns, or only documented no-fix entries.
2. `python -m pytest tests/` → all pass after bumps (no regressions from version changes).
3. `docs/security/vuln-triage.md` exists with the distinct-package triage table, the priority of
   what was fixed, and the documented residual.
4. Confirm no changes leaked outside dependency manifests + the triage doc (+ `pyproject.toml`/
   `SECURITY.md` only if intentionally touched).

Note: the Scorecard score itself updates on its own schedule after the PR merges — don't expect the
viewer to refresh instantly. The local `pip-audit` result is your ground truth for this PR.

---

## Honesty / scope guardrails

- The number that matters is **distinct shipped-dependency packages with available fixes**, not the
  raw advisory count. Lead the triage doc with that.
- Do not overstate the fix. If 40 of 53 are benchmark-only or unfixable transitive, say exactly
  that — an honest "we fixed all N shipped-library vulns; the residual M are benchmark-dev-only and
  documented" is stronger and more defensible than a vague "fixed vulnerabilities."
- Conservative bumps only. A green Scorecard with a broken install helps no one.

---

## Handoff (produce, do NOT run)

Emit a single PowerShell-friendly block (no Bash heredocs, no `\` continuations, one git command
per line; PR body via a here-string to a temp file passed with `--body-file`). Branch:
`fix/dependency-vulnerabilities`. Suggested title:
`fix(deps): remediate known dependency vulnerabilities and document residual`.
Do NOT push, open the PR, edit the main README, or create a release.
