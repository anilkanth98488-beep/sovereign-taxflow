"""Unit and adversarial tests for modules/fiduciary_1041_2025.py."""
from decimal import Decimal
import unittest

from core.reconciliation import InputValidationError
from modules.fiduciary_1041_2025 import build_1041_workpaper


class Fiduciary10412025Tests(unittest.TestCase):
    def test_complex_trust_dni_distribution_and_niit_flag(self):
        res = build_1041_workpaper(
            entity_type="complex_trust",
            tax_year=2025,
            interest_and_dividends="20000.00",
            capital_gains_net="10000.00",
            fiduciary_and_professional_fees="2000.00",
            distributions_to_beneficiaries="15000.00",
            capital_gains_allocated_to_corpus=True,
        )
        # Total = 30k, adj = 28k, DNI = 18k -> dist ded = 15k, exemption = 100 -> taxable = 12,900
        self.assertEqual(res["status"], "REVIEW_REQUIRED")
        self.assertTrue(res["form_8960_niit_review_required"])
        self.assertEqual(Decimal(res["preliminary_dni_schedule_b"]), Decimal("18000.00"))
        self.assertEqual(Decimal(res["taxable_income_line_23"]), Decimal("12900.00"))

    def test_estate_below_threshold_calculated(self):
        res = build_1041_workpaper(
            entity_type="estate",
            tax_year=2025,
            interest_and_dividends="3750.00",
            fiduciary_and_professional_fees="0",
        )
        self.assertEqual(res["status"], "CALCULATED")
        self.assertEqual(Decimal(res["taxable_income_line_23"]), Decimal("3150.00"))
        self.assertEqual(Decimal(res["illustrative_bracket_tax"]), Decimal("315.00"))

    def test_validation_errors(self):
        with self.assertRaises(InputValidationError):
            build_1041_workpaper(entity_type="1040", tax_year=2025)
        with self.assertRaises(InputValidationError):
            build_1041_workpaper(entity_type="estate", tax_year=2024)


if __name__ == "__main__":
    unittest.main()
