"""Smoke tests for the included synthetic sample CSVs."""
from pathlib import Path
import unittest
import pandas as pd
from core.reconciliation import Sovereign167VReconciler
from modules.financial_statements import build_financial_statements
from modules.book_to_tax import build_book_to_tax_workpaper
from modules.depreciation_schedule import build_depreciation_schedule, partition_assets_by_tax_year

DATA = Path(__file__).resolve().parents[1] / "sample_data"

class SampleDataTests(unittest.TestCase):
    def test_sample_ledger_passes_expected_arithmetic(self):
        df = pd.read_csv(DATA / "sample_ledger.csv", dtype=str, keep_default_na=False)
        result = Sovereign167VReconciler(df, "1000.00", "1250.00", "0.01").execute_reconciliation()
        self.assertEqual(result.status, "PASS")

    def test_sample_trial_balance_is_flagged_out_of_balance(self):
        df = pd.read_csv(DATA / "sample_trial_balance.csv", dtype=str, keep_default_na=False)
        result = build_financial_statements(df)
        self.assertEqual(result["trial_balance_status"], "OUT OF BALANCE")
        self.assertEqual(result["trial_balance_difference"], "-750.00")

    def test_sample_book_to_tax_has_review_required_fines(self):
        items = pd.read_csv(DATA / "sample_book_to_tax.csv", dtype=str, keep_default_na=False).to_dict("records")
        result = build_book_to_tax_workpaper(items, 2026)
        self.assertEqual(result["unresolved_review_amount_total"], "250.00")

    def test_sample_assets_separated_by_tax_year(self):
        items = pd.read_csv(DATA / "sample_assets.csv", dtype=str, keep_default_na=False).to_dict("records")
        for year in (2025, 2026):
            subset, excluded, invalid = partition_assets_by_tax_year(items, year)
            self.assertEqual(invalid, [])
            self.assertEqual(len(subset) + len(excluded), len(items))
            result = build_depreciation_schedule(subset, year)
            self.assertEqual(result["tax_year"], year)

if __name__ == "__main__":
    unittest.main()
