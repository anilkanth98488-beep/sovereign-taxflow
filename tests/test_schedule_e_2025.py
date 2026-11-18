"""Unit and adversarial tests for modules/schedule_e_2025.py."""
from decimal import Decimal
import unittest

from core.reconciliation import InputValidationError
from modules.schedule_e_2025 import build_schedule_e_workpaper


class ScheduleE2025Tests(unittest.TestCase):
    def test_rental_profit_and_k1_aggregation(self):
        rentals = [{"property": "123 Main", "rents_received": "24000.00", "expenses": "6000.00", "depreciation": "4000.00"}]
        k1s = [
            {"entity_form": "1065", "entity_name": "Alpha LP", "ordinary_income_loss": "10000.00", "guaranteed_payments": "2000.00"},
            {"entity_form": "1120-S", "entity_name": "Beta Inc", "ordinary_income_loss": "5000.00"},
        ]
        res = build_schedule_e_workpaper(tax_year=2025, rentals=rentals, k1_items=k1s)
        self.assertEqual(res["status"], "CALCULATED")
        self.assertEqual(Decimal(res["rental_net_income_loss"]), Decimal("14000.00"))
        self.assertEqual(Decimal(res["k1_net_income_loss"]), Decimal("17000.00"))
        self.assertEqual(Decimal(res["schedule_e_total_for_schedule_1_line_5"]), Decimal("31000.00"))

    def test_rental_loss_and_k1_loss_trigger_review_required(self):
        rentals = [{"property": "Oak St", "rents_received": "10000.00", "expenses": "12000.00"}]
        k1s = [{"entity_form": "1120-S", "entity_name": "Gamma S", "ordinary_income_loss": "-3000.00"}]
        res = build_schedule_e_workpaper(tax_year=2025, rentals=rentals, k1_items=k1s)
        self.assertEqual(res["status"], "REVIEW_REQUIRED")
        self.assertEqual(len(res["review_reasons"]), 2)

    def test_1120s_guaranteed_payments_and_bad_form_rejected(self):
        with self.assertRaises(InputValidationError):
            build_schedule_e_workpaper(
                tax_year=2025,
                k1_items=[{"entity_form": "1120-S", "entity_name": "BadS", "ordinary_income_loss": "100", "guaranteed_payments": "50"}],
            )
        with self.assertRaises(InputValidationError):
            build_schedule_e_workpaper(tax_year=2025, k1_items=[{"entity_form": "1040", "ordinary_income_loss": "100"}])


if __name__ == "__main__":
    unittest.main()
