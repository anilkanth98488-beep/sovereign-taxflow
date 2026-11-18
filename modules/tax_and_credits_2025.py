"""2025 Form 1040 ordinary tax-bracket and Child Tax Credit reference workpaper.

Deterministic arithmetic using 64-digit MONEY_CONTEXT. Bracket thresholds and
credit amounts are reference placeholders requiring CPA verification against
official 2025 IRS Form 1040 and Schedule 8812 instructions.
"""
from __future__ import annotations

from decimal import Decimal, localcontext
import math
from typing import Any

from core.reconciliation import InputValidationError, MONEY_CONTEXT, currency_stripper

ZERO = Decimal("0")

# Reference 2025 ordinary income tax brackets (upper bound, rate)
BRACKETS_2025_REFERENCE: dict[str, tuple[tuple[Decimal | None, Decimal], ...]] = {
    "single": (
        (Decimal("11925"), Decimal("0.10")),
        (Decimal("48475"), Decimal("0.12")),
        (Decimal("103350"), Decimal("0.22")),
        (Decimal("197300"), Decimal("0.24")),
        (Decimal("250525"), Decimal("0.32")),
        (Decimal("626350"), Decimal("0.35")),
        (None, Decimal("0.37")),
    ),
    "married_filing_jointly": (
        (Decimal("23850"), Decimal("0.10")),
        (Decimal("96950"), Decimal("0.12")),
        (Decimal("206700"), Decimal("0.22")),
        (Decimal("394600"), Decimal("0.24")),
        (Decimal("501050"), Decimal("0.32")),
        (Decimal("751600"), Decimal("0.35")),
        (None, Decimal("0.37")),
    ),
    "qualifying_surviving_spouse": (
        (Decimal("23850"), Decimal("0.10")),
        (Decimal("96950"), Decimal("0.12")),
        (Decimal("206700"), Decimal("0.22")),
        (Decimal("394600"), Decimal("0.24")),
        (Decimal("501050"), Decimal("0.32")),
        (Decimal("751600"), Decimal("0.35")),
        (None, Decimal("0.37")),
    ),
    "head_of_household": (
        (Decimal("17000"), Decimal("0.10")),
        (Decimal("64850"), Decimal("0.12")),
        (Decimal("103350"), Decimal("0.22")),
        (Decimal("197300"), Decimal("0.24")),
        (Decimal("250500"), Decimal("0.32")),
        (Decimal("626350"), Decimal("0.35")),
        (None, Decimal("0.37")),
    ),
    "married_filing_separately": (
        (Decimal("11925"), Decimal("0.10")),
        (Decimal("48475"), Decimal("0.12")),
        (Decimal("103350"), Decimal("0.22")),
        (Decimal("197300"), Decimal("0.24")),
        (Decimal("250525"), Decimal("0.32")),
        (Decimal("375800"), Decimal("0.35")),
        (None, Decimal("0.37")),
    ),
}

CTC_PHASEOUT_START_2025 = {
    "married_filing_jointly": Decimal("400000"),
    "single": Decimal("200000"),
    "head_of_household": Decimal("200000"),
    "married_filing_separately": Decimal("200000"),
    "qualifying_surviving_spouse": Decimal("200000"),
}


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def _parse_nonneg(value: Any, label: str) -> Decimal:
    amt = currency_stripper(value)
    if amt < ZERO:
        raise InputValidationError(f"{label} cannot be negative.")
    return amt


def _require_nonneg_int(value: Any, label: str) -> int:
    if type(value) is not int or value < 0:
        raise InputValidationError(f"{label} must be a non-negative integer.")
    return value


def build_tax_and_credits_workpaper(
    *,
    tax_year: int = 2025,
    filing_status: str | None = None,
    agi: Any = None,
    deduction_taken: Any = None,
    qualifying_children_under_17: int = 0,
    other_dependents: int = 0,
    qualified_dividends_or_ltcg_present: bool = False,
) -> dict[str, Any]:
    """Compute 2025 ordinary taxable income, bracket tax, and preliminary Child Tax Credit screen."""
    if type(tax_year) is not int or tax_year != 2025:
        raise InputValidationError("Configured Form 1040 tax-and-credits year is 2025 only.")
    if not isinstance(qualified_dividends_or_ltcg_present, bool):
        raise InputValidationError("qualified_dividends_or_ltcg_present must be a boolean True/False.")
    children_count = _require_nonneg_int(qualifying_children_under_17, "qualifying_children_under_17")
    other_dep_count = _require_nonneg_int(other_dependents, "other_dependents")

    missing_fields: list[str] = []
    if _is_blank(filing_status):
        missing_fields.append("filing_status")
    if _is_blank(agi):
        missing_fields.append("agi")
    if _is_blank(deduction_taken):
        missing_fields.append("deduction_taken")
    if missing_fields:
        return {
            "rule_id": "form_1040_tax_and_credits_2025",
            "tax_year": tax_year,
            "status": "REVIEW_REQUIRED",
            "missing_fields": missing_fields,
            "review_note": f"Missing required input(s): {', '.join(missing_fields)}.",
        }

    if not isinstance(filing_status, str):
        raise InputValidationError("filing_status must be a string.")
    status_key = filing_status.strip().lower().replace(" ", "_")
    if status_key not in BRACKETS_2025_REFERENCE:
        raise InputValidationError(f"Unsupported filing_status: {filing_status!r}")

    with localcontext(MONEY_CONTEXT):
        agi_val = _parse_nonneg(agi, "agi")
        ded_val = _parse_nonneg(deduction_taken, "deduction_taken")
        taxable_income = max(ZERO, agi_val - ded_val)

        # Ordinary bracket calculation
        tax = ZERO
        prev_cap = ZERO
        bracket_breakdown: list[dict[str, str]] = []
        for upper, rate in BRACKETS_2025_REFERENCE[status_key]:
            if taxable_income <= prev_cap:
                break
            slice_amt = (taxable_income - prev_cap) if upper is None else (min(taxable_income, upper) - prev_cap)
            if slice_amt > ZERO:
                slice_tax = slice_amt * rate
                tax += slice_tax
                bracket_breakdown.append({
                    "rate": str(rate),
                    "taxable_in_bracket": str(slice_amt),
                    "tax_in_bracket": str(slice_tax),
                })
            if upper is not None:
                prev_cap = upper

        # Preliminary Child Tax Credit / Other Dependent Credit phaseout screen
        initial_credit = (Decimal(children_count) * Decimal("2000")) + (Decimal(other_dep_count) * Decimal("500"))
        phaseout_start = CTC_PHASEOUT_START_2025[status_key]
        if initial_credit > ZERO and agi_val > phaseout_start:
            excess = agi_val - phaseout_start
            # $50 reduction for each $1,000 (or fraction thereof) above threshold
            increments = (excess / Decimal("1000")).to_integral_value(rounding="ROUND_CEILING")
            reduction = increments * Decimal("50")
            preliminary_credit = max(ZERO, initial_credit - reduction)
        else:
            preliminary_credit = initial_credit

        nonrefundable_credit_applied = min(tax, preliminary_credit)
        tax_after_nonrefundable = tax - nonrefundable_credit_applied

        review_reasons: list[str] = []
        if qualified_dividends_or_ltcg_present:
            review_reasons.append(
                "Qualified dividends or long-term capital gains present; use Qualified Dividends and Capital Gain Tax Worksheet."
            )
        if preliminary_credit > nonrefundable_credit_applied:
            review_reasons.append(
                "Preliminary credit exceeds regular tax; review Schedule 8812 for refundable Additional Child Tax Credit."
            )

        return {
            "rule_id": "form_1040_tax_and_credits_2025",
            "tax_year": tax_year,
            "filing_status": status_key,
            "status": "REVIEW_REQUIRED" if review_reasons else "CALCULATED",
            "agi": str(agi_val),
            "deduction_taken": str(ded_val),
            "taxable_income": str(taxable_income),
            "ordinary_bracket_tax": str(tax),
            "bracket_breakdown": bracket_breakdown,
            "preliminary_ctc_and_odc": str(preliminary_credit),
            "nonrefundable_credit_applied": str(nonrefundable_credit_applied),
            "tax_after_nonrefundable_credits": str(tax_after_nonrefundable),
            "review_reasons": review_reasons,
            "review_note": "Reference workpaper only. Verify 2025 IRS tax tables/brackets, SSN/qualifying-child rules, and Schedule 8812.",
        }
