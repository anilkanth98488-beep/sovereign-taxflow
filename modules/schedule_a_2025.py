"""2025 U.S. Federal Schedule A (Itemized vs. Standard Deduction) workpaper screen.

Implements IRC §213(a) medical-expense 7.5% AGI floor and reference Schedule A
line aggregation using 64-digit MONEY_CONTEXT. Standard deduction and SALT cap
values are reference placeholders requiring CPA verification against 2025 IRS instructions.
"""
from __future__ import annotations

from decimal import Decimal, localcontext
from typing import Any

from core.reconciliation import InputValidationError, MONEY_CONTEXT, currency_stripper

ZERO = Decimal("0")

STANDARD_DEDUCTION_2025_REFERENCE = {
    "single": Decimal("15000"),
    "married_filing_separately": Decimal("15000"),
    "married_filing_jointly": Decimal("30000"),
    "qualifying_surviving_spouse": Decimal("30000"),
    "head_of_household": Decimal("22500"),
}


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def _parse_nonneg(value: Any, label: str) -> Decimal:
    amt = currency_stripper(value)
    if amt < ZERO:
        raise InputValidationError(f"{label} cannot be negative.")
    return amt


def build_schedule_a_workpaper(
    *,
    tax_year: int = 2025,
    filing_status: str | None = None,
    agi: Any = None,
    eligible_medical_expenses: Any = "0",
    medical_reimbursements: Any = "0",
    state_and_local_taxes_paid: Any = "0",
    salt_cap: Any = "10000",
    mortgage_interest: Any = "0",
    charitable_contributions: Any = "0",
) -> dict[str, Any]:
    """Compute a 2025 Schedule A itemized vs. standard deduction reference workpaper."""
    if type(tax_year) is not int or tax_year != 2025:
        raise InputValidationError("Configured Schedule A reference year is 2025 only.")

    missing_fields: list[str] = []
    if _is_blank(filing_status):
        missing_fields.append("filing_status")
    if _is_blank(agi):
        missing_fields.append("agi")
    if missing_fields:
        return {
            "rule_id": "schedule_a_2025",
            "tax_year": tax_year,
            "status": "REVIEW_REQUIRED",
            "missing_fields": missing_fields,
            "deduction_recommendation": "REVIEW_REQUIRED",
            "review_note": f"Missing required input(s): {', '.join(missing_fields)}. Supply confirmed 2025 Form 1040 line 11b AGI and filing status.",
        }

    if not isinstance(filing_status, str):
        raise InputValidationError("filing_status must be a string.")
    status_key = filing_status.strip().lower().replace(" ", "_")
    if status_key not in STANDARD_DEDUCTION_2025_REFERENCE:
        raise InputValidationError(f"Unsupported filing_status: {filing_status!r}")

    with localcontext(MONEY_CONTEXT):
        agi_val = _parse_nonneg(agi, "agi")
        med_gross = _parse_nonneg(eligible_medical_expenses, "eligible_medical_expenses")
        med_reimb = _parse_nonneg(medical_reimbursements, "medical_reimbursements")
        if med_reimb > med_gross:
            raise InputValidationError("medical_reimbursements cannot exceed eligible_medical_expenses.")
        salt_paid = _parse_nonneg(state_and_local_taxes_paid, "state_and_local_taxes_paid")
        salt_limit = _parse_nonneg(salt_cap, "salt_cap")
        mort_int = _parse_nonneg(mortgage_interest, "mortgage_interest")
        charity = _parse_nonneg(charitable_contributions, "charitable_contributions")

        # IRC §213(a): net unreimbursed medical expenses exceeding 7.5% of AGI
        med_net = med_gross - med_reimb
        med_floor = agi_val * Decimal("0.075")
        med_deductible = max(ZERO, med_net - med_floor)

        salt_deductible = min(salt_paid, salt_limit)
        total_itemized = med_deductible + salt_deductible + mort_int + charity
        std_ded = STANDARD_DEDUCTION_2025_REFERENCE[status_key]
        excess_over_standard = total_itemized - std_ded

        return {
            "rule_id": "schedule_a_2025",
            "tax_year": tax_year,
            "filing_status": status_key,
            "status": "CALCULATED",
            "agi": str(agi_val),
            "medical_expenses": {
                "gross_eligible": str(med_gross),
                "reimbursements": str(med_reimb),
                "net_unreimbursed": str(med_net),
                "agi_7_5pct_floor": str(med_floor),
                "schedule_a_line_4": str(med_deductible),
            },
            "salt_deductible": str(salt_deductible),
            "mortgage_interest": str(mort_int),
            "charitable_contributions": str(charity),
            "total_itemized_deductions": str(total_itemized),
            "standard_deduction_reference": str(std_ded),
            "itemized_minus_standard": str(excess_over_standard),
            "deduction_recommendation": "ITEMIZE" if total_itemized > std_ded else "STANDARD_DEDUCTION",
            "review_note": "Reference workpaper only. Verify 2025 standard deduction, SALT cap, charitable AGI limits, and medical substantiation against current IRS instructions.",
        }
