"""End-to-end integration tests for modules/form_1040_assembler_2025.py."""
from decimal import Decimal
import unittest

from openpyxl import load_workbook

from core.reconciliation import InputValidationError
from modules.form_1040_assembler_2025 import (
    assemble_2025_form_1040_workpaper,
    export_1040_workpaper_xlsx,
)


class Form1040Assembler2025Tests(unittest.TestCase):
    def test_end_to_end_w2_only_return_and_xlsx_export(self):
        res = assemble_2025_form_1040_workpaper(
            taxpayer_label="=EVIL_NAME",
            filing_status="single",
            w2_wages="65000.00",
            w2_withholding="6500.00",
        )
        self.assertEqual(res["status"], "DRAFT_READY")
        self.assertEqual(Decimal(res["summary"]["agi_line_11"]), Decimal("65000.00"))
        self.assertEqual(res["summary"]["deduction_method"], "STANDARD_DEDUCTION")
        self.assertEqual(Decimal(res["summary"]["taxable_income_line_15"]), Decimal("50000.00"))
        self.assertEqual(Decimal(res["summary"]["total_tax_line_24"]), Decimal("5914.00"))
        self.assertEqual(Decimal(res["summary"]["overpayment_refund_line_34"]), Decimal("586.00"))

        wb = load_workbook(export_1040_workpaper_xlsx(res), data_only=True)
        self.assertEqual(wb.sheetnames, ["1040_Summary", "Diagnostics"])
        self.assertEqual(wb["1040_Summary"]["B2"].value, "'=EVIL_NAME")

    def test_multi_schedule_return_triggers_diagnostics(self):
        res = assemble_2025_form_1040_workpaper(
            filing_status="single",
            w2_wages="50000.00",
            w2_withholding="5000.00",
            form_1099_docs=[{"form_type": "1099-DIV", "reference": "DIV_1", "ordinary_dividends": "1000.00", "qualified_dividends": "500.00"}],
            draft_1040_for_1099={"3b": "1000.00", "3a": "500.00", "25b": "0.00"},
            schedule_c_gross="20000.00",
            schedule_c_expenses="5000.00",
            schedule_d_transactions=[{"holding_period": "long", "proceeds": "4000.00", "cost_basis": "1000.00"}],
            rentals=[{"property": "Oak", "rents_received": "10000.00", "expenses": "12000.00"}],
        )
        self.assertEqual(res["status"], "REVIEW_REQUIRED")
        modules_flagged = {d["module"] for d in res["diagnostics"]}
        self.assertIn("schedule_e", modules_flagged)
        self.assertIn("tax_and_credits", modules_flagged)

    def test_rejects_invalid_assembler_export_input(self):
        with self.assertRaises(InputValidationError):
            export_1040_workpaper_xlsx({"rule_id": "other"})


if __name__ == "__main__":
    unittest.main()
