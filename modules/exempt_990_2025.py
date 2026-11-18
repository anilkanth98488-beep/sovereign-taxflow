"""2025 Form 990 / 990-EZ / 990-N (Tax-Exempt Organization) filing-tier and UBIT screen.

Deterministic arithmetic using 64-digit MONEY_CONTEXT.
"""
from __future__ import annotations

from decimal import Decimal, localcontext
from typing import Any

from core.reconciliation import InputValidationError, MONEY_CONTEXT, currency_stripper

ZERO = Decimal("0")


def _parse_nonneg(value: Any, label: str) -> Decimal:
    amt = currency_stripper(value)
    if amt < ZERO:
        raise InputValidationError(f"{label} cannot be negative.")
    return amt


def build_990_workpaper(
    *,
    tax_year: int = 2025,
    contributions_and_grants: Any = "0",
    program_service_revenue: Any = "0",
    investment_income: Any = "0",
    program_service_expenses: Any = "0",
    management_and_general_expenses: Any = "0",
    fundraising_expenses: Any = "0",
    total_end_of_year_assets: Any = "0",
    unrelated_business_gross_income: Any = "0",
) -> dict[str, Any]:
    """Compute 2025 Form 990 revenue, functional expenses, filing tier, and Form 990-T UBIT screen."""
    if type(tax_year) is not int or tax_year != 2025:
        raise InputValidationError("Configured Form 990 workpaper year is 2025 only.")

    with localcontext(MONEY_CONTEXT):
        contrib = _parse_nonneg(contributions_and_grants, "contributions_and_grants")
        prog_rev = _parse_nonneg(program_service_revenue, "program_service_revenue")
        inv_inc = _parse_nonneg(investment_income, "investment_income")
        total_revenue = contrib + prog_rev + inv_inc

        prog_exp = _parse_nonneg(program_service_expenses, "program_service_expenses")
        mgmt_exp = _parse_nonneg(management_and_general_expenses, "management_and_general_expenses")
        fund_exp = _parse_nonneg(fundraising_expenses, "fundraising_expenses")
        total_expenses = prog_exp + mgmt_exp + fund_exp

        assets = _parse_nonneg(total_end_of_year_assets, "total_end_of_year_assets")
        ubit_gross = _parse_nonneg(unrelated_business_gross_income, "unrelated_business_gross_income")

        net_revenue = total_revenue - total_expenses
        prog_ratio_pct = ((prog_exp / total_expenses) * Decimal("100")) if total_expenses > ZERO else ZERO

        if total_revenue <= Decimal("50000"):
            suggested_form = "990-N"
        elif total_revenue < Decimal("200000") and assets < Decimal("500000"):
            suggested_form = "990-EZ"
        else:
            suggested_form = "990"

        ubit_required = ubit_gross >= Decimal("1000")
        return {
            "rule_id": "exempt_990_2025",
            "tax_year": tax_year,
            "status": "REVIEW_REQUIRED" if ubit_required else "CALCULATED",
            "total_revenue": str(total_revenue),
            "total_functional_expenses": str(total_expenses),
            "revenue_less_expenses": str(net_revenue),
            "program_expense_ratio_pct": str(prog_ratio_pct.quantize(Decimal("0.01"))),
            "total_end_of_year_assets": str(assets),
            "suggested_form_tier_reference": suggested_form,
            "form_990t_ubit_review_required": ubit_required,
            "review_note": (
                "Unrelated business gross income >= $1,000; Form 990-T filing and expense allocation review required."
                if ubit_required
                else "Reference Form 990 screen only. Verify 3-year gross-receipts average for 990-N, Schedule A public support, and governance disclosures."
            ),
        }
