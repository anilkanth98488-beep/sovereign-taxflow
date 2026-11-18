import unittest

from test_phase1_6_exhaustive import ROOT, _AppHarness, _FakeUploadedFile


class ReviewQueueTests(unittest.TestCase):
    def test_balance_change_cancels_approval_and_failed_check_blocks_signoff(self):
        h = _AppHarness()
        ledger = _FakeUploadedFile((ROOT / "sample_data/sample_ledger.csv").read_bytes(), "ledger.csv")
        h.run(clicked=["run_reconciliation"], ledger_upload=ledger,
              owner_ledger_upload="Preparer", reviewer_ledger_upload="Reviewer")
        h.run(clicked=["sign_ledger_upload"])
        self.assertIn("utc", h.session_state["approval_ledger_upload"])
        h.run(closing="1251")
        self.assertNotIn("approval_ledger_upload", h.session_state)
        h.run(clicked=["run_reconciliation", "sign_ledger_upload"])
        self.assertNotIn("approval_ledger_upload", h.session_state)

    def test_unresolved_adjustment_is_visible_and_blocks_signoff(self):
        h = _AppHarness()
        source = (ROOT / "sample_data/sample_book_to_tax.csv").read_bytes()
        h.run(clicked=["build_bt", "sign_book_tax_upload"], book_tax_upload=_FakeUploadedFile(source, "bt.csv"),
              owner_book_tax_upload="Preparer", reviewer_book_tax_upload="Reviewer")
        result = h.session_state["bt_result"]
        self.assertIn(("metric", "Awaiting review", result["unresolved_review_amount_total"]), h.events)
        self.assertIn(("metric", "Net quantified adjustment", result["net_quantified_proposed_adjustment"]), h.events)
        self.assertNotIn("approval_book_tax_upload", h.session_state)

    def test_new_pass_with_identical_inputs_requires_new_signoff(self):
        h = _AppHarness()
        source = (ROOT / "sample_data/sample_ledger.csv").read_bytes()
        h.run(clicked=["run_reconciliation"], ledger_upload=_FakeUploadedFile(source, "ledger.csv"),
              owner_ledger_upload="Preparer", reviewer_ledger_upload="Reviewer")
        h.run(clicked=["sign_ledger_upload"])
        h.run()
        self.assertIn("approval_ledger_upload", h.session_state)
        h.run(clicked=["run_reconciliation"])
        self.assertEqual(h.session_state["recon_result"].status, "PASS")
        self.assertNotIn("approval_ledger_upload", h.session_state)
        h.run(clicked=["sign_ledger_upload"])
        self.assertIn("utc", h.session_state["approval_ledger_upload"])
