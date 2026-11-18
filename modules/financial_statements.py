"""Explicitly mapped trial-balance workpapers."""
from decimal import Decimal, localcontext
import pandas as pd
from core.reconciliation import currency_stripper, InputValidationError, validate_headers, MONEY_CONTEXT

REQUIRED = {"Account", "Debit", "Credit", "Statement", "Category"}

def build_financial_statements(trial_balance: pd.DataFrame) -> dict:
    df = trial_balance.copy(deep=True)
    validate_headers(df)
    df.columns = [str(c).strip() for c in df.columns]
    missing = REQUIRED - set(df.columns)
    if missing:
        raise InputValidationError(f"Missing columns: {sorted(missing)}")
    if df.empty:
        raise InputValidationError("Trial balance is empty.")
    with localcontext(MONEY_CONTEXT):
        return _compute_financial_statements(df)


def _compute_financial_statements(df: pd.DataFrame) -> dict:
    pnl, bs = {}, {}
    total_debits = total_credits = Decimal("0")
    for index, row in df.iterrows():
        raw_account, raw_category = row["Account"], row["Category"]
        if pd.isna(raw_account) or pd.isna(raw_category):
            raise InputValidationError(f"Row {index}: Account and Category are required.")
        account = str(raw_account).strip()
        category = str(raw_category).strip()
        if not account or not category:
            raise InputValidationError(f"Row {index}: Account and Category are required.")
        debit = currency_stripper(row["Debit"])
        credit = currency_stripper(row["Credit"])
        if debit < 0 or credit < 0:
            raise InputValidationError(f"Row {index}: Debit and Credit must be nonnegative.")
        if debit and credit:
            raise InputValidationError(f"Row {index}: populate Debit or Credit, not both.")
        statement = str(row["Statement"]).strip().upper()
        if statement not in {"P&L", "BALANCE SHEET"}:
            raise InputValidationError(f"Row {index}: Statement must be P&L or BALANCE SHEET.")
        total_debits += debit
        total_credits += credit
        target = pnl if statement == "P&L" else bs
        target[category] = target.get(category, Decimal("0")) + debit - credit
    difference = total_debits - total_credits
    return {
        "profit_and_loss": {k: str(v) for k, v in sorted(pnl.items())},
        "balance_sheet": {k: str(v) for k, v in sorted(bs.items())},
        "p_and_l_net": str(sum(pnl.values(), Decimal("0"))),
        "balance_sheet_net": str(sum(bs.values(), Decimal("0"))),
        "total_debits": str(total_debits), "total_credits": str(total_credits),
        "trial_balance_difference": str(difference),
        "trial_balance_status": "BALANCED" if difference == 0 else "OUT OF BALANCE",
        "review_note": "Draft mapping only. Confirm account classifications, normal balances, retained earnings, and financial-statement presentation with CPA reviewer."
    }
