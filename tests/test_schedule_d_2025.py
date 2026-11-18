"""Unit and adversarial tests for modules/schedule_d_2025.py."""
from decimal import Decimal
import unittest

from core.reconciliation import InputValidationError
from modules.schedule_d_2025 import build_schedule_d_workpaper


class ScheduleD2025Tests(unittest.TestCase):
    def test_net_gain_and_wash_sale_review_flag(self):
        txs = [
            {"holding_period": "short", "proceeds": "10000.00", "cost_basis": "8000.00", "wash_sale_disallowed": "0"},
            {"holding_period": "long", "proceeds": "5000.00", "cost_basis": "6000.00", "wash_sale_disallowed": "200.00"},
        ]
        res = build_schedule_d_workpaper(txs, tax_year=2025, filing_status="single")
        self.assertEqual(res["status"], "REVIEW_REQUIRED")
        self.assertEqual(Decimal(res["net_short_term"]), Decimal("2000.00"))
        self.assertEqual(Decimal(res["net_long_term"]), Decimal("-800.00"))
        self.assertEqual(Decimal(res["schedule_d_for_1040_line_7"]), Decimal("1200.00"))

    def test_3000_capital_loss_limit_and_carryover(self):
        txs = [{"holding_period": "long", "proceeds": "2000.00", "cost_basis": "10000.00"}]
        res = build_schedule_d_workpaper(txs, tax_year=2025, filing_status="single")
        self.assertEqual(res["status"], "CALCULATED")
        self.assertEqual(Decimal(res["schedule_d_for_1040_line_7"]), Decimal("-3000"))
        self.assertEqual(Decimal(res["capital_loss_carryover_reference"]), Decimal("5000.00"))

    def test_mfs_1500_limit_and_validation_errors(self):
        txs = [{"holding_period": "short", "proceeds": "0", "cost_basis": "5000.00"}]
        res = build_schedule_d_workpaper(txs, tax_year=2025, filing_status="married_filing_separately")
        self.assertEqual(Decimal(res["schedule_d_for_1040_line_7"]), Decimal("-1500"))
        self.assertEqual(Decimal(res["capital_loss_carryover_reference"]), Decimal("3500.00"))

        with self.assertRaises(InputValidationError):
            build_schedule_d_workpaper(txs, tax_year=2024, filing_status="single")
        with self.assertRaises(InputValidationError):
            build_schedule_d_workpaper(txs, tax_year=2025, filing_status="BANANA")


if __name__ == "__main__":
    unittest.main()
