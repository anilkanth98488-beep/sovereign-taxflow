# Sovereign TaxFlow — Phase 1.5 Pre-deployment Engineering Report

## Scope

The Phase 1 release ZIP was extracted and reviewed before any GitHub, Codespaces, or Streamlit deployment. The existing five-module architecture was retained.

## Changes made

1. Added `tests/test_adversarial.py` with adversarial, boundary, and deterministic randomized tests.
2. Tightened depreciation input handling:
   - Reject boolean values masquerading as integer tax years.
   - Require actual booleans for direct bonus-rate flags.
   - Parse optional CSV boolean fields explicitly and reject unrecognized values rather than silently treating them as false.
   - Reject a requested Section 179 election amount above the total cost supplied to the reference helper.
3. Tightened book-to-tax tax-year and entity-type validation.
4. Added `.streamlit/config.toml` with a 10 MB per-file upload limit and usage-statistics collection disabled for the demonstration app.
5. Updated `CHANGELOG.md`.

## Verification executed

| Check | Result |
|---|---|
| Existing and new unit tests | 55 passed, 0 failed |
| Python bytecode compilation | Passed |
| AST parsing | 13 Python files passed |
| Sample-data tests | Passed |
| Python environment | 3.13.5 |
| Streamlit runtime | Not available; live app launch not tested |
| GitHub Actions / Python 3.11 | Not run; requires GitHub push/workflow execution |

`python -m pip check` reported an environment-level conflict: installed `moviepy 2.2.1` requires `pillow<12.0,>=9.2.0`, while the shared environment has Pillow 12.3.0. This is not a dependency declared by Sovereign TaxFlow's requirements file, but it is recorded rather than ignored.

## Additional tests added

- Currency parser rejects malformed grouping, embedded whitespace, repeated/trailing currency symbols, contradictory signs, scientific notation, NaN, and Infinity.
- Currency parser accepts supported positive, negative, parenthetical, and grouped formats.
- 50 seeded randomized reconciliation arithmetic scenarios.
- Missing and empty ledger inputs.
- Spreadsheet formula-prefix neutralization, including leading tab and BOM cases.
- Invalid and empty financial-statement input cases.
- Boolean tax-year rejection and invalid entity checks.
- Negative M-3 inputs and non-boolean partnership flag rejection.
- Section 179 election-versus-cost and flag validation.
- Depreciation invalid flags, invalid years, invalid amounts, and unknown boolean text.
- Ambiguous document names and unsupported missing-item form.

## Known limitations and items not claimed

- No live Streamlit runtime test was possible in this environment.
- No GitHub Actions run has occurred yet.
- No Python 3.11 local run has been performed.
- No browser/UI automation, load test, penetration test, dependency vulnerability audit, privacy assessment, or independent security review has been completed.
- No IRS/tax-law validation or CPA review has been completed. Tax-law constants, thresholds, bonus depreciation, Section 179, meals, M-3 screens, and book-to-tax assumptions remain reference-only and must be checked against current primary sources and professional judgment before client use.
- No real taxpayer data should be uploaded to the demo.
- The 10 MB upload cap is a demonstration guardrail, not a complete defense against denial-of-service or malicious files.

## Release decision

**Pre-deployment engineering package prepared; not yet production-ready.**

The 55 passing tests demonstrate only the tested software behaviors. Next steps are repository backup, upload, GitHub Actions verification, dependency installation in the target environment, and live Streamlit smoke testing with synthetic data.
