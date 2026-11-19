"""Unit and adversarial tests for modules/scorp_1120s_2025.py."""
from decimal import Decimal
import unittest

from core.reconciliation import InputValidationError
from modules.scorp_1120s_2025 import build_1120s_workpaper


class SCorp1120S2025Tests(unittest.TestCase):
    def test_1120s_officer_comp_and_form_7203_basis(self):
        res = build_1120s_workpaper(
            tax_year=2025,
            gross_receipts="300000.00",
            officer_compensation="80000.00",
            other_operating_expenses="120000.00",
            shareholders=[
                {"name": "Owner A", "ownership_pct": "100", "beginning_stock_basis": "10000.00", "distributions": "50000.00"},
            ],
        )
        self.assertEqual(res["status"], "CALCULATED")
        self.assertEqual(Decimal(res["ordinary_business_income"]), Decimal("100000.00"))
        self.assertEqual(Decimal(res["shareholders"][0]["ending_stock_basis"]), Decimal("60000.00"))

    def test_zero_officer_comp_and_excess_distribution_flagged(self):
        res = build_1120s_workpaper(
            tax_year=2025,
            gross_receipts="100000.00",
            officer_compensation="0",
            shareholders=[
                {"name": "Owner A", "ownership_pct": "100", "beginning_stock_basis": "5000.00", "distributions": "120000.00"},
            ],
        )
        self.assertEqual(res["status"], "REVIEW_REQUIRED")
        self.assertEqual(Decimal(res["shareholders"][0]["distributions_in_excess_of_basis"]), Decimal("15000.00"))
        self.assertGreaterEqual(len(res["review_reasons"]), 2)

    def test_validation_errors(self):
        with self.assertRaises(InputValidationError):
            build_1120s_workpaper(tax_year=2024)
        with self.assertRaises(InputValidationError):
            build_1120s_workpaper(tax_year=2025, gross_receipts="-1")


if __name__ == "__main__":
    unittest.main()
