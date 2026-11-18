import unittest
from decimal import Decimal
from io import BytesIO
import pandas as pd
from openpyxl import load_workbook
from core.reconciliation import (
    currency_stripper, sanitize_spreadsheet_text, InputValidationError,
    Sovereign167VReconciler
)

class ReconciliationTests(unittest.TestCase):
    def ledger(self):
        return pd.DataFrame([
            {"Date": "2026-01-01", "Amount": "300.00", "Type": "CREDIT"},
            {"Date": "2026-01-02", "Amount": "50.00", "Type": "DEBIT"},
        ])

    def test_valid_pass(self):
        result = Sovereign167VReconciler(self.ledger(), "1000", "1250").execute_reconciliation()
        self.assertEqual(result.status, "PASS")
        self.assertEqual(result.calculated_closing_balance, "1250.00")

    def test_variance_fail(self):
        self.assertEqual(Sovereign167VReconciler(self.ledger(), "1000", "1251").execute_reconciliation().status, "FAIL")

    def test_bad_amount_is_not_zero(self):
        df = self.ledger(); df.loc[0, "Amount"] = "bad"
        self.assertEqual(Sovereign167VReconciler(df, "0", "0").execute_reconciliation().status, "INPUT ERROR")

    def test_reject_bool_nan_inf_float(self):
        for value in (True, float("nan"), Decimal("NaN"), Decimal("Infinity"), 0.1):
            with self.subTest(value=value):
                with self.assertRaises(InputValidationError): currency_stripper(value)

    def test_money_parsing(self):
        self.assertEqual(currency_stripper("$1,234.56"), Decimal("1234.56"))
        self.assertEqual(currency_stripper("(1,234.50)"), Decimal("-1234.50"))
        self.assertEqual(currency_stripper("-123.45"), Decimal("-123.45"))
        self.assertEqual(currency_stripper("-$1,234.56"), Decimal("-1234.56"))
        self.assertEqual(currency_stripper("$-1,234.56"), Decimal("-1234.56"))

    def test_reject_bad_grouping_and_contradictory_sign(self):
        for value in ("1,2,3", "( -100 )", "(-100)", "100)", "(100", "1 2", "$1$2", "$$1", "1$", "1,23.45"):
            with self.subTest(value=value):
                with self.assertRaises(InputValidationError): currency_stripper(value)

    def test_precision_text_preserved(self):
        raw = "12345678901234567890.123456"
        self.assertEqual(str(currency_stripper(raw)), raw)

    def test_duplicate_headers(self):
        df = pd.DataFrame([["2026-01-01", "1", "2", "CREDIT"]], columns=["Date", "Amount", "Amount", "Type"])
        self.assertEqual(Sovereign167VReconciler(df, "0", "1").execute_reconciliation().status, "INPUT ERROR")

    def test_normalized_duplicate_headers(self):
        df = pd.DataFrame([["2026-01-01", "1", "CREDIT"]], columns=["Date", " Amount ", "amount"])
        self.assertEqual(Sovereign167VReconciler(df, "0", "1").execute_reconciliation().status, "INPUT ERROR")

    def test_invalid_date(self):
        df = self.ledger(); df.loc[0, "Date"] = "not-a-date"
        self.assertEqual(Sovereign167VReconciler(df, "0", "0").execute_reconciliation().status, "INPUT ERROR")

    def test_ambiguous_and_invalid_calendar_dates_rejected(self):
        for raw_date in ("01/02/2026", "2026-02-30", "2026/01/01"):
            with self.subTest(raw_date=raw_date):
                df = self.ledger(); df.loc[0, "Date"] = raw_date
                result = Sovereign167VReconciler(df, "0", "0").execute_reconciliation()
                self.assertEqual(result.status, "INPUT ERROR")

    def test_missing_date_and_type(self):
        df = self.ledger(); df.loc[0, "Date"] = ""
        self.assertEqual(Sovereign167VReconciler(df, "0", "0").execute_reconciliation().status, "INPUT ERROR")
        df = self.ledger(); df.loc[0, "Type"] = "OTHER"
        self.assertEqual(Sovereign167VReconciler(df, "0", "0").execute_reconciliation().status, "INPUT ERROR")

    def test_negative_transaction_and_tolerance(self):
        df = self.ledger(); df.loc[0, "Amount"] = "-1"
        self.assertEqual(Sovereign167VReconciler(df, "0", "0").execute_reconciliation().status, "INPUT ERROR")
        self.assertEqual(Sovereign167VReconciler(self.ledger(), "1000", "1250", "-1").execute_reconciliation().status, "INPUT ERROR")

    def test_formula_injection_whitespace_and_controls(self):
        payloads = ("=1+1", "  =1+1", "+SUM(A1)", "-1+2", "@cmd", "\t=1", "\n=1", "\ufeff=1", "\x00=1", "\u2003=1", "\u200b=1")
        for value in payloads:
            with self.subTest(value=repr(value)):
                self.assertTrue(sanitize_spreadsheet_text(value).startswith("'"))

    def test_safe_text_unchanged(self):
        self.assertEqual(sanitize_spreadsheet_text("ordinary memo"), "ordinary memo")

    def test_xlsx_pass_only(self):
        engine = Sovereign167VReconciler(self.ledger(), "1000", "1250")
        result = engine.execute_reconciliation()
        self.assertIsInstance(engine.export_xlsx(result), BytesIO)
        bad = Sovereign167VReconciler(self.ledger(), "1000", "900").execute_reconciliation()
        with self.assertRaises(InputValidationError): engine.export_xlsx(bad)

    def test_xlsx_exports_money_as_text(self):
        df = pd.DataFrame([
            {"Date": "2026-01-01", "Amount": "0.000001", "Type": "CREDIT"},
        ])
        engine = Sovereign167VReconciler(df, "12345678901234567890.123456", "12345678901234567890.123457", "0.000000")
        result = engine.execute_reconciliation()
        self.assertEqual(result.status, "PASS")
        workbook = load_workbook(engine.export_xlsx(result), data_only=True)
        sheet = workbook["Reconciliation"]
        exported = {sheet.cell(row, 1).value: sheet.cell(row, 2).value for row in range(2, sheet.max_row + 1)}
        self.assertEqual(exported["opening_balance"], "12345678901234567890.123456")
        self.assertIsInstance(exported["opening_balance"], str)

    def test_stale_pass_cannot_export_different_ledger(self):
        original = Sovereign167VReconciler(self.ledger(), "1000", "1250")
        pass_result = original.execute_reconciliation()
        changed = self.ledger(); changed.loc[0, "Amount"] = "301.00"
        with self.assertRaises(InputValidationError):
            Sovereign167VReconciler(changed, "1000", "1250").export_xlsx(pass_result)

    def test_pass_cannot_export_with_changed_parameters(self):
        original = Sovereign167VReconciler(self.ledger(), "1000", "1250")
        pass_result = original.execute_reconciliation()
        with self.assertRaises(InputValidationError):
            Sovereign167VReconciler(self.ledger(), "999", "1250").export_xlsx(pass_result)

    def test_fabricated_pass_cannot_export(self):
        engine = Sovereign167VReconciler(self.ledger(), "1000", "1250")
        result = engine.execute_reconciliation()
        result.status = "PASS"
        result.variance = "999999"
        with self.assertRaises(InputValidationError): engine.export_xlsx(result)

if __name__ == "__main__":
    unittest.main()
