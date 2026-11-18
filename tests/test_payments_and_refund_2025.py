"""Unit and adversarial tests for modules/payments_and_refund_2025.py."""
from decimal import Decimal
import unittest

from core.reconciliation import InputValidationError
from modules.payments_and_refund_2025 import build_payments_and_refund_workpaper


class PaymentsAndRefund2025Tests(unittest.TestCase):
    def test_refund_scenario(self):
        res = build_payments_and_refund_workpaper(
            tax_year=2025,
            regular_tax_after_credits="5000.00",
            self_employment_tax="1000.00",
            w2_withholding_line_25a="5700.00",
            form_1099_withholding_line_25b="650.00",
        )
        self.assertEqual(res["status"], "CALCULATED")
        self.assertEqual(Decimal(res["total_tax_line_24"]), Decimal("6000.00"))
        self.assertEqual(Decimal(res["total_payments_line_33"]), Decimal("6350.00"))
        self.assertEqual(Decimal(res["overpayment_refund_line_34"]), Decimal("350.00"))
        self.assertEqual(Decimal(res["amount_you_owe_line_37"]), Decimal("0"))
        self.assertFalse(res["form_2210_penalty_review_required"])

    def test_amount_owed_triggers_form_2210_review(self):
        res = build_payments_and_refund_workpaper(
            tax_year=2025,
            regular_tax_after_credits="10000.00",
            w2_withholding_line_25a="5000.00",
        )
        self.assertEqual(res["status"], "REVIEW_REQUIRED")
        self.assertEqual(Decimal(res["amount_you_owe_line_37"]), Decimal("5000.00"))
        self.assertTrue(res["form_2210_penalty_review_required"])

    def test_32_digit_precision_and_validation_errors(self):
        big = "123456789012345678901234567890.12"
        res = build_payments_and_refund_workpaper(tax_year=2025, regular_tax_after_credits=big, w2_withholding_line_25a=big)
        self.assertEqual(Decimal(res["overpayment_refund_line_34"]), Decimal("0"))

        with self.assertRaises(InputValidationError):
            build_payments_and_refund_workpaper(tax_year=2024, regular_tax_after_credits="100")
        with self.assertRaises(InputValidationError):
            build_payments_and_refund_workpaper(tax_year=2025, regular_tax_after_credits="-1")


if __name__ == "__main__":
    unittest.main()
