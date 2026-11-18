import unittest
from io import BytesIO

from openpyxl import load_workbook
from test_phase1_6_exhaustive import ROOT, _AppHarness, _FakeUploadedFile


class SampleLedgerTests(unittest.TestCase):
    def test_sample_exports_and_parameter_edit_clears_download(self):
        h = _AppHarness()
        h.run(use_sample_ledger=True)
        self.assertEqual(h.session_state["recon_result"].status, "PASS")
        workbook = load_workbook(BytesIO(h.downloads[0]["data"]))
        self.assertIn("1250.00", [str(cell.value) for sheet in workbook for row in sheet for cell in row])
        h.run(closing="1251.00")
        self.assertNotIn("recon_result", h.session_state)
        self.assertFalse(h.downloads)
        h.run(clicked=["run_reconciliation"])
        self.assertEqual(h.session_state["recon_result"].status, "FAIL")

    def test_upload_supersedes_sample_even_for_identical_bytes(self):
        h = _AppHarness()
        h.run(use_sample_ledger=True)
        sample = (ROOT / "sample_data/sample_ledger.csv").read_bytes()
        h.run(ledger_upload=_FakeUploadedFile(sample, "mine.csv"))
        self.assertNotIn("recon_result", h.session_state)
        self.assertFalse(h.downloads)
