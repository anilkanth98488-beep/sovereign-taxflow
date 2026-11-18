"""2025 Form 1041 (U.S. Income Tax Return for Estates and Trusts) workpaper screen.

Deterministic arithmetic using 64-digit MONEY_CONTEXT. Compressed trust/estate
brackets and exemption amounts are reference placeholders requiring CPA verification.
"""
from __future__ import annotations

from decimal import Decimal, localcontext
from typing import Any

from core.reconciliation import InputValidationError, MONEY_CONTEXT, currency_stripper

ZERO = Decimal("0")

EXEMPTIONS_1041_2025 = {
    "estate": Decimal("600"),
    "simple_trust": Decimal("300"),
    "complex_trust": Decimal("100"),
}

# Reference 2025 Form 1041 compressed ordinary income tax brackets
BRACKETS_1041_2025_REFERENCE = (
    (Decimal("3150"), Decimal("0.10")),
    (Decimal("11450"), Decimal("0.24")),
    (Decimal("15650"), Decimal("0.35")),
    (None, Decimal("0.37")),
)


def _parse_nonneg(value: Any, label: str) -> Decimal:
    amt = currency_stripper(value)
    if amt < ZERO:
        raise InputValidationError(f"{label} cannot be negative.")
    return amt


def build_1041_workpaper(
    *,
    entity_type: str,
    tax_year: int = 2025,
    interest_and_dividends: Any = "0",
    capital_gains_net: Any = "0",
    other_income: Any = "0",
    fiduciary_and_professional_fees: Any = "0",
    distributions_to_beneficiaries: Any = "0",
    capital_gains_allocated_to_corpus: bool = True,
) -> dict[str, Any]:
    """Compute 2025 Form 1041 total income, DNI/distribution deduction screen, and bracket tax."""
    if type(tax_year) is not int or tax_year != 2025:
        raise InputValidationError("Configured Form 1041 workpaper year is 2025 only.")
    if not isinstance(entity_type, str):
        raise InputValidationError("entity_type must be 'estate', 'simple_trust', or 'complex_trust'.")
    etype = entity_type.strip().lower().replace(" ", "_")
    if etype not in EXEMPTIONS_1041_2025:
        raise InputValidationError(f"Unsupported Form 1041 entity_type: {entity_type!r}")
    if not isinstance(capital_gains_allocated_to_corpus, bool):
        raise InputValidationError("capital_gains_allocated_to_corpus must be a boolean True/False.")

    with localcontext(MONEY_CONTEXT):
        int_div = _parse_nonneg(interest_and_dividends, "interest_and_dividends")
        cap_gains = currency_stripper(capital_gains_net)
        other_inc = _parse_nonneg(other_income, "other_income")
        fees = _parse_nonneg(fiduciary_and_professional_fees, "fiduciary_and_professional_fees")
        distributions = _parse_nonneg(distributions_to_beneficiaries, "distributions_to_beneficiaries")

        total_income = int_div + cap_gains + other_inc
        adjusted_total_income = total_income - fees

        # Preliminary DNI: exclude capital gains allocated to corpus (IRC §643(a)(3))
        dni = max(ZERO, adjusted_total_income - (cap_gains if capital_gains_allocated_to_corpus else ZERO))
        distribution_deduction = min(dni, distributions)
        exemption = EXEMPTIONS_1041_2025[etype]
        taxable_income = max(ZERO, adjusted_total_income - distribution_deduction - exemption)

        tax = ZERO
        prev = ZERO
        for upper, rate in BRACKETS_1041_2025_REFERENCE:
            if taxable_income <= prev:
                break
            slice_amt = (taxable_income - prev) if upper is None else (min(taxable_income, upper) - prev)
            if slice_amt > ZERO:
                tax += slice_amt * rate
            if upper is not None:
                prev = upper

        niit_review = adjusted_total_income > Decimal("15650")
        return {
            "rule_id": "fiduciary_1041_2025",
            "entity_type": etype,
            "tax_year": tax_year,
            "status": "REVIEW_REQUIRED" if niit_review else "CALCULATED",
            "total_income_line_9": str(total_income),
            "fiduciary_fees_and_deductions": str(fees),
            "preliminary_dni_schedule_b": str(dni),
            "income_distribution_deduction_line_18": str(distribution_deduction),
            "exemption_line_21": str(exemption),
            "taxable_income_line_23": str(taxable_income),
            "illustrative_bracket_tax": str(tax),
            "form_8960_niit_review_required": niit_review,
            "review_note": (
                "Adjusted total income exceeds 2025 top trust bracket ($15,650); review Form 8960 Net Investment Income Tax (3.8%) and Schedule K-1 allocations."
                if niit_review
                else "Reference Form 1041 workpaper only. Verify trust instrument, DNI adjustments, and Schedule K-1 allocations."
            ),
        }
