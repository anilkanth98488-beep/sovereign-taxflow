# Sovereign TaxFlow

**Deterministic Workpaper Preparation & Quality-Control Assistant**

Sovereign TaxFlow is a local demonstration application for structured workpaper preparation: source-data validation, arithmetic ledger reconciliation, explicit trial-balance grouping, draft book-to-tax adjustment support, fixed-asset reference screening, and deterministic document filename routing.

## Scope and professional review

This is **not** tax-filing software, an automated tax calculator, tax/legal advice, an audit opinion, or a guarantee of compliance. A reconciliation `PASS` means only that the defined arithmetic check passed within the selected tolerance. It does not verify the completeness, authenticity, ownership, deductibility, tax treatment, or accuracy of source documents.

Every classification, tax treatment, election, threshold determination, depreciation result, and workpaper requires review and approval by a qualified tax professional. Use synthetic data for demonstrations. Real client data requires an approved secure environment, written authorization, confidentiality controls, access restrictions, retention/deletion procedures, and documented data-processing terms.

## Project structure

```text
sovereign-taxflow/
├── app.py
├── core/
│   └── reconciliation.py
├── modules/
│   ├── financial_statements.py
│   ├── book_to_tax.py
│   ├── depreciation_schedule.py
│   └── document_organizer.py
├── tests/
│   ├── test_reconciliation.py
│   └── test_modules.py
├── sample_data/
├── .github/workflows/python-tests.yml
├── requirements.txt
├── TAX_RULES_AND_LIMITATIONS.md
└── README.md
```

## Modules

- `core/reconciliation.py`: Decimal-only text/integer money parser, duplicate-header validation, date and transaction validation, input fingerprints, recomputation-bound PASS-only XLSX export, and spreadsheet formula-injection sanitization.
- `modules/financial_statements.py`: explicit trial-balance category grouping and debit/credit equality screening. It is not a complete financial statement generator.
- `modules/book_to_tax.py`: proposed adjustment support for selected codes and preliminary M-3 screening. §162(f) amounts are held for review rather than automatically quantified.
- `modules/depreciation_schedule.py`: limited acquisition/placed-in-service date reference helper and 2025/2026 §179 reference ceilings. Long-production-period property is deliberately withheld for separate review; invalid placed-in-service dates are reported, not silently filtered.
- `modules/document_organizer.py`: deterministic filename keyword routing. Ambiguous filenames are sent to `REVIEW`; no AI, OCR, external API or network calls.
- `app.py`: Streamlit interface with CSV imports using `dtype=str`, session-state invalidation when inputs change, and `on_click="ignore"` for XLSX downloads.

## Setup

```bash
python -m venv .venv
# macOS/Linux:
source .venv/bin/activate
# Windows:
# .venv\\Scripts\\activate
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
streamlit run app.py
```

## Sample CSV schemas

- Reconciliation: `Date,Amount,Type`; dates must be unambiguous ISO `YYYY-MM-DD`; Type is `CREDIT` or `DEBIT`.
- Trial balance: `Account,Debit,Credit,Statement,Category`; Statement is `P&L` or `BALANCE SHEET`.
- Book-to-tax: `code,amount,description`; supported codes are `FINES_162F`, `MEALS_274N`, `CONVENIENCE_MEALS_274O`, and `MUNI_INTEREST_103`.
- Assets: `asset,cost,acquisition_date,placed_in_service_date`; optional columns include `long_production_period` and `binding_contract_before_cutoff`.

All CSV imports use `dtype=str` to avoid premature float conversion. The strict money parser rejects floats, booleans, missing values, malformed grouping, NaN and Infinity. High-precision values must originate in text-formatted source cells; precision already lost by Excel or an upstream system cannot be restored.

## Important engineering controls

- Reconciliation XLSX export recomputes the current ledger and verifies the supplied PASS result against input and parameter fingerprints.
- The Streamlit app invalidates previous results when the uploaded file or relevant parameters change.
- XLSX workpaper values are exported as text to preserve exact decimal strings; untrusted text is sanitized against spreadsheet formula injection.
- No module silently converts invalid money to zero.

## Tax-law and calculation limitations

See `TAX_RULES_AND_LIMITATIONS.md`. The reference values in code are limited screening assumptions, not a complete or independently certified implementation of tax law. Verify statutes, current IRS forms/instructions, effective dates, elections, exceptions, and entity-specific rules for the relevant tax year before using outputs.

Not implemented: full MACRS tables, complete bonus depreciation qualification, binding-contract/long-production-period analysis, full §179 taxable-income limitation, complete Schedule M-1/M-3 calculations, tax return line mapping, OCR, document-content classification, e-filing, cloud storage, integrations, access control, or a production audit log.

## Pre-pilot release checklist

Before any CPA-firm pilot: independent code review; CPA-approved test cases; tax-law review for each tax year; security/privacy review; access controls; audit logging; data retention/deletion controls; written client authorization; backup/recovery plan; dependency vulnerability review; and validation against CPA-prepared sample workpapers.
