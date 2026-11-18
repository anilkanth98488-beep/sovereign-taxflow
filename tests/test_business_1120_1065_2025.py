"""Unit and adversarial tests for modules/business_1120_1065_2025.py."""
from decimal import Decimal
import unittest

from core.reconciliation import InputValidationError
from modules.business_1120_1065_2025 import build_business_return_workpaper


class Business11201065Tests(unittest.TestCase):
    def test_1120_corporate_workpaper_and_21pct_tax(self):
        res = build_business_return_workpaper(
            entity_form="1120",
            tax_year=2025,
            gross_receipts="500000.00",
            cogs="200000.00",
            operating_expenses="100000.00",
            book_to_tax_items=[{"code": "MEALS_274N", "amount": "1000.00"}],
            total_assets="1000000.00",
        )
        self.assertEqual(res["status"], "CALCULATED")
        self.assertEqual(Decimal(res["book_net_income"]), Decimal("200000.00"))
        self.assertEqual(Decimal(res["preliminary_taxable_or_ordinary_income"]), Decimal("200500.00"))
        self.assertEqual(Decimal(res["illustrative_1120_tax_21pct"]), Decimal("42105.00"))

    def test_1065_partner_allocation_and_out_of_balance_pct_flag(self):
        res = build_business_return_workpaper(
            entity_form="1065",
            tax_year=2025,
            gross_receipts="100000.00",
            operating_expenses="20000.00",
            partner_allocations=[
                {"partner": "Partner A", "profit_pct": "60"},
                {"partner": "Partner B", "profit_pct": "30"},
            ],
        )
        self.assertEqual(res["status"], "REVIEW_REQUIRED")
        self.assertTrue(any("100%" in r for r in res["review_reasons"]))

    def test_validation_errors(self):
        with self.assertRaises(InputValidationError):
            build_business_return_workpaper(entity_form="1040", tax_year=2025)
        with self.assertRaises(InputValidationError):
            build_business_return_workpaper(entity_form="1120", tax_year=2024)


if __name__ == "__main__":
    unittest.main()
