"""Unit and adversarial tests for modules/payroll_941_tieout_2025.py."""
import unittest

from core.reconciliation import InputValidationError
from modules.payroll_941_tieout_2025 import build_payroll_941_tieout


class Payroll941Tieout2025Tests(unittest.TestCase):
    def _quarters(self):
        return [
            {"quarter": "Q1", "wages_line_2": "25000.00", "fed_withholding_line_3": "3000.00", "ss_wages_line_5a": "25000.00", "medicare_wages_line_5c": "25000.00"},
            {"quarter": "Q2", "wages_line_2": "25000.00", "fed_withholding_line_3": "3000.00", "ss_wages_line_5a": "25000.00", "medicare_wages_line_5c": "25000.00"},
            {"quarter": "Q3", "wages_line_2": "25000.00", "fed_withholding_line_3": "3000.00", "ss_wages_line_5a": "25000.00", "medicare_wages_line_5c": "25000.00"},
            {"quarter": "Q4", "wages_line_2": "25000.00", "fed_withholding_line_3": "3000.00", "ss_wages_line_5a": "25000.00", "medicare_wages_line_5c": "25000.00"},
        ]

    def test_exact_match_q1_to_q4_against_w3(self):
        w3 = {"box_1_wages": "100000.00", "box_2_withholding": "12000.00", "box_3_ss_wages": "100000.00", "box_5_medicare_wages": "100000.00"}
        res = build_payroll_941_tieout(self._quarters(), w3)
        self.assertEqual(res["status"], "MATCH")

    def test_withholding_mismatch_flagged(self):
        w3 = {"box_1_wages": "100000.00", "box_2_withholding": "11500.00", "box_3_ss_wages": "100000.00", "box_5_medicare_wages": "100000.00"}
        res = build_payroll_941_tieout(self._quarters(), w3)
        self.assertEqual(res["status"], "REVIEW_REQUIRED")
        self.assertEqual(res["checks"][1]["difference"], "500.00")

    def test_rejects_missing_or_duplicate_quarters(self):
        w3 = {"box_1_wages": "0", "box_2_withholding": "0", "box_3_ss_wages": "0", "box_5_medicare_wages": "0"}
        with self.assertRaises(InputValidationError):
            build_payroll_941_tieout(self._quarters()[:3], w3)
        duped = self._quarters()
        duped[3]["quarter"] = "Q1"
        with self.assertRaises(InputValidationError):
            build_payroll_941_tieout(duped, w3)


if __name__ == "__main__":
    unittest.main()
