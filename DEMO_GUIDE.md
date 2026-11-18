# Sovereign TaxFlow — CPA firm demonstration guide

## Positioning

**Sovereign TaxFlow is a Deterministic Workpaper Preparation & Quality-Control Assistant.** It organizes and validates source data and prepares draft workpapers for qualified professional review. It does not prepare or file tax returns, make final tax determinations, provide tax advice, or issue an audit opinion.

## Three-minute demo flow

### 1. Reconciliation (about 45 seconds)
- Open the Reconciliation tab.
- Upload `sample_data/sample_ledger.csv`.
- Use opening balance `1000.00`, expected closing `1250.00`, and tolerance `0.01`.
- Run reconciliation. Explain that PASS confirms only the defined arithmetic movement.
- Download the PASS-gated XLSX workpaper.
- Change the expected closing balance to `1251.00`; show that the old result is invalidated and the new result must be calculated.

### 2. Trial balance (about 35 seconds)
- Upload `sample_data/sample_trial_balance.csv`.
- Build draft statements.
- Explain that the sample is intentionally out of balance by $750 and the software flags it rather than hiding the difference.

### 3. Book-to-tax support (about 45 seconds)
- Upload `sample_data/sample_book_to_tax.csv`.
- Select 2026 and build the draft workpaper.
- Point out that the fines/penalties amount is marked `REVIEW_REQUIRED`, not silently treated as a confirmed adjustment.
- Explain that meal and municipal-interest lines are provisional classifications requiring CPA substantiation.

### 4. Depreciation reference (about 35 seconds)
- Upload `sample_data/sample_assets.csv`.
- Select 2025 or 2026; the app filters rows to the selected placed-in-service year and reports excluded rows.
- Explain that this is a date-based reference screen, not a complete MACRS calculation. Long-production-period property is sent for separate review.

### 5. Document organizer (about 20 seconds)
- Paste sample filenames containing explicit form tokens, such as `Client_1040_W2.pdf` or `Partnership_1065_K1.pdf`.
- Show that ambiguous names such as `Generic_K1.pdf` are routed to REVIEW.

## Suggested CPA discovery questions

1. Which monthly/quarterly workpaper tasks consume the most staff time?
2. Which source formats are most common (QuickBooks exports, bank CSVs, trial balances, Excel workbooks)?
3. What validations should happen before a preparer starts work?
4. Which exceptions should be escalated to a reviewer?
5. What evidence, source links, reviewer notes and sign-offs must be retained?
6. What security, data residency, retention, access and vendor review requirements apply?

## Demo safety

Use only the synthetic sample data included in this repository. Do not use live client records in an unapproved environment. Do not claim IRS approval, CPA certification, audit-grade status, complete tax compliance, or guaranteed accuracy.
