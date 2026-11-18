import unittest
from decimal import Decimal
import pandas as pd
from core.reconciliation import InputValidationError
from modules.financial_statements import build_financial_statements
from modules.book_to_tax import build_book_to_tax_workpaper, m3_threshold_flags
from modules.depreciation_schedule import (
    bonus_rate, section_179_reference, build_depreciation_schedule, partition_assets_by_tax_year
)
from modules.document_organizer import classify_filename, missing_item_alerts

class ModuleTests(unittest.TestCase):
    def test_financial_statements_and_tb_out_of_balance(self):
        df = pd.DataFrame([
            {"Account":"Sales", "Debit":"0", "Credit":"100", "Statement":"P&L", "Category":"Revenue"},
            {"Account":"Rent", "Debit":"20", "Credit":"0", "Statement":"P&L", "Category":"Expense"},
        ])
        result = build_financial_statements(df)
        self.assertEqual(result["profit_and_loss"]["Revenue"], "-100")
        self.assertEqual(result["trial_balance_status"], "OUT OF BALANCE")
        self.assertEqual(result["trial_balance_difference"], "-80")

    def test_balanced_trial_balance(self):
        df = pd.DataFrame([
            {"Account":"Cash", "Debit":"100", "Credit":"0", "Statement":"BALANCE SHEET", "Category":"Assets"},
            {"Account":"Capital", "Debit":"0", "Credit":"100", "Statement":"BALANCE SHEET", "Category":"Equity"},
        ])
        self.assertEqual(build_financial_statements(df)["trial_balance_status"], "BALANCED")

    def test_negative_both_sides_and_duplicate_headers_rejected(self):
        df = pd.DataFrame([{"Account":"A", "Debit":"-1", "Credit":"0", "Statement":"P&L", "Category":"Expense"}])
        with self.assertRaises(InputValidationError): build_financial_statements(df)
        missing_label = pd.DataFrame([{"Account": None, "Debit": "0", "Credit": "0", "Statement": "P&L", "Category": "Expense"}])
        with self.assertRaises(InputValidationError): build_financial_statements(missing_label)
        df = pd.DataFrame([["A","0","0","P&L","X","Y"]], columns=["Account","Debit","Credit","Statement","Category","Category"])
        with self.assertRaises(InputValidationError): build_financial_statements(df)

    def test_both_debit_and_credit_rejected(self):
        df = pd.DataFrame([{"Account":"A", "Debit":"1", "Credit":"1", "Statement":"P&L", "Category":"Expense"}])
        with self.assertRaises(InputValidationError): build_financial_statements(df)

    def test_274o_year_assumptions(self):
        items = [{"code":"CONVENIENCE_MEALS_274O", "amount":"100"}]
        self.assertEqual(build_book_to_tax_workpaper(items, 2025)["quantified_proposed_addbacks_total"], "50.00")
        self.assertEqual(build_book_to_tax_workpaper(items, 2026)["quantified_proposed_addbacks_total"], "100.00")

    def test_162f_is_held_for_review_and_103_flagged(self):
        result = build_book_to_tax_workpaper([
            {"code":"FINES_162F", "amount":"100"},
            {"code":"MUNI_INTEREST_103", "amount":"40"},
        ], 2025)
        self.assertEqual(result["items"][0]["proposed_addback"], "REVIEW_REQUIRED")
        self.assertEqual(result["unresolved_review_amount_total"], "100")
        self.assertEqual(result["proposed_exclusions_total"], "40")

    def test_meals_274n_default_placeholder(self):
        result = build_book_to_tax_workpaper([{"code":"MEALS_274N", "amount":"100"}], 2025)
        self.assertEqual(result["quantified_proposed_addbacks_total"], "50.00")

    def test_m3_preliminary_flags(self):
        self.assertTrue(m3_threshold_flags("1120", "10000000")["schedule_m3_required_preliminary"])
        self.assertTrue(m3_threshold_flags("1120-S", "50000000")["schedule_m3_full_parts_ii_iii_threshold"])
        self.assertTrue(m3_threshold_flags("1065", "0", "35000000")["schedule_m3_required_preliminary"])
        with self.assertRaises(InputValidationError): m3_threshold_flags("BAD", "0")
        with self.assertRaises(InputValidationError): m3_threshold_flags("1065", "0", "0", "False")

    def test_bonus_cutoff_reference(self):
        self.assertEqual(bonus_rate("2025-01-20", "2025-02-01"), Decimal("1.00"))
        self.assertEqual(bonus_rate("2025-01-19", "2025-12-01"), Decimal("0.40"))
        self.assertEqual(bonus_rate("2025-01-19", "2026-03-01"), Decimal("0.20"))
        self.assertEqual(bonus_rate("2025-02-01", "2026-03-01", binding_contract_before_cutoff=True), Decimal("0.20"))

    def test_long_production_period_withheld_for_review(self):
        with self.assertRaises(InputValidationError): bonus_rate("2025-01-20", "2026-03-01", long_production_period=True)

    def test_acquisition_after_placed_in_service_rejected(self):
        with self.assertRaises(InputValidationError): bonus_rate("2026-02-01", "2026-01-01")

    def test_partition_assets_reports_invalid_dates(self):
        rows = [
            {"asset": "valid-current", "placed_in_service_date": "2026-02-01"},
            {"asset": "valid-other", "placed_in_service_date": "2025-06-01"},
            {"asset": "bad-date", "placed_in_service_date": "not-a-date"},
        ]
        selected, other, invalid = partition_assets_by_tax_year(rows, 2026)
        self.assertEqual([row["asset"] for row in selected], ["valid-current"])
        self.assertEqual([row["asset"] for row in other], ["valid-other"])
        self.assertEqual(invalid[0]["asset"], "bad-date")

    def test_section_179_reference(self):
        self.assertEqual(section_179_reference(2025, "0")["statutory_reference_limit"], "2500000")
        self.assertEqual(section_179_reference(2026, "0")["statutory_reference_limit"], "2560000")
        self.assertEqual(section_179_reference(2026, "6650000")["statutory_reference_limit"], "0")

    def test_document_router_explicit_form_only(self):
        self.assertEqual(classify_filename("Client_1040_W2.pdf")["suggested_form"], "1040")
        self.assertEqual(classify_filename("Partnership_1065_K1.pdf")["suggested_form"], "1065")
        self.assertEqual(classify_filename("Client_1120-S_K1.pdf")["suggested_form"], "1120-S")
        self.assertEqual(classify_filename("Client_1120_K1.pdf")["suggested_form"], "1120")
        self.assertEqual(classify_filename("Generic_K1.pdf")["suggested_form"], "REVIEW")
        self.assertIn("corporate", missing_item_alerts("1120", []))
        self.assertEqual(classify_filename("Client_1120-S_K1_1065.pdf")["suggested_form"], "REVIEW")
        self.assertEqual(classify_filename("Generic_K1.pdf")["suggested_form"], "REVIEW")

if __name__ == "__main__":
    unittest.main()
