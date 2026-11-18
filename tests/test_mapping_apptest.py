import unittest
from pathlib import Path
from decimal import localcontext
from streamlit.testing.v1 import AppTest
from modules.csv_mapper import map_bank_csv_to_ledger
from modules.reviewer_notes import draft_reviewer_notes
from modules.w2_tieout import SAMPLE, build_w2_tieout


class IntegratedWorkpapers(unittest.TestCase):
    def test_w2_question_uses_producer_box_label(self):
        workpaper = build_w2_tieout(SAMPLE, "W2-A\nW2-B", "60000.00", "5500.00")
        question = draft_reviewer_notes(workpaper)["notes"][0]["draft_question"]
        for value in ("federal withholding", "$5,700.00", "$5,500.00", "$200.00"):
            self.assertIn(value, question)

    def test_signed_amount_retains_digits(self):
        with localcontext() as ctx:
            ctx.prec = 2
            df = map_bank_csv_to_ledger(b"Date,Amount\n2025-01-01,-123456.78\n", type_col=None)
        self.assertEqual(df.iloc[0]["Amount"], "123456.78")

    def test_mapping_and_download_invalidation(self):
        at = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run()
        csv = b"Date,Amount\n2025-01-01,300\n2025-01-02,-50\n"
        at.file_uploader(key="ledger_upload").set_value(("synthetic.csv", csv, "text/csv")).run()
        at.checkbox(key="map_csv").check().run()
        at.button(key="run_reconciliation").click().run()
        self.assertFalse(at.exception)
        self.assertEqual(at.session_state["recon_result"].status, "PASS")
        self.assertEqual(len(at.get("download_button")), 1)
        at.text_input(key="map_date").set_value("Absent").run()
        self.assertFalse(at.get("download_button"))
        self.assertNotIn("recon_result", at.session_state)
        self.assertTrue(at.error)
        at.text_input(key="map_date").set_value("Date").run()
        at.button(key="run_reconciliation").click().run()
        at.text_input(key="closing").set_value("1251.00").run()
        self.assertNotIn("recon_result", at.session_state)
        self.assertFalse(at.get("download_button"))
        at.button(key="run_reconciliation").click().run()
        self.assertEqual(at.session_state["recon_result"].status, "FAIL")
        self.assertFalse(at.get("download_button"))
        self.assertFalse(at.exception)
