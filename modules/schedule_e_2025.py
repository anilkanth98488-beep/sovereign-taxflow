"""2025 Schedule E (Part I Rental Real Estate & Part II K-1 Pass-Through) workpaper.

Deterministic arithmetic using 64-digit MONEY_CONTEXT. Passive-activity loss
(Form 8582) and basis/at-risk limitations are flagged REVIEW_REQUIRED for CPA sign-off.
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


def _parse_signed(value: Any, label: str) -> Decimal:
    return currency_stripper(value)


def build_schedule_e_workpaper(
    *,
    tax_year: int = 2025,
    rentals: list[dict[str, Any]] | None = None,
    k1_items: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Aggregate 2025 Schedule E rental properties and 1065/1120-S K-1 items."""
    if type(tax_year) is not int or tax_year != 2025:
        raise InputValidationError("Configured Schedule E reference year is 2025 only.")
    rentals = [] if rentals is None else rentals
    k1_items = [] if k1_items is None else k1_items
    if not isinstance(rentals, list) or not isinstance(k1_items, list):
        raise InputValidationError("rentals and k1_items must be lists.")

    with localcontext(MONEY_CONTEXT):
        rental_net = ZERO
        k1_net = ZERO
        review_reasons: list[str] = []

        rental_rows: list[dict[str, str]] = []
        for idx, prop in enumerate(rentals, 1):
            if not isinstance(prop, dict):
                raise InputValidationError(f"Rental {idx} must be a dict.")
            name = str(prop.get("property") or f"Property {idx}").strip()
            if _is_blank(prop.get("rents_received")):
                return {
                    "rule_id": "schedule_e_2025",
                    "tax_year": tax_year,
                    "status": "REVIEW_REQUIRED",
                    "review_note": f"Rental {name!r}: missing rents_received.",
                }
            rents = _parse_nonneg(prop.get("rents_received"), f"{name} rents_received")
            expenses = ZERO if _is_blank(prop.get("expenses")) else _parse_nonneg(prop.get("expenses"), f"{name} expenses")
            depreciation = ZERO if _is_blank(prop.get("depreciation")) else _parse_nonneg(prop.get("depreciation"), f"{name} depreciation")
            net = rents - expenses - depreciation
            rental_net += net
            if net < ZERO:
                review_reasons.append(f"Rental {name!r} has net loss ({net}); verify Form 8582 passive-activity loss rules.")
            rental_rows.append({"property": name, "net_income_loss": str(net)})

        k1_rows: list[dict[str, str]] = []
        for idx, k1 in enumerate(k1_items, 1):
            if not isinstance(k1, dict):
                raise InputValidationError(f"K-1 {idx} must be a dict.")
            entity_form = str(k1.get("entity_form") or "").strip().upper()
            if entity_form not in {"1065", "1120-S"}:
                raise InputValidationError(f"K-1 {idx}: entity_form must be '1065' or '1120-S', got {entity_form!r}.")
            entity_name = str(k1.get("entity_name") or f"{entity_form}_{idx}").strip()
            ordinary = ZERO if _is_blank(k1.get("ordinary_income_loss")) else _parse_signed(k1.get("ordinary_income_loss"), f"{entity_name} ordinary_income_loss")
            guaranteed = ZERO if _is_blank(k1.get("guaranteed_payments")) else _parse_nonneg(k1.get("guaranteed_payments"), f"{entity_name} guaranteed_payments")
            if entity_form == "1120-S" and guaranteed > ZERO:
                raise InputValidationError(f"{entity_name}: 1120-S K-1 cannot report partnership guaranteed_payments.")
            net_k1 = ordinary + guaranteed
            k1_net += net_k1
            if ordinary < ZERO:
                review_reasons.append(f"K-1 {entity_name!r} reports loss ({ordinary}); verify basis (Form 7203/6198) and passive-loss limits.")
            k1_rows.append({"entity_name": entity_name, "entity_form": entity_form, "net_k1_income_loss": str(net_k1)})

        total_schedule_e = rental_net + k1_net
        return {
            "rule_id": "schedule_e_2025",
            "tax_year": tax_year,
            "status": "REVIEW_REQUIRED" if review_reasons else "CALCULATED",
            "rental_net_income_loss": str(rental_net),
            "k1_net_income_loss": str(k1_net),
            "schedule_e_total_for_schedule_1_line_5": str(total_schedule_e),
            "rentals": rental_rows,
            "k1_items": k1_rows,
            "review_reasons": review_reasons,
            "review_note": "Reference workpaper only. Confirm QBI (§199A), basis, at-risk (Form 6198), and passive-activity (Form 8582) limitations.",
        }
