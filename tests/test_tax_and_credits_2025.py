"""Unit and adversarial tests for modules/tax_and_credits_2025.py."""
from decimal import Decimal
import unittest

from core.reconciliation import InputValidationError
from modules.tax_and_credits_2025 import build_tax_and_credits_workpaper


class TaxAndCredits2025Tests(unittest.TestCase):
    def test_progressive_brackets_single_filer(self):
        # Taxable income = 65,000 - 15,000 = 50,000
        # 11,925 * 0.10 = 1,192.50
        # (48,475 - 11,925) = 36,550 * 0.12 = 4,386.00
        # (50,000 - 48,475) = 1,525 * 0.22 = 335.50
        # Total = 5,914.00
        res = build_tax_and_credits_workpaper(
            tax_year=2025,
            filing_status="single",
            agi="65000.00",
            deduction_taken="15000.00",
        )
        self.assertEqual(res["status"], "CALCULATED")
        self.assertEqual(Decimal(res["taxable_income"]), Decimal("50000.00"))
        self.assertEqual(Decimal(res["ordinary_bracket_tax"]), Decimal("5914.00"))

    def test_child_tax_credit_phaseout_and_ltcg_review_flag(self):
        # MFJ AGI = 400,001 -> $1 over $400,000 -> rounds up to 1st $1,000 increment -> $50 reduction
        res = build_tax_and_credits_workpaper(
            tax_year=2025,
            filing_status="married_filing_jointly",
            agi="400001.00",
            deduction_taken="30000.00",
            qualifying_children_under_17=1,
            qualified_dividends_or_ltcg_present=True,
        )
        self.assertEqual(res["status"], "REVIEW_REQUIRED")
        self.assertEqual(Decimal(res["preliminary_ctc_and_odc"]), Decimal("1950"))
        self.assertTrue(any("Qualified Dividends" in r for r in res["review_reasons"]))

    def test_missing_inputs_return_review_required(self):
        res = build_tax_and_credits_workpaper(tax_year=2025, filing_status="single", agi="", deduction_taken="15000")
        self.assertEqual(res["status"], "REVIEW_REQUIRED")
        self.assertEqual(res["missing_fields"], ["agi"])

    def test_32_digit_precision_and_validation_errors(self):
        big = "123456789012345678901234567890.00"
        res = build_tax_and_credits_workpaper(tax_year=2025, filing_status="single", agi=big, deduction_taken="0")
        self.assertEqual(Decimal(res["taxable_income"]), Decimal(big))

        with self.assertRaises(InputValidationError):
            build_tax_and_credits_workpaper(tax_year=2024, filing_status="single", agi="50000", deduction_taken="15000")
        with self.assertRaises(InputValidationError):
            build_tax_and_credits_workpaper(tax_year=2025, filing_status="single", agi="50000", deduction_taken="15000", qualifying_children_under_17=True)
        with self.assertRaises(InputValidationError):
            build_tax_and_credits_workpaper(tax_year=2025, filing_status="single", agi="50000", deduction_taken="15000", qualified_dividends_or_ltcg_present="False")


if __name__ == "__main__":
    unittest.main()
