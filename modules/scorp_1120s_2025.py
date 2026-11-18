"""2025 Form 1120-S (S-Corporation), Officer Compensation & Form 7203 Basis screen.

Deterministic arithmetic using 64-digit MONEY_CONTEXT.
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


def build_1120s_workpaper(
    *,
    tax_year: int = 2025,
    gross_receipts: Any = "0",
    cogs: Any = "0",
    officer_compensation: Any = "0",
    other_operating_expenses: Any = "0",
    book_to_tax_items: list[dict[str, Any]] | None = None,
    total_assets: Any = "0",
    shareholders: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Assemble a 2025 Form 1120-S workpaper with officer-comp, K-1 %, and Form 7203 basis checks."""
    if type(tax_year) is not int or tax_year != 2025:
        raise InputValidationError("Configured Form 1120-S workpaper year is 2025 only.")

    with localcontext(MONEY_CONTEXT):
        receipts = _parse_nonneg(gross_receipts, "gross_receipts")
        cogs_val = _parse_nonneg(cogs, "cogs")
        officer_comp = _parse_nonneg(officer_compensation, "officer_compensation")
        other_opex = _parse_nonneg(other_operating_expenses, "other_operating_expenses")
        book_net = receipts - cogs_val - officer_comp - other_opex

        bt_res = build_book_to_tax_workpaper(
            [] if book_to_tax_items is None else book_to_tax_items,
            tax_year,
            entity_type="1120-S",
        )
        net_bt = Decimal(bt_res["net_quantified_proposed_adjustment"])
        unresolved_bt = Decimal(bt_res["unresolved_review_amount_total"])
        ordinary_income = book_net + net_bt

        m3_res = m3_threshold_flags("1120-S", total_assets, total_receipts=str(receipts))
        review_reasons: list[str] = []
        if unresolved_bt > ZERO:
            review_reasons.append(f"Book-to-tax has ${unresolved_bt} awaiting CPA review.")
        if m3_res["schedule_m3_required_preliminary"]:
            review_reasons.append("Schedule M-3 preliminary threshold triggered.")
        if ordinary_income > ZERO and officer_comp == ZERO:
            review_reasons.append("Ordinary income > $0 with $0 officer compensation; review IRC §3121 reasonable compensation.")

        sh_rows: list[dict[str, Any]] = []
        pct_sum = ZERO
        if shareholders is not None:
            if not isinstance(shareholders, list):
                raise InputValidationError("shareholders must be a list.")
            for idx, sh in enumerate(shareholders, 1):
                if not isinstance(sh, dict):
                    raise InputValidationError(f"Shareholder {idx} must be a dict.")
                name = str(sh.get("name") or f"Shareholder {idx}").strip()
                pct = _parse_nonneg(sh.get("ownership_pct"), f"{name} ownership_pct")
                pct_sum += pct
                share_income = ordinary_income * (pct / Decimal("100"))

                beg_basis = _parse_nonneg(sh.get("beginning_stock_basis", "0"), f"{name} beginning_stock_basis")
                contributions = _parse_nonneg(sh.get("capital_contributions", "0"), f"{name} capital_contributions")
                distributions = _parse_nonneg(sh.get("distributions", "0"), f"{name} distributions")
                nondeductible = _parse_nonneg(sh.get("nondeductible_expenses", "0"), f"{name} nondeductible_expenses")

                # Simplified Form 7203 ordering: beginning + contributions + positive income - distributions - nondeductible - loss
                basis_before_loss = beg_basis + contributions + max(ZERO, share_income)
                dist_in_excess_of_basis = max(ZERO, distributions - basis_before_loss)
                basis_after_dist = max(ZERO, basis_before_loss - distributions)
                basis_after_nonded = max(ZERO, basis_after_dist - nondeductible)

                loss_share = abs(min(ZERO, share_income))
                allowed_loss = min(loss_share, basis_after_nonded)
                suspended_loss = loss_share - allowed_loss
                ending_basis = basis_after_nonded - allowed_loss

                if dist_in_excess_of_basis > ZERO:
                    review_reasons.append(f"{name}: distributions exceed stock basis by ${dist_in_excess_of_basis} (potential capital gain).")
                if suspended_loss > ZERO:
                    review_reasons.append(f"{name}: ${suspended_loss} ordinary loss suspended for insufficient stock basis (Form 7203).")

                sh_rows.append({
                    "name": name,
                    "ownership_pct": str(pct),
                    "ordinary_income_share": str(share_income),
                    "ending_stock_basis": str(ending_basis),
                    "distributions_in_excess_of_basis": str(dist_in_excess_of_basis),
                    "suspended_loss_carryforward": str(suspended_loss),
                })

            if sh_rows and pct_sum != Decimal("100"):
                review_reasons.append(f"Shareholder ownership_pct sum is {pct_sum}%, expected 100%.")

        return {
            "rule_id": "scorp_1120s_2025",
            "tax_year": tax_year,
            "status": "REVIEW_REQUIRED" if review_reasons else "CALCULATED",
            "book_net_income": str(book_net),
            "ordinary_business_income": str(ordinary_income),
            "officer_compensation": str(officer_comp),
            "m3_flags": m3_res,
            "shareholders": sh_rows,
            "review_reasons": review_reasons,
            "review_note": "Reference Form 1120-S / Form 7203 workpaper only. Verify debt basis, AAA/AE&P, and §1366 ordering.",
        }
