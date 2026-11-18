# Changelog

## Rebuild 0.2 — engineering hardening

- Bound reconciliation PASS exports to the exact ledger and parameter fingerprints and require fresh recomputation.
- Added strict money parsing, duplicate-header checks, date validation, and broader formula-injection sanitization.
- Added Streamlit session-state invalidation when uploaded data or relevant inputs change.
- Added trial-balance debit/credit equality screening and explicit out-of-balance status.
- Changed §162(f) items to REVIEW_REQUIRED pending statutory exception and identification analysis.
- Withheld long-production-period depreciation cases for separate professional review.
- Changed ambiguous document routing to REVIEW.
- Added synthetic sample-data smoke tests, demo instructions, and CPA-pilot release limitations.


## Phase 1 hardening — 2026-11-17

- Tightened monetary parsing: embedded spaces, repeated currency symbols, trailing symbols and malformed grouping are rejected instead of being normalized into a different amount.
- Enforced unambiguous ISO `YYYY-MM-DD` ledger dates.
- Added a depreciation asset partition helper that reports invalid placed-in-service dates rather than silently excluding those rows in the UI.
- Added regression tests for malformed currency strings, ambiguous dates, invalid calendar dates, asset-date partitioning, explicit boolean threshold flags and null trial-balance labels.

## Phase 1.5 — Pre-deployment hardening

- Added adversarial and boundary tests for monetary parsing, randomized reconciliation arithmetic, spreadsheet formula-prefix sanitization, missing/invalid financial-statement inputs, tax-year type validation, depreciation flag validation, Section 179 election-versus-cost validation, and ambiguous document names.
- Tightened depreciation helper inputs: tax-year arguments must be integer years, boolean flags must be actual booleans in the direct bonus-rate helper, optional CSV boolean fields reject unrecognized values, and requested Section 179 elections cannot exceed the cost supplied to the reference screen.
- Tightened book-to-tax year and entity-type input validation.
- Added a Streamlit configuration upload limit of 10 MB per file and disabled anonymous usage-statistics collection in the demo configuration.
- Re-ran the full standard-library unittest suite: 55 tests passed in the local Python 3.13.5 environment.
- Parsed all 13 Python files and compiled the application, modules, and tests successfully.
- Live Streamlit launch remains unverified because Streamlit is not installed in the current environment. GitHub Actions and Python 3.11 CI remain unverified until the repository is updated and the workflow runs.
- These engineering checks do not validate tax-law assumptions, provide security certification, or establish production readiness.


## Phase 1.6 — Deep testing and pre-deployment review

- Fixed parenthetical currency + sign bypass in `core/reconciliation.py` (`currency_stripper`), where inputs like `($-100)` could bypass sign rejection and negate to `+100`.
- Made `build_depreciation_schedule` 100% JSON-serializable by converting `section_179_reference` limits to strings, rejected `datetime` and non-`YYYY-MM-DD` date strings in `depreciation_schedule._date`, and handled `None` asset names cleanly.
- Aligned `build_book_to_tax_workpaper` `entity_type` validation with `m3_threshold_flags` and normalized `None` descriptions to `""`.
- Updated `app.py` CSV imports to `encoding="utf-8-sig"` for Excel UTF-8 BOM compatibility, switched session-state fingerprints to `json.dumps(...)`, cleared stale `recon_ledger`/`recon_parameters` alongside `recon_result`, and filtered blank categories in Document Organizer.
- Added `tests/test_phase1_6.py` covering cross-module workflows, 5,000-row ledger and 2,000-row trial-balance scale tests, UTF-8 BOM CSVs, JSON-serializability, `app.py` static/state checks, and M-3 boundary thresholds (67 tests passing under Python 3.11.2).
