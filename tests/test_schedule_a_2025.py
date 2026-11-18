"""Unit and adversarial tests for modules/schedule_a_2025.py."""
from decimal import Decimal
import unittest

from core.reconciliation import InputValidationError
from modules.schedule_a_2025 import build_schedule_a_workpaper


class ScheduleA2025Tests(unittest.TestCase):
    def test_synthetic_medical_example_2000_deduction(self):
        res = build_schedule_a_workpaper(
            tax_year=2025,
            filing_status="single",
            agi="80000.00",
            eligible_medical_expenses="9000.00",
            medical_reimbursements="1000.00",
        )
        self.assertEqual(res["status"], "CALCULATED")
        self.assertEqual(Decimal(res["medical_expenses"]["net_unreimbursed"]), Decimal("8000.00"))
        self.assertEqual(Decimal(res["medical_expenses"]["agi_7_5pct_floor"]), Decimal("6000.00"))
        self.assertEqual(Decimal(res["medical_expenses"]["schedule_a_line_4"]), Decimal("2000.00"))
        self.assertEqual(res["deduction_recommendation"], "STANDARD_DEDUCTION")

    def test_itemized_exceeds_standard_deduction_with_salt_cap(self):
        res = build_schedule_a_workpaper(
            tax_year=2025,
            filing_status="single",
            agi="100000.00",
            state_and_local_taxes_paid="18000.00",
            mortgage_interest="9000.00",
            charitable_contributions="1000.00",
        )
        self.assertEqual(Decimal(res["salt_deductible"]), Decimal("10000"))
        self.assertEqual(Decimal(res["total_itemized_deductions"]), Decimal("20000.00"))
        self.assertEqual(res["deduction_recommendation"], "ITEMIZE")

    def test_missing_agi_or_filing_status_returns_review_required(self):
        res = build_schedule_a_workpaper(tax_year=2025, filing_status="single", agi="")
        self.assertEqual(res["status"], "REVIEW_REQUIRED")
        self.assertIn("agi", res["missing_fields"])

    def test_32_digit_precision_and_validation_rejections(self):
        big = "123456789012345678901234567890.12"
        res = build_schedule_a_workpaper(tax_year=2025, filing_status="married_filing_jointly", agi="0.00", charitable_contributions=big)
        self.assertEqual(Decimal(res["total_itemized_deductions"]), Decimal(big))

        with self.assertRaises(InputValidationError):
            build_schedule_a_workpaper(tax_year=2025, filing_status="single", agi="50000", eligible_medical_expenses="500", medical_reimbursements="600")
        with self.assertRaises(InputValidationError):
            build_schedule_a_workpaper(tax_year=2024, filing_status="single", agi="50000")
        with self.assertRaises(InputValidationError):
            build_schedule_a_workpaper(tax_year=2025, filing_status="BANANA", agi="50000")


if __name__ == "__main__":
    unittest.main()
