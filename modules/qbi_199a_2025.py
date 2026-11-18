"""2025 IRC §199A Qualified Business Income (Form 8995 Simplified) workpaper.

Deterministic arithmetic using 64-digit MONEY_CONTEXT. The 2025 taxable-income
phase-in thresholds ($197,300 / $394,600 MFJ) are reference placeholders
requiring CPA verification against 2025 IRS Form 8995 / 8995-A instructions.
"""
from __future__ import annotations

from decimal import Decimal, localcontext
from typing import Any

from core.reconciliation import InputValidationError, MONEY_CONTEXT, currency_stripper

ZERO = Decimal("0")
QBI_THRESHOLD_2025_REFERENCE = {
    "single": Decimal("197300"),
    "head_of_household": Decimal("197300"),
    "qualifying_surviving_spouse": Decimal("197300"),
    "married_filing_separately": Decimal("197300"),
    "married_filing_jointly": Decimal("394600"),
}


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def _parse_nonneg(value: Any, label: str) -> Decimal:
    amt = currency_stripper(value)
    if amt < ZERO:
        raise InputValidationError(f"{label} cannot be negative.")
    return amt


def build_qbi_199a_workpaper(
    *,
    tax_year: int = 2025,
    filing_status: str | None = None,
    qualified_business_income: Any = None,
    taxable_income_before_qbi: Any = None,
    net_capital_gain: Any = "0",
    prior_year_qbi_loss_carryforward: Any = "0",
) -> dict[str, Any]:
    """Compute 2025 Form 8995 simplified §199A QBI deduction or flag Form 8995-A review."""
    if type(tax_year) is not int or tax_year != 2025:
        raise InputValidationError("Configured §199A QBI reference year is 2025 only.")
    missing = [
        name for name, val in (
            ("filing_status", filing_status),
            ("qualified_business_income", qualified_business_income),
            ("taxable_income_before_qbi", taxable_income_before_qbi),
        )
        if _is_blank(val)
    ]
    if missing:
        return {
            "rule_id": "qbi_199a_2025",
            "tax_year": tax_year,
            "status": "REVIEW_REQUIRED",
            "missing_fields": missing,
            "review_note": f"Missing required input(s): {', '.join(missing)}.",
        }
    if not isinstance(filing_status, str):
        raise InputValidationError("filing_status must be a string.")
    status_key = filing_status.strip().lower().replace(" ", "_")
    if status_key not in QBI_THRESHOLD_2025_REFERENCE:
        raise InputValidationError(f"Unsupported filing_status: {filing_status!r}")

    with localcontext(MONEY_CONTEXT):
        qbi_raw = currency_stripper(qualified_business_income)
        ti_before = _parse_nonneg(taxable_income_before_qbi, "taxable_income_before_qbi")
        cap_gain = _parse_nonneg(net_capital_gain, "net_capital_gain")
        loss_cf = _parse_nonneg(prior_year_qbi_loss_carryforward, "prior_year_qbi_loss_carryforward")

        threshold = QBI_THRESHOLD_2025_REFERENCE[status_key]
        if ti_before > threshold:
            return {
                "rule_id": "qbi_199a_2025",
                "tax_year": tax_year,
                "filing_status": status_key,
                "status": "REVIEW_REQUIRED",
                "taxable_income_before_qbi": str(ti_before),
                "threshold_reference": str(threshold),
                "qbi_deduction_line_13": None,
                "review_note": "Taxable income exceeds 2025 simplified Form 8995 threshold; Form 8995-A W-2 wage/UBIA and SSTB testing required.",
            }

        net_qbi = qbi_raw - loss_cf
        if net_qbi <= ZERO:
            return {
                "rule_id": "qbi_199a_2025",
                "tax_year": tax_year,
                "filing_status": status_key,
                "status": "CALCULATED",
                "net_qbi": str(net_qbi),
                "qbi_deduction_line_13": "0",
                "qbi_loss_carryforward_to_2026": str(abs(net_qbi)),
                "review_note": "Net QBI is zero or negative; $0 deduction for 2025 and loss carries forward.",
            }

        qbi_component = net_qbi * Decimal("0.20")
        ti_less_cap_gain = max(ZERO, ti_before - cap_gain)
        ti_limitation = ti_less_cap_gain * Decimal("0.20")
        deduction = min(qbi_component, ti_limitation)

        return {
            "rule_id": "qbi_199a_2025",
            "tax_year": tax_year,
            "filing_status": status_key,
            "status": "CALCULATED",
            "net_qbi": str(net_qbi),
            "qbi_20_percent": str(qbi_component),
            "taxable_income_limitation": str(ti_limitation),
            "qbi_deduction_line_13": str(deduction),
            "qbi_loss_carryforward_to_2026": "0",
            "review_note": "Simplified Form 8995 reference calculation only. Verify SSTB, REIT/PTP, and §199A eligibility.",
        }
