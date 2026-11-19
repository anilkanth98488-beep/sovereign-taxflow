"""Unit and adversarial tests for modules/exempt_990_2025.py."""
from decimal import Decimal
import unittest

from core.reconciliation import InputValidationError
from modules.exempt_990_2025 import build_990_workpaper


class Exempt9902025Tests(unittest.TestCase):
    def test_990ez_tier_and_program_ratio(self):
        res = build_990_workpaper(
            tax_year=2025,
            contributions_and_grants="120000.00",
            program_service_revenue="30000.00",
            program_service_expenses="80000.00",
            management_and_general_expenses="20000.00",
            total_end_of_year_assets="250000.00",
        )
        self.assertEqual(res["status"], "CALCULATED")
        self.assertEqual(res["suggested_form_tier_reference"], "990-EZ")
        self.assertEqual(Decimal(res["program_expense_ratio_pct"]), Decimal("80.00"))

    def test_990_tier_and_ubit_flag(self):
        res = build_990_workpaper(
            tax_year=2025,
            contributions_and_grants="250000.00",
            unrelated_business_gross_income="1500.00",
        )
        self.assertEqual(res["status"], "REVIEW_REQUIRED")
        self.assertEqual(res["suggested_form_tier_reference"], "990")
        self.assertTrue(res["form_990t_ubit_review_required"])

    def test_validation_errors(self):
        with self.assertRaises(InputValidationError):
            build_990_workpaper(tax_year=2024)
        with self.assertRaises(InputValidationError):
            build_990_workpaper(tax_year=2025, contributions_and_grants="-1")


if __name__ == "__main__":
    unittest.main()
