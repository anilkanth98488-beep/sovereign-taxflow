"""Unit, adversarial, and randomized tests for modules/form_1099_tieout_2025.py."""
from decimal import Decimal
import random
import unittest

from core.reconciliation import InputValidationError
from modules.form_1099_tieout_2025 import build_1099_tieout


class Form1099TieoutTests(unittest.TestCase):
    def _sample_docs(self):
        return [
            {"form_type": "1099-INT", "reference": "INT_BankA", "taxable_interest": "1200.50", "federal_withholding": "100.00"},
            {"form_type": "1099-DIV", "reference": "DIV_BrokerB", "ordinary_dividends": "800.00", "qualified_dividends": "600.00", "federal_withholding": "50.00"},
            {"form_type": "1099-R", "reference": "R_IRA", "gross_distribution": "5000.00", "taxable_distribution": "5000.00", "federal_withholding": "500.00"},
        ]

    def _sample_draft(self):
        return {
            "2b": "1200.50",
            "3b": "800.00",
            "3a": "600.00",
            "5a": "5000.00",
            "5b": "5000.00",
            "25b": "650.00",
        }

    def test_exact_match_without_requiring_unused_1099_nec_draft_line(self):
        res = build_1099_tieout(self._sample_docs(), self._sample_draft(), ["INT_BankA", "DIV_BrokerB", "R_IRA"])
        self.assertEqual(res["status"], "MATCH")
        self.assertEqual(res["missing_documents"], [])
        self.assertEqual(res["unexpected_documents"], [])

    def test_phantom_draft_income_without_source_1099_is_flagged(self):
        draft = {"2b": "1200.50", "3b": "500.00", "25b": "100.00"}
        docs = [{"form_type": "1099-INT", "reference": "INT_BankA", "taxable_interest": "1200.50", "federal_withholding": "100.00"}]
        res = build_1099_tieout(docs, draft)
        self.assertEqual(res["status"], "REVIEW_REQUIRED")
        div_check = [c for c in res["checks"] if c["line"] == "3b"][0]
        self.assertEqual(div_check["source_minus_draft_usd"], "-500.00")

    def test_withholding_discrepancy_and_missing_document(self):
        draft = self._sample_draft()
        draft["25b"] = "500.00"
        res = build_1099_tieout(self._sample_docs(), draft, ["INT_BankA", "DIV_BrokerB", "R_IRA", "NEC_ClientX"])
        self.assertEqual(res["status"], "REVIEW_REQUIRED")
        self.assertEqual(res["missing_documents"], ["NEC_ClientX"])
        wh_check = [c for c in res["checks"] if c["line"] == "25b"][0]
        self.assertEqual(wh_check["source_total_usd"], "650.00")
        self.assertEqual(wh_check["draft_usd"], "500.00")
        self.assertIsNone(wh_check["source_minus_draft_usd"])

    def test_1099_nec_always_requires_schedule_c_review(self):
        docs = self._sample_docs() + [{"form_type": "1099-NEC", "reference": "NEC_1", "nonemployee_comp": "2500.00"}]
        draft = self._sample_draft()
        draft["Schedule 1 / Sch C"] = "2500.00"
        res = build_1099_tieout(docs, draft)
        self.assertEqual(res["status"], "REVIEW_REQUIRED")
        nec = [c for c in res["checks"] if c["form"] == "1099-NEC"][0]
        self.assertEqual(nec["status"], "REVIEW_REQUIRED")
        self.assertEqual(nec["source_minus_draft_usd"], "0.00")

    def test_1099_div_validates_qualified_even_when_ordinary_blank(self):
        docs = [{"form_type": "1099-DIV", "reference": "D1", "ordinary_dividends": "", "qualified_dividends": "bad"}]
        with self.assertRaises(InputValidationError):
            build_1099_tieout(docs, {})

    def test_1099_r_rejects_non_boolean_box2b_and_flags_true(self):
        bad_doc = [{"form_type": "1099-R", "reference": "R1", "gross_distribution": "100", "taxable_distribution": "100", "taxable_amount_not_determined": "False"}]
        with self.assertRaises(InputValidationError):
            build_1099_tieout(bad_doc, {"5a": "100", "5b": "100", "25b": "0"})

        flag_doc = [{"form_type": "1099-R", "reference": "R1", "gross_distribution": "100", "taxable_distribution": "100", "taxable_amount_not_determined": True}]
        res = build_1099_tieout(flag_doc, {"5a": "100", "5b": "100", "25b": "0"})
        self.assertEqual(res["status"], "REVIEW_REQUIRED")

    def test_expected_documents_rejects_blank_and_duplicates(self):
        with self.assertRaises(InputValidationError):
            build_1099_tieout(self._sample_docs(), self._sample_draft(), ["INT_BankA", ""])
        with self.assertRaises(InputValidationError):
            build_1099_tieout(self._sample_docs(), self._sample_draft(), ["INT_BankA", "INT_BankA"])

    def test_32_digit_precision_and_randomized_tieouts(self):
        big = "123456789012345678901234567890.12"
        docs = [{"form_type": "1099-INT", "reference": "INT_Big", "taxable_interest": big}]
        res = build_1099_tieout(docs, {"2b": big, "25b": "0.00"})
        self.assertEqual(res["status"], "MATCH")

        rng = random.Random(1099)
        for idx in range(100):
            a = Decimal(f"{rng.randint(0, 10000)}.{rng.randint(0, 99):02d}")
            b = Decimal(f"{rng.randint(0, 10000)}.{rng.randint(0, 99):02d}")
            wh = Decimal(f"{rng.randint(0, 2000)}.{rng.randint(0, 99):02d}")
            d = [
                {"form_type": "1099-INT", "reference": f"I1_{idx}", "taxable_interest": str(a), "federal_withholding": str(wh)},
                {"form_type": "1099-INT", "reference": f"I2_{idx}", "taxable_interest": str(b)},
            ]
            r = build_1099_tieout(d, {"2b": str(a + b), "25b": str(wh)})
            self.assertEqual(r["status"], "MATCH")


if __name__ == "__main__":
    unittest.main()
