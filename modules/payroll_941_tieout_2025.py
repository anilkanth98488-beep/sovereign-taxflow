"""2025 Quarterly Form 941 (Q1-Q4) vs. Annual Form W-2 / W-3 tie-out workpaper.

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


def build_payroll_941_tieout(
    quarterly_941s: list[dict[str, Any]],
    annual_w3_totals: dict[str, Any],
    *,
    tax_year: int = 2025,
) -> dict[str, Any]:
    """Reconcile Q1-Q4 Form 941 totals against annual Form W-3 / combined W-2 totals."""
    if type(tax_year) is not int or tax_year != 2025:
        raise InputValidationError("Configured payroll 941 tie-out year is 2025 only.")
    if not isinstance(quarterly_941s, list) or len(quarterly_941s) != 4:
        raise InputValidationError("quarterly_941s must contain exactly 4 quarter records (Q1-Q4).")
    if not isinstance(annual_w3_totals, dict):
        raise InputValidationError("annual_w3_totals must be a dict.")

    with localcontext(MONEY_CONTEXT):
        seen_quarters: set[str] = set()
        q_wages = q_wh = q_ss = q_med = ZERO

        for idx, q in enumerate(quarterly_941s, 1):
            if not isinstance(q, dict):
                raise InputValidationError(f"Quarter {idx} must be a dict.")
            q_label = str(q.get("quarter") or "").strip().upper()
            if q_label not in {"Q1", "Q2", "Q3", "Q4"}:
                raise InputValidationError(f"Quarter {idx}: quarter must be Q1, Q2, Q3, or Q4, got {q_label!r}.")
            if q_label in seen_quarters:
                raise InputValidationError(f"Duplicate quarter {q_label!r} rejected.")
            seen_quarters.add(q_label)

            q_wages += _parse_nonneg(q.get("wages_line_2", "0"), f"{q_label} wages_line_2")
            q_wh += _parse_nonneg(q.get("fed_withholding_line_3", "0"), f"{q_label} fed_withholding_line_3")
            q_ss += _parse_nonneg(q.get("ss_wages_line_5a", "0"), f"{q_label} ss_wages_line_5a")
            q_med += _parse_nonneg(q.get("medicare_wages_line_5c", "0"), f"{q_label} medicare_wages_line_5c")

        w3_box1 = _parse_nonneg(annual_w3_totals.get("box_1_wages", "0"), "W-3 box_1_wages")
        w3_box2 = _parse_nonneg(annual_w3_totals.get("box_2_withholding", "0"), "W-3 box_2_withholding")
        w3_box3 = _parse_nonneg(annual_w3_totals.get("box_3_ss_wages", "0"), "W-3 box_3_ss_wages")
        w3_box5 = _parse_nonneg(annual_w3_totals.get("box_5_medicare_wages", "0"), "W-3 box_5_medicare_wages")

        checks = [
            {"field": "wages_box_1_vs_941_line_2", "total_941": str(q_wages), "total_w3": str(w3_box1), "difference": str(q_wages - w3_box1), "status": "MATCH" if q_wages == w3_box1 else "REVIEW_REQUIRED"},
            {"field": "withholding_box_2_vs_941_line_3", "total_941": str(q_wh), "total_w3": str(w3_box2), "difference": str(q_wh - w3_box2), "status": "MATCH" if q_wh == w3_box2 else "REVIEW_REQUIRED"},
            {"field": "ss_wages_box_3_vs_941_line_5a", "total_941": str(q_ss), "total_w3": str(w3_box3), "difference": str(q_ss - w3_box3), "status": "MATCH" if q_ss == w3_box3 else "REVIEW_REQUIRED"},
            {"field": "medicare_wages_box_5_vs_941_line_5c", "total_941": str(q_med), "total_w3": str(w3_box5), "difference": str(q_med - w3_box5), "status": "MATCH" if q_med == w3_box5 else "REVIEW_REQUIRED"},
        ]

        overall = "MATCH" if all(c["status"] == "MATCH" for c in checks) else "REVIEW_REQUIRED"
        return {
            "rule_id": "payroll_941_tieout_2025",
            "tax_year": tax_year,
            "status": overall,
            "checks": checks,
            "review_note": "Payroll workpaper tie-out only. Verify Form 941-X amendments, third-party sick pay, and §125/401(k) pre-tax items.",
        }
