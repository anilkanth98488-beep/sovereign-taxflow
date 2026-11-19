"""Unit and adversarial tests for modules/schedule_se_2025.py."""
from decimal import Decimal
import unittest

from core.reconciliation import InputValidationError
from modules.schedule_se_2025 import build_schedule_se_workpaper


class ScheduleSE2025Tests(unittest.TestCase):
    def test_standard_schedule_se_and_line_15_deduction(self):
        res = build_schedule_se_workpaper(
            tax_year=2025,
            filing_status="single",
            gross_receipts="100000.00",
            deductible_expenses="20000.00",
        )
        self.assertEqual(res["status"], "CALCULATED")
        self.assertEqual(Decimal(res["schedule_c_net_profit"]), Decimal("80000.00"))
        # 80,000 * 0.9235 = 73,880; * 0.153 = 11,303.64; half = 5,651.82
        self.assertEqual(Decimal(res["net_earnings_from_se"]), Decimal("73880.00"))
        self.assertEqual(Decimal(res["total_se_tax"]), Decimal("11303.64"))
        self.assertEqual(Decimal(res["deductible_half_se_tax_line_15"]), Decimal("5651.82"))

    def test_under_400_threshold_and_net_loss_produce_zero_se_tax(self):
        under = build_schedule_se_workpaper(tax_year=2025, filing_status="single", gross_receipts="400.00")
        self.assertEqual(Decimal(under["total_se_tax"]), Decimal("0"))
        loss = build_schedule_se_workpaper(tax_year=2025, filing_status="single", gross_receipts="1000.00", deductible_expenses="1500.00")
        self.assertEqual(loss["status"], "REVIEW_REQUIRED")
        self.assertEqual(Decimal(loss["total_se_tax"]), Decimal("0"))

    def test_social_security_wage_base_cap_with_w2_wages_and_additional_medicare(self):
        res = build_schedule_se_workpaper(
            tax_year=2025,
            filing_status="single",
            gross_receipts="100000.00",
            w2_social_security_wages="170000.00",
            w2_medicare_wages="170000.00",
        )
        # Remaining SS wage base = 176,100 - 170,000 = 6,100; 170k + 92,350 > 200k triggers Form 8959 review
        self.assertEqual(Decimal(res["taxable_ss_se_earnings"]), Decimal("6100.00"))
        self.assertTrue(res["additional_medicare_review_required"])
        self.assertEqual(res["status"], "REVIEW_REQUIRED")

    def test_32_digit_precision_and_validation_errors(self):
        big = "123456789012345678901234567890.00"
        res = build_schedule_se_workpaper(tax_year=2025, filing_status="single", gross_receipts=big)
        self.assertEqual(Decimal(res["schedule_c_net_profit"]), Decimal(big))

        with self.assertRaises(InputValidationError):
            build_schedule_se_workpaper(tax_year=2024, filing_status="single", gross_receipts="1000")
        with self.assertRaises(InputValidationError):
            build_schedule_se_workpaper(tax_year=2025, filing_status="BANANA", gross_receipts="1000")
        with self.assertRaises(InputValidationError):
            build_schedule_se_workpaper(tax_year=2025, filing_status="single", gross_receipts="-1")


if __name__ == "__main__":
    unittest.main()
