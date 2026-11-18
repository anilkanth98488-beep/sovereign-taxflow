"""2025 Form 1120 (Corporation) & Form 1065 (Partnership) return workpaper screen.

Integrates book net income, book_to_tax adjustments, preliminary Schedule M-3
flags, and either Form 1120 21% corporate tax screen or Form 1065 partner K-1
ownership allocation checks using 64-digit MONEY_CONTEXT.
"""
from __future__ import annotations

from decimal import Decimal, localcontext
from typing import Any

from core.reconciliation import InputValidationError, MONEY_CONTEXT, currency_stripper
from modules.book_to_tax import build_book_to_tax_workpaper, m3_threshold_flags

ZERO = Decimal("0")


def _parse_nonneg(value: Any, label: str) -> Decimal:
    amt = currency_stripper(value)
    if amt < ZERO:
        raise InputValidationError(f"{label} cannot be negative.")
    return amt


def build_business_return_workpaper(
    *,
    entity_form: str,
    tax_year: int = 2025,
    gross_receipts: Any = "0",
    cogs: Any = "0",
    operating_expenses: Any = "0",
    book_to_tax_items: list[dict[str, Any]] | None = None,
    total_assets: Any = "0",
    reportable_partner_50pct: bool = False,
    partner_allocations: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Assemble a 2025 Form 1120 or Form 1065 workpaper summary with M-3 and K-1 checks."""
    if type(tax_year) is not int or tax_year != 2025:
        raise InputValidationError("Configured business return workpaper year is 2025 only.")
    if not isinstance(entity_form, str):
        raise InputValidationError("entity_form must be '1120' or '1065'.")
    form_key = entity_form.strip().upper()
    if form_key not in {"1120", "1065"}:
        raise InputValidationError(f"Unsupported entity_form {entity_form!r}; use '1120' or '1065'.")

    with localcontext(MONEY_CONTEXT):
        receipts = _parse_nonneg(gross_receipts, "gross_receipts")
        cogs_val = _parse_nonneg(cogs, "cogs")
        opex_val = _parse_nonneg(operating_expenses, "operating_expenses")
        book_net_income = receipts - cogs_val - opex_val

        bt_res = build_book_to_tax_workpaper(
            [] if book_to_tax_items is None else book_to_tax_items,
            tax_year,
            entity_type=form_key,
        )
        net_bt_adj = Decimal(bt_res["net_quantified_proposed_adjustment"])
        unresolved_bt = Decimal(bt_res["unresolved_review_amount_total"])
        prelim_taxable_or_ordinary = book_net_income + net_bt_adj

        m3_res = m3_threshold_flags(
            form_key,
            total_assets,
            total_receipts=str(receipts),
            reportable_partner_50pct=reportable_partner_50pct,
        )

        review_reasons: list[str] = []
        if unresolved_bt > ZERO:
            review_reasons.append(f"Book-to-tax has ${unresolved_bt} awaiting CPA review.")
        if m3_res["schedule_m3_required_preliminary"]:
            review_reasons.append("Schedule M-3 preliminary threshold triggered.")

        result: dict[str, Any] = {
            "rule_id": "business_1120_1065_2025",
            "entity_form": form_key,
            "tax_year": tax_year,
            "book_net_income": str(book_net_income),
            "quantified_book_to_tax_net": str(net_bt_adj),
            "unresolved_book_to_tax_amount": str(unresolved_bt),
            "preliminary_taxable_or_ordinary_income": str(prelim_taxable_or_ordinary),
            "m3_flags": m3_res,
        }

        if form_key == "1120":
            corp_tax = max(ZERO, prelim_taxable_or_ordinary) * Decimal("0.21")
            result["illustrative_1120_tax_21pct"] = str(corp_tax)
        else:
            alloc_rows: list[dict[str, str]] = []
            pct_sum = ZERO
            if partner_allocations is not None:
                if not isinstance(partner_allocations, list):
                    raise InputValidationError("partner_allocations must be a list.")
                for idx, p in enumerate(partner_allocations, 1):
                    if not isinstance(p, dict):
                        raise InputValidationError(f"Partner {idx} must be a dict.")
                    pname = str(p.get("partner") or f"Partner {idx}").strip()
                    pct = _parse_nonneg(p.get("profit_pct"), f"{pname} profit_pct")
                    pct_sum += pct
                    share = prelim_taxable_or_ordinary * (pct / Decimal("100"))
                    alloc_rows.append({"partner": pname, "profit_pct": str(pct), "ordinary_share": str(share)})
                if alloc_rows and pct_sum != Decimal("100"):
                    review_reasons.append(f"Partner profit_pct sum is {pct_sum}%, expected 100%.")
            result["partner_k1_allocations"] = alloc_rows

        result["status"] = "REVIEW_REQUIRED" if review_reasons else "CALCULATED"
        result["review_reasons"] = review_reasons
        result["review_note"] = "Reference business workpaper only. Verify NOLs, §163(j), officer compensation, basis, and Schedule M-1/M-3."
        return result
