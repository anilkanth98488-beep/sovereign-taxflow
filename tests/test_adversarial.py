"""Adversarial and boundary tests for deterministic workpaper helpers.

These tests verify software behavior only; they do not validate tax-law conclusions.
"""
import random
import unittest
from decimal import Decimal

import pandas as pd

from core.reconciliation import (
    InputValidationError,
    Sovereign167VReconciler,
    currency_stripper,
    sanitize_spreadsheet_text,
)
from modules.book_to_tax import build_book_to_tax_workpaper, m3_threshold_flags
from modules.depreciation_schedule import (
    bonus_rate,
    build_depreciation_schedule,
    partition_assets_by_tax_year,
    section_179_reference,
)
from modules.document_organizer import classify_filename, missing_item_alerts
from modules.financial_statements import build_financial_statements


class AdversarialTests(unittest.TestCase):
    def test_money_parser_rejects_adversarial_strings(self):
        bad_values = ["", " ", "1 2", "1,23", "1,234,56", "$1$", "1$", "--1", "+-1", "( -1 )", "1e6", "NaN", "Infinity"]
        for value in bad_values:
            with self.subTest(value=value):
                with self.assertRaises(InputValidationError):
                    currency_stripper(value)

    def test_money_parser_accepts_supported_currency_formats(self):
        cases = {
            "$1,234.56": Decimal("1234.56"),
            "-$1,234.56": Decimal("-1234.56"),
            "$-1,234.56": Decimal("-1234.56"),
            "(1,234.56)": Decimal("-1234.56"),
            "0": Decimal("0"),
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(currency_stripper(raw), expected)

    def test_reconciliation_randomized_arithmetic(self):
        rng = random.Random(167)
        for _ in range(50):
            opening = rng.randint(0, 1_000_000)
            credits = [rng.randint(0, 10_000) for _ in range(rng.randint(1, 8))]
            debits = [rng.randint(0, 10_000) for _ in range(rng.randint(1, 8))]
            rows = []
            for i, amount in enumerate(credits):
                rows.append({"Date": "2026-01-15", "Amount": str(amount), "Type": "CREDIT"})
            for i, amount in enumerate(debits):
                rows.append({"Date": "2026-01-16", "Amount": str(amount), "Type": "DEBIT"})
            expected = opening + sum(credits) - sum(debits)
            result = Sovereign167VReconciler(pd.DataFrame(rows), str(opening), str(expected), "0").execute_reconciliation()
            self.assertEqual(result.status, "PASS")
            self.assertEqual(Decimal(result.calculated_closing_balance), Decimal(expected))

    def test_reconciliation_rejects_missing_and_extra_required_data(self):
        frame = pd.DataFrame([{"Date": "2026-01-01", "Amount": "10"}])
        self.assertEqual(Sovereign167VReconciler(frame, "0", "10").execute_reconciliation().status, "INPUT ERROR")
        empty = pd.DataFrame(columns=["Date", "Amount", "Type"])
        self.assertEqual(Sovereign167VReconciler(empty, "0", "0").execute_reconciliation().status, "INPUT ERROR")

    def test_spreadsheet_formula_prefixes_are_neutralized(self):
        for value in ["=1+1", "+SUM(A1:A2)", "-10", "@cmd", "\t=1+1", "\ufeff=1+1"]:
            with self.subTest(value=value):
                self.assertTrue(sanitize_spreadsheet_text(value).startswith("'"))
        self.assertEqual(sanitize_spreadsheet_text("ordinary text"), "ordinary text")

    def test_financial_statement_rejects_invalid_statement_and_blank_labels(self):
        base = {"Account": "Cash", "Debit": "10", "Credit": "0", "Statement": "OTHER", "Category": "Assets"}
        with self.assertRaises(InputValidationError):
            build_financial_statements(pd.DataFrame([base]))
        base["Statement"] = "BALANCE SHEET"
        base["Category"] = "   "
        with self.assertRaises(InputValidationError):
            build_financial_statements(pd.DataFrame([base]))

    def test_financial_statement_rejects_missing_columns_and_empty_frame(self):
        with self.assertRaises(InputValidationError):
            build_financial_statements(pd.DataFrame(columns=["Account", "Debit"]))
        columns = ["Account", "Debit", "Credit", "Statement", "Category"]
        with self.assertRaises(InputValidationError):
            build_financial_statements(pd.DataFrame(columns=columns))

    def test_book_to_tax_rejects_boolean_year_and_invalid_entity(self):
        with self.assertRaises(InputValidationError):
            build_book_to_tax_workpaper([], True)
        with self.assertRaises(InputValidationError):
            build_book_to_tax_workpaper([], 2025, entity_type="")
        with self.assertRaises(InputValidationError):
            build_book_to_tax_workpaper([{"code": "UNKNOWN", "amount": "1"}], 2025)

    def test_m3_threshold_rejects_negative_and_non_boolean(self):
        with self.assertRaises(InputValidationError):
            m3_threshold_flags("1065", "-1")
        with self.assertRaises(InputValidationError):
            m3_threshold_flags("1065", "0", "0", "False")

    def test_section_179_rejects_election_above_cost(self):
        with self.assertRaises(InputValidationError):
            section_179_reference(2026, "10000", "10001")

    def test_section_179_rejects_boolean_year_and_suv_flag(self):
        with self.assertRaises(InputValidationError):
            section_179_reference(True, "10000", "0")
        with self.assertRaises(InputValidationError):
            section_179_reference(2026, "10000", "0", suv="False")

    def test_depreciation_rejects_non_boolean_flags(self):
        with self.assertRaises(InputValidationError):
            bonus_rate("2025-01-20", "2025-02-01", long_production_period="False")
        with self.assertRaises(InputValidationError):
            bonus_rate("2025-01-20", "2025-02-01", binding_contract_before_cutoff="False")

    def test_depreciation_rejects_boolean_tax_year(self):
        with self.assertRaises(InputValidationError):
            build_depreciation_schedule([], True)
        with self.assertRaises(InputValidationError):
            partition_assets_by_tax_year([], True)

    def test_depreciation_rejects_invalid_asset_cost(self):
        rows = [{"asset": "bad", "cost": "not-money", "acquisition_date": "2026-01-01", "placed_in_service_date": "2026-02-01"}]
        with self.assertRaises(InputValidationError):
            build_depreciation_schedule(rows, 2026)

    def test_depreciation_rejects_unrecognized_boolean_text(self):
        rows = [{"asset": "bad flag", "cost": "100", "acquisition_date": "2026-01-01", "placed_in_service_date": "2026-02-01", "long_production_period": "maybe"}]
        with self.assertRaises(InputValidationError):
            build_depreciation_schedule(rows, 2026)

    def test_document_router_handles_ambiguous_and_empty_names(self):
        self.assertEqual(classify_filename("client_1040_1120.pdf")["suggested_form"], "REVIEW")
        self.assertEqual(classify_filename("K-1.pdf")["suggested_form"], "REVIEW")
        self.assertEqual(classify_filename(".")["suggested_form"], "REVIEW")

    def test_missing_item_alerts_rejects_unknown_form(self):
        with self.assertRaises(ValueError):
            missing_item_alerts("9999", [])


if __name__ == "__main__":
    unittest.main()
