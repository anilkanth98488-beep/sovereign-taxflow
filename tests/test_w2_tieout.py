import random
import unittest
from decimal import localcontext

from core.reconciliation import InputValidationError
from modules.w2_tieout import SAMPLE, build_w2_tieout
from test_phase1_6_exhaustive import _AppHarness


class W2Tests(unittest.TestCase):
    def test_sample_and_missing_inventory(self):
        w = build_w2_tieout(SAMPLE, "W2-A\nW2-B", "60000", "5500")
        self.assertEqual([c["status"] for c in w["checks"]], ["MATCH", "REVIEW_REQUIRED"])
        self.assertEqual(w["checks"][1]["source_minus_draft_usd"], "200.00")
        for inventory in ("", "W2-A", "W2-A\nW2-B\nW2-C"):
            w = build_w2_tieout(SAMPLE, inventory, "60000", "5700")
            self.assertTrue(all(c["source_total_usd"] is None for c in w["checks"]))

    def test_zero_blank_duplicate_and_invalid_values(self):
        first = "year,reference,box1,box2\n2025,A,0,"
        c = build_w2_tieout(first, "A", "0", "")["checks"]
        self.assertEqual(c[0]["status"], "MATCH")
        self.assertEqual(c[1]["blank_on"], ["A"])
        for value in ("-1", "1e3", "1.234", "NaN", "1"*49):
            with self.assertRaises(InputValidationError):
                build_w2_tieout(first + value, "A", "0", "0")
        for data in (first.replace("2025", "2026"), first + "\n2025,a,0,0"):
            with self.assertRaises(InputValidationError):
                build_w2_tieout(data, "A", "0", "0")

    def test_randomized_exact_cents(self):
        rng = random.Random(42)
        with localcontext() as ctx:
            ctx.prec = 6
            for _ in range(100):
                cents = rng.randrange(10**45)
                val = f"{cents//100}.{cents%100:02d}"
                source = "year,reference,box1,box2\n2025,A," + val + ",0.01"
                c = build_w2_tieout(source, "A", val, "0.02")["checks"]
                self.assertEqual(c[0]["source_total_usd"], val)
                self.assertEqual(c[1]["source_minus_draft_usd"], "-0.01")

    def test_ui_clears_download_when_draft_changes(self):
        h = _AppHarness()
        h.run(clicked=["run_w2"])
        self.assertTrue(h.downloads)
        h.run(w2_withholding="5700")
        self.assertFalse(h.downloads)
        self.assertNotIn("w2_result", h.session_state)
