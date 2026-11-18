"""2025 Schedule D & Form 8949 capital gains/losses and loss-limitation workpaper.

Deterministic arithmetic using 64-digit MONEY_CONTEXT. The $3,000 ($1,500 MFS)
capital-loss deduction limit is a reference ceiling requiring CPA verification.
"""
from __future__ import annotations

from decimal import Decimal, localcontext
from typing import Any

from core.reconciliation import InputValidationError, MONEY_CONTEXT, currency_stripper

ZERO = Decimal("0")
CAPITAL_LOSS_LIMIT_2025 = {
    "single": Decimal("3000"),
    "married_filing_jointly": Decimal("3000"),
    "qualifying_surviving_spouse": Decimal("3000"),
    "head_of_household": Decimal("3000"),
    "married_filing_separately": Decimal("1500"),
}


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def _parse_nonneg(value: Any, label: str) -> Decimal:
    amt = currency_stripper(value)
    if amt < ZERO:
        raise InputValidationError(f"{label} cannot be negative.")
    return amt


def build_schedule_d_workpaper(
    transactions: list[dict[str, Any]],
    *,
    tax_year: int = 2025,
    filing_status: str | None = None,
    prior_year_st_carryover: Any = "0",
    prior_year_lt_carryover: Any = "0",
) -> dict[str, Any]:
    """Compute 2025 short-term/long-term capital gain or loss, deduction limit, and carryover."""
    if type(tax_year) is not int or tax_year != 2025:
        raise InputValidationError("Configured Schedule D reference year is 2025 only.")
    if not isinstance(transactions, list):
        raise InputValidationError("transactions must be a list of Form 8949 / Schedule D rows.")
    if _is_blank(filing_status):
        return {
            "rule_id": "schedule_d_2025",
            "tax_year": tax_year,
            "status": "REVIEW_REQUIRED",
            "missing_fields": ["filing_status"],
            "review_note": "Missing required filing_status.",
        }
    if not isinstance(filing_status, str):
        raise InputValidationError("filing_status must be a string.")
    status_key = filing_status.strip().lower().replace(" ", "_")
    if status_key not in CAPITAL_LOSS_LIMIT_2025:
        raise InputValidationError(f"Unsupported filing_status: {filing_status!r}")

    with localcontext(MONEY_CONTEXT):
        st_carry = _parse_nonneg(prior_year_st_carryover, "prior_year_st_carryover")
        lt_carry = _parse_nonneg(prior_year_lt_carryover, "prior_year_lt_carryover")

        st_net = -st_carry
        lt_net = -lt_carry
        wash_sales_total = ZERO
        missing_basis_or_period = False

        for idx, tx in enumerate(transactions, 1):
            if not isinstance(tx, dict):
                raise InputValidationError(f"Transaction {idx} must be a dict.")
            period = str(tx.get("holding_period") or "").strip().lower()
            if period not in {"short", "long"}:
                missing_basis_or_period = True
                continue
            if _is_blank(tx.get("proceeds")) or _is_blank(tx.get("cost_basis")):
                missing_basis_or_period = True
                continue
            proceeds = _parse_nonneg(tx.get("proceeds"), f"Transaction {idx} proceeds")
            basis = _parse_nonneg(tx.get("cost_basis"), f"Transaction {idx} cost_basis")
            wash_raw = tx.get("wash_sale_disallowed", "0")
            wash = ZERO if _is_blank(wash_raw) else _parse_nonneg(wash_raw, f"Transaction {idx} wash_sale_disallowed")
            wash_sales_total += wash
            gain_loss = proceeds - basis + wash
            if period == "short":
                st_net += gain_loss
            else:
                lt_net += gain_loss

        if missing_basis_or_period:
            return {
                "rule_id": "schedule_d_2025",
                "tax_year": tax_year,
                "filing_status": status_key,
                "status": "REVIEW_REQUIRED",
                "review_note": "One or more transactions have missing proceeds, cost_basis, or holding_period ('short'/'long').",
            }

        combined_net = st_net + lt_net
        loss_limit = CAPITAL_LOSS_LIMIT_2025[status_key]
        if combined_net < ZERO:
            capital_loss_deduction = min(abs(combined_net), loss_limit)
            net_schedule_d_for_1040 = -capital_loss_deduction
            carryover_to_2026 = abs(combined_net) - capital_loss_deduction
        else:
            capital_loss_deduction = ZERO
            net_schedule_d_for_1040 = combined_net
            carryover_to_2026 = ZERO

        review_required = wash_sales_total > ZERO
        return {
            "rule_id": "schedule_d_2025",
            "tax_year": tax_year,
            "filing_status": status_key,
            "status": "REVIEW_REQUIRED" if review_required else "CALCULATED",
            "transaction_count": len(transactions),
            "net_short_term": str(st_net),
            "net_long_term": str(lt_net),
            "combined_net_capital_gain_loss": str(combined_net),
            "wash_sales_disallowed_total": str(wash_sales_total),
            "schedule_d_for_1040_line_7": str(net_schedule_d_for_1040),
            "capital_loss_carryover_reference": str(carryover_to_2026),
            "review_note": (
                "Wash-sale adjustments present; verify Form 8949 codes and 30-day replacement periods."
                if review_required
                else "Reference workpaper only. Verify Form 8949 basis reporting, collectibles/28% rates, and Qualified Dividends/Capital Gain Tax Worksheet."
            ),
        }
