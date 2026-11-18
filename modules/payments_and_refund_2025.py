"""2025 Form 1040 total tax, payments tie-out, refund/owed, and Form 2210 screen.

Deterministic arithmetic using 64-digit MONEY_CONTEXT.
"""
from __future__ import annotations

from decimal import Decimal, localcontext
from typing import Any

from core.reconciliation import InputValidationError, MONEY_CONTEXT, currency_stripper

ZERO = Decimal("0")


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def _parse_nonneg(value: Any, label: str) -> Decimal:
    amt = currency_stripper(value)
    if amt < ZERO:
        raise InputValidationError(f"{label} cannot be negative.")
    return amt


def build_payments_and_refund_workpaper(
    *,
    tax_year: int = 2025,
    regular_tax_after_credits: Any = None,
    self_employment_tax: Any = "0",
    other_taxes: Any = "0",
    w2_withholding_line_25a: Any = "0",
    form_1099_withholding_line_25b: Any = "0",
    estimated_payments_line_26: Any = "0",
    extension_payment: Any = "0",
    refundable_credits: Any = "0",
) -> dict[str, Any]:
    """Compute 2025 Form 1040 total tax, total payments, refund or amount owed, and Form 2210 screen."""
    if type(tax_year) is not int or tax_year != 2025:
        raise InputValidationError("Configured Form 1040 payments/refund year is 2025 only.")
    if _is_blank(regular_tax_after_credits):
        return {
            "rule_id": "form_1040_payments_and_refund_2025",
            "tax_year": tax_year,
            "status": "REVIEW_REQUIRED",
            "missing_fields": ["regular_tax_after_credits"],
            "review_note": "Missing required regular_tax_after_credits.",
        }

    with localcontext(MONEY_CONTEXT):
        reg_tax = _parse_nonneg(regular_tax_after_credits, "regular_tax_after_credits")
        se_tax = _parse_nonneg(self_employment_tax, "self_employment_tax")
        other_t = _parse_nonneg(other_taxes, "other_taxes")
        total_tax = reg_tax + se_tax + other_t

        wh_w2 = _parse_nonneg(w2_withholding_line_25a, "w2_withholding_line_25a")
        wh_1099 = _parse_nonneg(form_1099_withholding_line_25b, "form_1099_withholding_line_25b")
        est_pmts = _parse_nonneg(estimated_payments_line_26, "estimated_payments_line_26")
        ext_pmt = _parse_nonneg(extension_payment, "extension_payment")
        ref_credits = _parse_nonneg(refundable_credits, "refundable_credits")

        total_withholding_line_25d = wh_w2 + wh_1099
        total_payments = total_withholding_line_25d + est_pmts + ext_pmt + ref_credits

        overpayment_refund = max(ZERO, total_payments - total_tax)
        amount_you_owe = max(ZERO, total_tax - total_payments)

        # Preliminary Form 2210 screen: owed >= $1,000 and timely withholding/estimated < 90% of total tax
        timely_payments = total_withholding_line_25d + est_pmts + ref_credits
        form_2210_review = (amount_you_owe >= Decimal("1000")) and (timely_payments < (total_tax * Decimal("0.90")))

        return {
            "rule_id": "form_1040_payments_and_refund_2025",
            "tax_year": tax_year,
            "status": "REVIEW_REQUIRED" if form_2210_review else "CALCULATED",
            "total_tax_line_24": str(total_tax),
            "total_withholding_line_25d": str(total_withholding_line_25d),
            "total_payments_line_33": str(total_payments),
            "overpayment_refund_line_34": str(overpayment_refund),
            "amount_you_owe_line_37": str(amount_you_owe),
            "form_2210_penalty_review_required": form_2210_review,
            "review_note": (
                "Amount owed is $1,000+ and timely payments are below 90% of total tax; review Form 2210 prior-year safe harbor."
                if form_2210_review
                else "Reference workpaper only. Verify estimated payment dates/confirmations and refundable credit eligibility."
            ),
        }
