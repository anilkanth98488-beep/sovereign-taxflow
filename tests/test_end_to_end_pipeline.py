import csv
import json
import unittest
from hashlib import sha256
from io import BytesIO, StringIO
from pathlib import Path
from zipfile import ZipFile

import pdfplumber
from docx import Document
from fpdf import FPDF
from openpyxl import Workbook, load_workbook
from streamlit.testing.v1 import AppTest

from modules.packet_export import export_packet
from modules.packet_intake import csv_bytes, read_table
from modules.workpaper_packet import run_packet

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "sample_data/packet"


def encode(rows, fmt):
    if fmt == "csv":
        return b"\xef\xbb\xbf" + csv_bytes(rows)
    if fmt == "xlsx":
        book = Workbook()
        for row in rows:
            book.active.append(row)
        out = BytesIO()
        book.save(out)
        return out.getvalue()
    pdf = FPDF(unit="pt", format=(3500, 1100))
    pdf.add_page()
    pdf.set_font("Courier", size=7)
    for row in rows:
        pdf.cell(0,10,"|".join(row),new_x="LMARGIN",new_y="NEXT")
    return bytes(pdf.output())


class PacketTests(unittest.TestCase):
    def test_three_formats_and_deliverables(self):
        for fmt in ("csv","xlsx","pdf"):
            with self.subTest(fmt=fmt):
                sources = {}
                for path in sorted(SAMPLES.glob("*.csv")):
                    rows = list(csv.reader(StringIO(path.read_text())))
                    sources[path.stem] = (path.stem+"."+fmt,encode(rows,fmt),None)
                m = run_packet(sources,"1000","1250")
                self.assertEqual(m["sources"]["ledger"]["status"],"PASS",m["findings"])
                self.assertEqual(m["results"]["1040"]["summary"]["agi_line_11"],"60000")
                self.assertEqual(m["sources"]["business"]["status"],"REVIEW_REQUIRED")
                self.assertEqual(m["results"]["payroll"]["checks"][1]["difference"],"500")
                self.assertTrue(m["reviewer_notes"]["draft_only"])
                self.assertFalse(m["reviewer_notes"]["approval_granted"])
                with ZipFile(BytesIO(export_packet(m))) as z:
                    saved = json.loads(z.read("audit.json"))
                    self.assertEqual(saved,m)
                    wb = load_workbook(BytesIO(z.read("workpapers.xlsx")))
                    self.assertIn("1040_Summary",wb.sheetnames)
                    with pdfplumber.open(BytesIO(z.read("summary.pdf"))) as doc:
                        pdf = "\n".join(p.extract_text() for p in doc.pages)
                    memo = "\n".join(p.text for p in Document(BytesIO(z.read("review-memo.docx"))).paragraphs)
                    audit = "\n".join(str(r[0]) for r in wb["Packet audit"].values)
                    for text in (pdf,memo,audit):
                        for token in (m["version"],"Sign-off","REVIEW_REQUIRED","500",
                                      *(sha256(src[1]).hexdigest() for src in sources.values())):
                            self.assertIn(token,text)
                    self.assertFalse(any(c.data_type=="f" for sh in wb for row in sh for c in row))

    def test_bad_source_isolated_and_controls_preserved(self):
        m=run_packet({"ledger":("ledger.csv",b"Date, Net ,Net\n2025-01-01,1,2",None),
                      "trial_balance":("tb.csv",(ROOT/"sample_data/sample_trial_balance.csv").read_bytes(),None)},"0","0")
        self.assertEqual(m["sources"]["ledger"]["status"],"INPUT ERROR")
        self.assertEqual(m["sources"]["trial_balance"]["status"],"OUT OF BALANCE")
        self.assertEqual(m["results"]["trial_balance"]["trial_balance_difference"],"-750.00")

    def test_excel_sheet_formula_and_unstructured_pdf(self):
        w=Workbook();w.active.append(["Date","Net"]);w.active.append(["2025-01-01","=1+1"]);w.create_sheet("Other")
        b=BytesIO();w.save(b)
        for sheet in (None,"Sheet"):
            with self.assertRaises(ValueError):
                read_table("ledger.xlsx",b.getvalue(),sheet)
        pdf=FPDF();pdf.add_page();pdf.set_font("Helvetica",size=12);pdf.cell(0,10,"unmapped text")
        with self.assertRaises(ValueError):
            read_table("ledger.pdf",bytes(pdf.output()))

    def test_ui_stale_packet(self):
        at=AppTest.from_file(str(ROOT/"app.py")).run()
        at.checkbox(key="packet_enable").check().run()
        at.checkbox(key="packet_sample").check().run()
        at.button(key="packet_build").click().run()
        self.assertFalse(at.exception)
        self.assertIn("packet_bytes",at.session_state)
        self.assertTrue(any("draft packet" in el.label.lower() for el in at.get("download_button")))
        at.text_input(key="packet_closing").set_value("1251").run()
        self.assertNotIn("packet_bytes",at.session_state)
        self.assertFalse(any("draft packet" in el.label.lower() for el in at.get("download_button")))

    def test_excel_decimal_and_reproducible_render(self):
        book = Workbook()
        book.active.append(["Date","Net"])
        book.active.append(["2025-01-01",125.55])
        raw = BytesIO()
        book.save(raw)
        row = read_table("ledger.xlsx",raw.getvalue())[0]
        self.assertEqual(row["Net"],"125.55")
        m = run_packet({"ledger":("ledger.xlsx",raw.getvalue(),None)},"0","125.55")
        self.assertEqual(m["sources"]["ledger"]["status"],"PASS")
        self.assertEqual(export_packet(m),export_packet(m))

    def test_partial_payroll_evidence_and_high_precision(self):
        rows = list(csv.reader(StringIO((SAMPLES/"payroll.csv").read_text())))
        annual = next(row for row in rows if row[0] == "annual_w3_totals")
        fields = json.loads(annual[1])
        del fields["box_2_withholding"]
        annual[1] = json.dumps(fields)
        large="123456789012345678901234567890.12"
        m = run_packet({"payroll":("payroll.csv",csv_bytes(rows),None),
                        "ledger":("ledger.csv",csv_bytes([["Date","Net"],["2025-01-01",large]]),None)},"0",large)
        self.assertEqual(m["sources"]["payroll"]["status"],"INPUT ERROR")
        self.assertEqual(m["results"]["ledger"]["calculated_closing_balance"],large)
        self.assertNotIn("payroll",m["results"])
