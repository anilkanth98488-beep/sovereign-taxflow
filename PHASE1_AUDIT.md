# Sovereign TaxFlow — Phase 1 Engineering Audit

Audit date: 2026-11-17  
Source baseline: `sovereign-taxflow-release-candidate.zip` plus the latest individually uploaded source files (`app(4).py`, `reconciliation(3).py`, and the four module files).

## Scope

This Phase 1 pass preserves the existing five-module architecture and focuses on engineering correctness, input validation, regression tests, and sample-data handling. It is not a tax-law opinion, security certification, or production-readiness assessment.

## Baseline verification

- The extracted release candidate contained the expected `core/`, `modules/`, `tests/`, `sample_data/`, Streamlit app, documentation, requirements, and GitHub Actions workflow.
- The uploaded `app(4).py`, `reconciliation(3).py`, `book_to_tax(1).py`, `depreciation_schedule(1).py`, and `financial_statements(1).py` matched the release-candidate copies byte-for-byte.
- The release candidate contained a newer `document_organizer.py` than the individually uploaded copy. The newer version fixes the `1120-S` versus `1120` token collision and was retained.
- Baseline test suite: 35 tests passed.

## Phase 1 fixes applied

1. **Strict monetary parsing**
   - Rejects embedded whitespace such as `1 2` rather than silently converting it to `12`.
   - Rejects repeated or trailing currency symbols such as `$1$2`, `$$1`, and `1$`.
   - Rejects malformed comma grouping.
   - Accepts supported conventional forms such as `$1,234.56`, `-$1,234.56`, `$-1,234.56`, and `(1,234.56)`.
   - Continues to reject floats, booleans, missing values, NaN and Infinity.

2. **Unambiguous ledger dates**
   - Ledger dates must be ISO `YYYY-MM-DD` values.
   - Ambiguous locale dates and invalid calendar dates are rejected as input errors.

3. **Depreciation date partitioning**
   - Added `partition_assets_by_tax_year`.
   - The UI no longer silently drops invalid placed-in-service dates by checking only a string prefix.
   - Invalid rows are displayed and the workpaper is withheld until the rows are corrected.

4. **Additional validation**
   - M-3 reportable-partner flag must be an actual boolean, not a truthy string such as `"False"`.
   - Trial-balance account/category null values are rejected.

5. **Regression tests**
   - Added tests for malformed money strings, ambiguous and invalid dates, invalid asset-date reporting, strict boolean flags, null trial-balance labels, and XLSX text precision.

## Verification results

- `python -m unittest discover -s tests -v`: **38 tests passed**.
- `python -m compileall -q app.py core modules tests`: **passed**.
- Sample ledger: **PASS**, calculated closing balance `1250.00` from opening `1000.00`, credits `300.00`, debits `50.00`.
- Sample trial balance: **OUT OF BALANCE**, debit-credit difference `-750.00`; correctly flagged, not silently accepted.
- Sample book-to-tax: §162(f) item remains `REVIEW_REQUIRED`.
- Sample depreciation data: split by placed-in-service year; invalid dates now have an explicit reporting path.
- XLSX export test confirms high-precision monetary values are stored as text.

## Verification limitations

- Local runtime: Python 3.13.5, pandas 2.2.3, openpyxl 3.1.5.
- Streamlit is not installed in this execution environment. An installation attempt could not reach the package index because network name resolution is unavailable. Therefore the Streamlit app was syntax-compiled but **not launched interactively** here.
- The repository GitHub Actions workflow targets Python 3.11. A GitHub-hosted run has not been performed; local tests ran under Python 3.13.5.
- Tax-law assumptions and statutory thresholds were not independently researched or certified in this engineering phase. The tax modules remain preliminary workpaper support and require qualified tax-professional review.
- No penetration test, privacy assessment, formal security audit, or CPA pilot has been completed.

## Remaining Phase 1 release gates

- Run the included workflow on GitHub Actions under Python 3.11.
- Install requirements in a clean environment and launch Streamlit.
- Manually test all five tabs, including upload changes and stale-result invalidation.
- Have a qualified U.S. tax professional review the tax-year assumptions and outputs before any client use.

## Product boundary

Sovereign TaxFlow remains a **Deterministic Workpaper Preparation & Quality-Control Assistant**. It is not tax-filing software, an automated tax calculator, tax/legal advice, an audit opinion, or a guarantee of compliance.
