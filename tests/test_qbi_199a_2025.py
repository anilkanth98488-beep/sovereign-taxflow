"""Unit and adversarial tests for modules/qbi_199a_2025.py."""
from decimal import Decimal
import unittest

from core.reconciliation import InputValidationError
from modules.qbi_199a_2025 import build_qbi_199a_workpaper


class QBI199A2025Tests(unittest.TestCase):
    def test_simplified_qbi_and_taxable_income_limitation(self):
        # 20% of 100k QBI = 20k; 20% of (80k - 10k) = 14k -> limited to 14k
        res = build_qbi_199a_workpaper(
            tax_year=2025,
            filing_status="single",
            qualified_business_income="100000.00",
            taxable_income_before_qbi="80000.00",
            net_capital_gain="10000.00",
        )
        self.assertEqual(res["status"], "CALCULATED")
        self.assertEqual(Decimal(res["qbi_deduction_line_13"]), Decimal("14000.00"))

    def test_above_threshold_triggers_form_8995a_review(self):
        res = build_qbi_199a_workpaper(
            tax_year=2025,
            filing_status="single",
            qualified_business_income="100000.00",
            taxable_income_before_qbi="200000.00",
        )
        self.assertEqual(res["status"], "REVIEW_REQUIRED")
        self.assertIsNone(res["qbi_deduction_line_13"])

    def test_negative_qbi_carries_forward(self):
        res = build_qbi_199a_workpaper(
            tax_year=2025,
            filing_status="single",
            qualified_business_income="-5000.00",
            taxable_income_before_qbi="50000.00",
        )
        self.assertEqual(res["status"], "CALCULATED")
        self.assertEqual(Decimal(res["qbi_deduction_line_13"]), Decimal("0"))
        self.assertEqual(Decimal(res["qbi_loss_carryforward_to_2026"]), Decimal("5000.00"))

    def test_validation_errors(self):
        with self.assertRaises(InputValidationError):
            build_qbi_199a_workpaper(tax_year=2024, filing_status="single", qualified_business_income="100", taxable_income_before_qbi="100")
        with self.assertRaises(InputValidationError):
            build_qbi_199a_workpaper(tax_year=2025, filing_status="BANANA", qualified_business_income="100", taxable_income_before_qbi="100")


if __name__ == "__main__":
    unittest.main()
