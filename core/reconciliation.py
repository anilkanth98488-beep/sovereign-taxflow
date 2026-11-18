"""Deterministic ledger reconciliation with integrity-bound XLSX exports.

A PASS means only that the arithmetic check described here passed. It is not
an audit opinion, tax conclusion, assurance, or validation of source completeness.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from decimal import Context, Decimal, InvalidOperation, localcontext
from hashlib import sha256
from io import BytesIO
import json
import re
import unicodedata
from typing import Any

import pandas as pd

ZERO = Decimal("0")
MAX_SIGNIFICANT_DIGITS = 50
MONEY_CONTEXT = Context(prec=64)
_CURRENCY = re.compile(r"[$€£₹¥]")
_PLAIN = re.compile(r"\d+(?:\.\d+)?")
_GROUPED = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?")
_PREFIX = re.compile(r"(?:[$€£₹¥][+-]?|[+-]?[$€£₹¥]?)\s*")
_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


class InputValidationError(ValueError):
    """Raised when data cannot safely be used for a workpaper calculation."""


def currency_stripper(value: Any) -> Decimal:
    """Parse money to Decimal without float conversion or silent zero coercion.

    Supports integer, Decimal, and text values such as "$1,234.56" or
    "(1,234.56)". Floats, booleans, non-finite values, malformed grouping,
    contradictory signs, and blank values are rejected.
    """
    if isinstance(value, bool) or value is None or isinstance(value, float):
        raise InputValidationError("Boolean, missing, and float amounts are rejected; ingest original money as text.")
    if isinstance(value, Decimal):
        amount = value
    elif isinstance(value, int):
        amount = Decimal(value)
    elif isinstance(value, str):
        raw = value.strip()
        if not raw:
            raise InputValidationError("Monetary amount is missing.")
        paren = raw.startswith("(") or raw.endswith(")")
        if paren and not (raw.startswith("(") and raw.endswith(")")):
            raise InputValidationError(f"Unbalanced parentheses in amount: {value!r}")
        if paren:
            raw = raw[1:-1].strip()
            if raw.startswith(("+", "-")):
                raise InputValidationError("Do not combine a leading sign with parenthetical negatives.")
        prefix = _PREFIX.match(raw)
        if prefix is None:
            raise InputValidationError(f"Invalid monetary amount prefix: {value!r}")
        sign_and_currency = prefix.group(0).strip()
        if paren and ("+" in sign_and_currency or "-" in sign_and_currency):
            raise InputValidationError("Do not combine a sign with parenthetical negatives.")
        number = raw[prefix.end():]
        if not (_PLAIN.fullmatch(number) or _GROUPED.fullmatch(number)):
            raise InputValidationError(f"Invalid monetary amount or comma grouping: {value!r}")
        sign = "-" if "-" in sign_and_currency else ("+" if "+" in sign_and_currency else "")
        amount = Decimal(sign + number.replace(",", ""))
        if paren:
            amount = -amount
    else:
        raise InputValidationError(f"Unsupported monetary type: {type(value).__name__}")
    if not amount.is_finite():
        raise InputValidationError("NaN and Infinity are invalid monetary amounts.")
    if len(amount.as_tuple().digits) > MAX_SIGNIFICANT_DIGITS:
        raise InputValidationError(
            f"Monetary amount exceeds supported {MAX_SIGNIFICANT_DIGITS}-digit precision limit."
        )
    return amount


def _dangerous_leading_character(text: str) -> bool:
    for char in text:
        # Ignore Unicode whitespace, control, format and BOM characters when
        # identifying a formula prefix; preserve original text in output.
        if char == "\ufeff" or char.isspace() or unicodedata.category(char) in {"Cc", "Cf", "Zs", "Zl", "Zp"}:
            continue
        return char in "=+-@"
    return False


def sanitize_spreadsheet_text(value: Any) -> str:
    """Prefix untrusted text that could be interpreted as a spreadsheet formula."""
    text = str(value)
    return "'" + text if _dangerous_leading_character(text) else text


def validate_headers(df: pd.DataFrame) -> None:
    if not df.columns.is_unique:
        dupes = df.columns[df.columns.duplicated()].tolist()
        raise InputValidationError(f"Duplicate column headers rejected: {dupes}")
    normalized = [str(c).strip().casefold() for c in df.columns]
    if len(normalized) != len(set(normalized)):
        raise InputValidationError("Column headers collide after trimming/case normalization.")


def _frame_fingerprint(df: pd.DataFrame) -> str:
    """Stable digest of the current frame's column names and cell values."""
    payload = {
        "columns": [str(c) for c in df.columns],
        "rows": [[None if pd.isna(v) else str(v) for v in row] for row in df.itertuples(index=False, name=None)],
    }
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8")
    return sha256(encoded).hexdigest()


@dataclass
class ReconciliationResult:
    status: str
    opening_balance: str
    credits: str
    debits: str
    calculated_closing_balance: str
    expected_closing_balance: str
    variance: str
    tolerance: str
    row_count: int
    exceptions: list[str]
    input_fingerprint: str
    parameters_fingerprint: str
    protocol: str = "Sovereign167VReconciler-v2.15-workpaper"
    timestamp_utc: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class Sovereign167VReconciler:
    """Reconcile opening + credits - debits to an expected closing balance."""
    REQUIRED_COLUMNS = {"Date", "Amount", "Type"}

    def __init__(self, df_ledger: pd.DataFrame, opening_balance: Any,
                 expected_closing_balance: Any, tolerance: Any = "0.01"):
        self.raw_df = df_ledger.copy(deep=True)
        self.opening_balance = opening_balance
        self.expected_closing_balance = expected_closing_balance
        self.tolerance = tolerance

    def _parameters_fingerprint(self) -> str:
        values = [str(self.opening_balance), str(self.expected_closing_balance), str(self.tolerance)]
        return sha256(json.dumps(values, separators=(",", ":")).encode()).hexdigest()

    def execute_reconciliation(self) -> ReconciliationResult:
        errors: list[str] = []
        input_hash = _frame_fingerprint(self.raw_df)
        param_hash = self._parameters_fingerprint()
        try:
            validate_headers(self.raw_df)
            self.raw_df.columns = [str(c).strip() for c in self.raw_df.columns]
            missing = self.REQUIRED_COLUMNS - set(self.raw_df.columns)
            if missing:
                raise InputValidationError(f"Missing required columns: {sorted(missing)}")
            if self.raw_df.empty:
                raise InputValidationError("Ledger contains no rows.")
            with localcontext(MONEY_CONTEXT):
                opening = currency_stripper(self.opening_balance)
                expected = currency_stripper(self.expected_closing_balance)
                tolerance = currency_stripper(self.tolerance)
                if tolerance < ZERO:
                    raise InputValidationError("Tolerance cannot be negative.")
                credits = debits = ZERO
                for index, row in self.raw_df.iterrows():
                    raw_date = row["Date"]
                    if pd.isna(raw_date) or not str(raw_date).strip():
                        raise InputValidationError(f"Row {index}: missing date.")
                    date_text = str(raw_date).strip()
                    if not _ISO_DATE.fullmatch(date_text):
                        raise InputValidationError(f"Row {index}: date must use YYYY-MM-DD format; got {raw_date!r}.")
                    try:
                        parsed_date = pd.to_datetime(date_text, errors="raise", format="%Y-%m-%d")
                    except Exception as exc:
                        raise InputValidationError(f"Row {index}: invalid calendar date {raw_date!r}.") from exc
                    if pd.isna(parsed_date):
                        raise InputValidationError(f"Row {index}: invalid date.")
                    amount = currency_stripper(row["Amount"])
                    if amount < ZERO:
                        raise InputValidationError(f"Row {index}: amount must be nonnegative; Type determines direction.")
                    kind = str(row["Type"]).strip().upper()
                    if kind == "CREDIT":
                        credits += amount
                    elif kind == "DEBIT":
                        debits += amount
                    else:
                        raise InputValidationError(f"Row {index}: Type must be CREDIT or DEBIT, got {kind!r}.")
                calculated = opening + credits - debits
                variance = calculated - expected
                status = "PASS" if abs(variance) <= tolerance else "FAIL"
            return self._make_result(status, opening, credits, debits, calculated,
                                     expected, variance, tolerance, len(self.raw_df), errors,
                                     input_hash, param_hash)
        except (InputValidationError, InvalidOperation, TypeError, ValueError) as exc:
            errors.append(str(exc))
            return self._make_result("INPUT ERROR", ZERO, ZERO, ZERO, ZERO, ZERO,
                                     ZERO, ZERO, len(self.raw_df), errors, input_hash, param_hash)

    @staticmethod
    def _make_result(status, opening, credits, debits, calculated, expected,
                     variance, tolerance, row_count, errors, input_hash, param_hash):
        return ReconciliationResult(
            status, *map(str, (opening, credits, debits, calculated, expected, variance, tolerance)),
            row_count, list(errors), input_hash, param_hash,
            timestamp_utc=datetime.now(timezone.utc).isoformat()
        )

    def export_xlsx(self, result: ReconciliationResult) -> BytesIO:
        """Export only if a fresh recomputation matches the supplied PASS result."""
        if not isinstance(result, ReconciliationResult) or result.status != "PASS":
            raise InputValidationError("XLSX export is disabled unless a valid PASS result is supplied.")
        fresh = self.execute_reconciliation()
        comparable = ("status", "opening_balance", "credits", "debits", "calculated_closing_balance",
                      "expected_closing_balance", "variance", "tolerance", "row_count",
                      "input_fingerprint", "parameters_fingerprint", "protocol")
        if fresh.status != "PASS" or any(getattr(result, key) != getattr(fresh, key) for key in comparable):
            raise InputValidationError("PASS result does not match the current ledger and reconciliation parameters.")
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill
        wb = Workbook()
        ws = wb.active
        ws.title = "Reconciliation"
        ws.append(["Field", "Value"])
        ws[1][0].font = ws[1][1].font = Font(bold=True)
        ws[1][0].fill = ws[1][1].fill = PatternFill("solid", fgColor="D9EAF7")
        export_data = result.to_dict()
        for key, value in export_data.items():
            # All exported values are strings to preserve >15-digit money values.
            ws.append([sanitize_spreadsheet_text(key), sanitize_spreadsheet_text(value)])
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
        ws.column_dimensions["A"].width = 30
        ws.column_dimensions["B"].width = 70
        out = BytesIO()
        wb.save(out)
        out.seek(0)
        return out
