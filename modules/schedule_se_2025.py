"""2025 Schedule C net-profit and Schedule SE self-employment tax workpaper.

Deterministic arithmetic using 64-digit MONEY_CONTEXT. The 2025 Social Security
wage base ($176,100) is a reference constant requiring CPA verification against
official 2025 IRS Schedule SE instructions.
"""
from __future__ import annotations

from decimal import Decimal, localcontext
from typing import Any

from core.reconciliation import InputValidationError, MONEY_CONTEXT, currency_stripper

ZERO = Decimal("0")
SS_WAGE_BASE_2025_REFERENCE = Decimal("176100")
ADDITIONAL_MEDICARE_THRESHOLDS = {
    "single": Decimal("200000"),
    "head_of_household": Decimal("200000"),
    "qualifying_surviving_spouse": Decimal("200000"),
    "married_filing_jointly": Decimal("250000"),
    "married_filing_separately": Decimal("125000"),
}


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def _parse_nonneg(value: Any, label: str) -> Decimal:
    amt = currency_stripper(value)
    if amt < ZERO:
        raise InputValidationError(f"{label} cannot be negative.")
    return amt


def build_schedule_se_workpaper(
    *,
    tax_year: int = 2025,
    filing_status: str | None = None,
    gross_receipts: Any = None,
    returns_and_allowances: Any = "0",
    deductible_expenses: Any = "0",
    w2_social_security_wages: Any = "0",
    w2_medicare_wages: Any = "0",
) -> dict[str, Any]:
    """Compute 2025 Schedule C net profit, Schedule SE tax, and Schedule 1 line 15 deduction."""
    if type(tax_year) is not int or tax_year != 2025:
        raise InputValidationError("Configured Schedule SE reference year is 2025 only.")

    missing_fields: list[str] = []
    if _is_blank(filing_status):
        missing_fields.append("filing_status")
    if _is_blank(gross_receipts):
        missing_fields.append("gross_receipts")
    if missing_fields:
        return {
            "rule_id": "schedule_se_2025",
            "tax_year": tax_year,
            "status": "REVIEW_REQUIRED",
            "missing_fields": missing_fields,
            "review_note": f"Missing required input(s): {', '.join(missing_fields)}.",
        }

    if not isinstance(filing_status, str):
        raise InputValidationError("filing_status must be a string.")
    status_key = filing_status.strip().lower().replace(" ", "_")
    if status_key not in ADDITIONAL_MEDICARE_THRESHOLDS:
        raise InputValidationError(f"Unsupported filing_status: {filing_status!r}")

    with localcontext(MONEY_CONTEXT):
        gross = _parse_nonneg(gross_receipts, "gross_receipts")
        returns = _parse_nonneg(returns_and_allowances, "returns_and_allowances")
        expenses = _parse_nonneg(deductible_expenses, "deductible_expenses")
        w2_ss = _parse_nonneg(w2_social_security_wages, "w2_social_security_wages")
        w2_med = _parse_nonneg(w2_medicare_wages, "w2_medicare_wages")

        net_profit = gross - returns - expenses
        if net_profit <= ZERO:
            return {
                "rule_id": "schedule_se_2025",
                "tax_year": tax_year,
                "filing_status": status_key,
                "status": "CALCULATED" if net_profit == ZERO else "REVIEW_REQUIRED",
                "schedule_c_net_profit": str(net_profit),
                "net_earnings_from_se": "0",
                "social_security_tax": "0",
                "medicare_tax": "0",
                "total_se_tax": "0",
                "deductible_half_se_tax_line_15": "0",
                "additional_medicare_review_required": False,
                "review_note": "Zero or net loss on Schedule C produces $0 Schedule SE tax; confirm loss/hobby/at-risk rules if net profit < 0.",
            }

        net_earnings = net_profit * Decimal("0.9235")
        if net_earnings < Decimal("400"):
            return {
                "rule_id": "schedule_se_2025",
                "tax_year": tax_year,
                "filing_status": status_key,
                "status": "CALCULATED",
                "schedule_c_net_profit": str(net_profit),
                "net_earnings_from_se": str(net_earnings),
                "social_security_tax": "0",
                "medicare_tax": "0",
                "total_se_tax": "0",
                "deductible_half_se_tax_line_15": "0",
                "additional_medicare_review_required": False,
                "review_note": "Net earnings from self-employment under $400 threshold; no Schedule SE tax applies.",
            }

        remaining_ss_base = max(ZERO, SS_WAGE_BASE_2025_REFERENCE - w2_ss)
        taxable_ss_se = min(net_earnings, remaining_ss_base)
        ss_tax = taxable_ss_se * Decimal("0.124")
        medicare_tax = net_earnings * Decimal("0.029")
        total_se_tax = ss_tax + medicare_tax
        half_se_deduction = total_se_tax * Decimal("0.5")

        combined_med_earnings = w2_med + net_earnings
        addl_med_threshold = ADDITIONAL_MEDICARE_THRESHOLDS[status_key]
        addl_med_review = combined_med_earnings > addl_med_threshold

        return {
            "rule_id": "schedule_se_2025",
            "tax_year": tax_year,
            "filing_status": status_key,
            "status": "REVIEW_REQUIRED" if addl_med_review else "CALCULATED",
            "schedule_c_net_profit": str(net_profit),
            "net_earnings_from_se": str(net_earnings),
            "ss_wage_base_reference": str(SS_WAGE_BASE_2025_REFERENCE),
            "taxable_ss_se_earnings": str(taxable_ss_se),
            "social_security_tax": str(ss_tax),
            "medicare_tax": str(medicare_tax),
            "total_se_tax": str(total_se_tax),
            "deductible_half_se_tax_line_15": str(half_se_deduction),
            "additional_medicare_review_required": addl_med_review,
            "review_note": (
                "Combined Medicare wages and SE net earnings exceed Form 8959 threshold; complete Form 8959 Additional Medicare Tax."
                if addl_med_review
                else "Reference workpaper only. Verify 2025 Social Security wage base ($176,100) and Schedule C expense substantiation."
            ),
        }
