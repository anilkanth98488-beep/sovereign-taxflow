"""Deterministic QuickBooks / Xero / Bank CSV mapper for Sovereign TaxFlow.

Normalizes real-world bank or accounting CSV exports into the strict
`Date, Amount, Type` DataFrame schema required by Sovereign167VReconciler,
without silent zero coercion or ambiguous date guessing.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from io import BytesIO
import re
from typing import Any

import pandas as pd

from core.reconciliation import (
    InputValidationError,
    currency_stripper,
    sanitize_spreadsheet_text,
    validate_headers,
)

ZERO = Decimal("0")
_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def _parse_iso_or_explicit_date(raw: Any, date_format: str | None) -> str:
    if _is_blank(raw):
        raise InputValidationError("Missing transaction date.")
    text = str(raw).strip()
    if date_format is None:
        if not _ISO_DATE.fullmatch(text):
            raise InputValidationError(
                f"Ambiguous or non-ISO date {raw!r}; use YYYY-MM-DD or pass explicit date_format."
            )
        datetime.strptime(text, "%Y-%m-%d")
        return text
    try:
        parsed = datetime.strptime(text, date_format)
    except ValueError as exc:
        raise InputValidationError(f"Invalid date {raw!r} for format {date_format!r}.") from exc
    return parsed.strftime("%Y-%m-%d")


def map_bank_csv_to_ledger(
    csv_bytes: bytes,
    *,
    date_col: str = "Date",
    amount_col: str | None = "Amount",
    type_col: str | None = "Type",
    debit_col: str | None = None,
    credit_col: str | None = None,
    memo_col: str | None = None,
    date_format: str | None = None,
) -> pd.DataFrame:
    """Map an uploaded bank/QuickBooks/Xero CSV into strict Date, Amount, Type (+ optional Memo)."""
    if not isinstance(csv_bytes, (bytes, bytearray)) or len(csv_bytes) == 0:
        raise InputValidationError("CSV file is empty.")

    df = pd.read_csv(BytesIO(bytes(csv_bytes)), dtype=str, keep_default_na=False, encoding="utf-8-sig")
    validate_headers(df)
    df.columns = [str(c).strip() for c in df.columns]
    if df.empty:
        raise InputValidationError("CSV contains no transaction rows.")

    if date_col not in df.columns:
        raise InputValidationError(f"Missing date column {date_col!r}.")

    using_split_dc = debit_col is not None or credit_col is not None
    if using_split_dc:
        if not debit_col or not credit_col:
            raise InputValidationError("Both debit_col and credit_col must be specified together.")
        for col in (debit_col, credit_col):
            if col not in df.columns:
                raise InputValidationError(f"Missing column {col!r}.")
    else:
        if not amount_col or amount_col not in df.columns:
            raise InputValidationError(f"Missing amount column {amount_col!r}.")
        if type_col is not None and type_col not in df.columns:
            raise InputValidationError(f"Missing type column {type_col!r}.")

    if memo_col is not None and memo_col not in df.columns:
        raise InputValidationError(f"Missing memo column {memo_col!r}.")

    mapped_rows: list[dict[str, str]] = []
    for idx, row in df.iterrows():
        iso_date = _parse_iso_or_explicit_date(row[date_col], date_format)

        if using_split_dc:
            d_raw = row[debit_col]
            c_raw = row[credit_col]
            d_amt = ZERO if _is_blank(d_raw) else currency_stripper(d_raw)
            c_amt = ZERO if _is_blank(c_raw) else currency_stripper(c_raw)
            if d_amt < ZERO or c_amt < ZERO:
                raise InputValidationError(f"Row {idx}: Debit and Credit values must be nonnegative.")
            if d_amt > ZERO and c_amt > ZERO:
                raise InputValidationError(f"Row {idx}: populate Debit or Credit, not both.")
            if d_amt == ZERO and c_amt == ZERO:
                raise InputValidationError(f"Row {idx}: both Debit and Credit are zero/blank.")
            if c_amt > ZERO:
                out_amt, out_type = str(c_amt), "CREDIT"
            else:
                out_amt, out_type = str(d_amt), "DEBIT"
        else:
            amt = currency_stripper(row[amount_col])
            if type_col is not None:
                if amt < ZERO:
                    raise InputValidationError(f"Row {idx}: negative amount rejected when Type column is used.")
                kind = str(row[type_col]).strip().upper()
                if kind not in {"CREDIT", "DEBIT"}:
                    raise InputValidationError(f"Row {idx}: Type must be CREDIT or DEBIT, got {kind!r}.")
                out_amt, out_type = str(amt), kind
            else:
                if amt > ZERO:
                    out_amt, out_type = str(amt), "CREDIT"
                elif amt < ZERO:
                    out_amt, out_type = str(abs(amt)), "DEBIT"
                else:
                    raise InputValidationError(f"Row {idx}: zero signed amount cannot determine CREDIT/DEBIT.")

        out_row = {"Date": iso_date, "Amount": out_amt, "Type": out_type}
        if memo_col is not None:
            out_row["Memo"] = sanitize_spreadsheet_text(row[memo_col])
        mapped_rows.append(out_row)

    return pd.DataFrame(mapped_rows)
