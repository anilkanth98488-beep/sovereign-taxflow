"""Phase 1.6 deep-testing suite: cross-module workflows, large CSVs, BOM/encoding, and app state checks."""
import ast
from datetime import date, datetime
from decimal import Decimal
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import time
import unittest

import pandas as pd
from openpyxl import load_workbook

from core.reconciliation import (
    InputValidationError,
    Sovereign167VReconciler,
    currency_stripper,
)
from modules.book_to_tax import build_book_to_tax_workpaper, m3_threshold_flags
from modules.depreciation_schedule import (
    bonus_rate,
    build_depreciation_schedule,
    partition_assets_by_tax_year,
    section_179_reference,
)
from modules.document_organizer import classify_filename, missing_item_alerts
from modules.financial_statements import build_financial_statements

ROOT = Path(__file__).resolve().parents[1]


class Phase16DeepTests(unittest.TestCase):
    def test_parenthetical_with_currency_and_sign_rejected(self):
        for bad in ("($-100)", "($+100)", "($ -1,234.56)", "(€-50.00)", "(₹+10)"):
            with self.subTest(bad=bad):
                with self.assertRaises(InputValidationError):
                    currency_stripper(bad)

    def test_large_ledger_reconciliation_and_xlsx_export(self):
        rows = []
        for i in range(2500):
            rows.append({"Date": "2026-01-15", "Amount": "100.25", "Type": "CREDIT"})
            rows.append({"Date": "2026-01-16", "Amount": "50.10", "Type": "DEBIT"})
        df = pd.DataFrame(rows)
        # Net movement per pair = 50.15; 2500 pairs = 125375.00; opening 1000.00 -> 126375.00
        start = time.perf_counter()
        engine = Sovereign167VReconciler(df, "1000.00", "126375.00", "0.00")
        result = engine.execute_reconciliation()
        elapsed = time.perf_counter() - start
        self.assertEqual(result.status, "PASS")
        self.assertEqual(result.row_count, 5000)
        self.assertEqual(result.calculated_closing_balance, "126375.00")
        self.assertLess(elapsed, 5.0)
        wb = load_workbook(engine.export_xlsx(result), data_only=True)
        self.assertIn("Reconciliation", wb.sheetnames)

    def test_utf8_bom_csv_bytes_and_extra_columns(self):
        bom_csv = "\ufeffDate,Amount,Type,Memo\n2026-01-01,200.00,CREDIT,=SUM(A1:A2)\n".encode("utf-8")
        df = pd.read_csv(BytesIO(bom_csv), dtype=str, keep_default_na=False, encoding="utf-8-sig")
        engine = Sovereign167VReconciler(df, "100.00", "300.00", "0.00")
        result = engine.execute_reconciliation()
        self.assertEqual(result.status, "PASS")

    def test_depreciation_outputs_are_json_serializable(self):
        assets = [
            {"asset": "Server", "cost": "5000.00", "acquisition_date": "2025-02-01", "placed_in_service_date": "2025-06-01"},
            {"asset": None, "cost": "1000.00", "acquisition_date": "2025-02-01", "placed_in_service_date": "2025-07-01"},
        ]
        result = build_depreciation_schedule(assets, 2025)
        encoded = json.dumps(result)
        decoded = json.loads(encoded)
        self.assertEqual(decoded["section_179_reference"]["maximum"], "2500000")
        self.assertEqual(decoded["assets"][1]["asset"], "Asset 2")

    def test_depreciation_rejects_datetime_and_compact_iso_dates(self):
        with self.assertRaises(InputValidationError):
            bonus_rate(datetime(2025, 2, 1, 12, 0), date(2025, 6, 1))
        with self.assertRaises(InputValidationError):
            bonus_rate("20250201", "2025-06-01")
        selected, other, invalid = partition_assets_by_tax_year(
            [{"asset": "BadCompact", "placed_in_service_date": "20250601"}], 2025
        )
        self.assertEqual(selected, [])
        self.assertEqual(other, [])
        self.assertEqual(len(invalid), 1)

    def test_book_to_tax_validates_entity_type_and_none_description(self):
        with self.assertRaises(InputValidationError):
            build_book_to_tax_workpaper([], 2025, entity_type="INVALID_FORM")
        res = build_book_to_tax_workpaper(
            [{"code": "MEALS_274N", "amount": "100", "description": None}],
            2025,
            entity_type="1120-S",
        )
        self.assertEqual(res["items"][0]["description"], "")
        json.dumps(res)

    def test_m3_boundary_thresholds(self):
        self.assertFalse(m3_threshold_flags("1120", "9999999.99")["schedule_m3_required_preliminary"])
        self.assertTrue(m3_threshold_flags("1120", "10000000.00")["schedule_m3_required_preliminary"])
        self.assertFalse(m3_threshold_flags("1120", "49999999.99")["schedule_m3_full_parts_ii_iii_threshold"])
        self.assertTrue(m3_threshold_flags("1120", "50000000.00")["schedule_m3_full_parts_ii_iii_threshold"])
        self.assertFalse(m3_threshold_flags("1065", "0", "34999999.99", False)["schedule_m3_required_preliminary"])
        self.assertTrue(m3_threshold_flags("1065", "0", "35000000.00", False)["schedule_m3_required_preliminary"])
        self.assertTrue(m3_threshold_flags("1065", "0", "0", True)["schedule_m3_required_preliminary"])

    def test_large_trial_balance_and_category_aggregation(self):
        rows = []
        for i in range(1000):
            rows.append({"Account": f"Asset_{i}", "Debit": "100.00", "Credit": "0.00", "Statement": "BALANCE SHEET", "Category": "Current Assets"})
            rows.append({"Account": f"Rev_{i}", "Debit": "0.00", "Credit": "100.00", "Statement": "P&L", "Category": "Revenue"})
        res = build_financial_statements(pd.DataFrame(rows))
        self.assertEqual(res["trial_balance_status"], "BALANCED")
        self.assertEqual(res["balance_sheet"]["Current Assets"], "100000.00")
        self.assertEqual(res["profit_and_loss"]["Revenue"], "-100000.00")
        json.dumps(res)

    def test_document_organizer_blank_received_categories(self):
        alerts = missing_item_alerts("1040", ["", "   "])
        self.assertEqual(alerts, ["deductions", "identity", "income"])

    def test_cross_module_synthetic_partnership_workflow(self):
        # 1. Document routing for a 1065 client packet
        routed_tb = classify_filename("Acme_1065_Trial-Balance.csv")
        routed_k1 = classify_filename("Acme_1065_K-1.pdf")
        self.assertEqual(routed_tb["suggested_form"], "1065")
        self.assertEqual(routed_tb["category"], "partnership")
        self.assertEqual(routed_k1["suggested_form"], "1065")
        self.assertEqual(missing_item_alerts("1065", [routed_tb["category"]]), [])

        # 2. Financial statements check
        tb_df = pd.read_csv(ROOT / "sample_data" / "sample_trial_balance.csv", dtype=str, keep_default_na=False, encoding="utf-8-sig")
        fs = build_financial_statements(tb_df)
        self.assertEqual(fs["trial_balance_status"], "OUT OF BALANCE")

        # 3. Book-to-tax + M-3 screen for 1065
        bt_items = pd.read_csv(ROOT / "sample_data" / "sample_book_to_tax.csv", dtype=str, keep_default_na=False, encoding="utf-8-sig").to_dict("records")
        bt = build_book_to_tax_workpaper(bt_items, 2026, entity_type="1065")
        m3 = m3_threshold_flags("1065", "1000000.00", "2000000.00", False)
        self.assertFalse(m3["schedule_m3_required_preliminary"])
        self.assertEqual(Decimal(bt["net_quantified_proposed_adjustment"]), Decimal("80.00"))

        # 4. Depreciation partition + 179 reference
        assets = pd.read_csv(ROOT / "sample_data" / "sample_assets.csv", dtype=str, keep_default_na=False, encoding="utf-8-sig").to_dict("records")
        selected, other, invalid = partition_assets_by_tax_year(assets, 2026)
        self.assertEqual(len(selected), 1)
        self.assertEqual(len(other), 1)
        self.assertEqual(invalid, [])
        dep = build_depreciation_schedule(selected, 2026)
        sec179 = section_179_reference(2026, dep["total_cost"], dep["total_cost"])
        self.assertTrue(sec179["within_reference_limit"])
        for payload in (fs, bt, m3, dep, sec179):
            json.dumps(payload)

    def test_app_py_uses_utf8_sig_and_json_fingerprints(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        ast.parse(source)
        self.assertIn('encoding="utf-8-sig"', source)
        self.assertEqual(source.count("read_csv_upload(upload)"), 5)
        self.assertIn("json.dumps([ledger_key, opening, closing, tolerance]", source)
        self.assertIn("json.dumps([form, received]", source)
        self.assertIn('"recon_ledger", "recon_parameters"', source)

    def test_stale_session_state_invalidation_logic(self):
        session_state = {}

        def clear_if_changed(state_key, current_fingerprint, result_key, *extra_keys):
            previous = session_state.get(state_key)
            if previous != current_fingerprint:
                session_state.pop(result_key, None)
                for key in extra_keys:
                    session_state.pop(key, None)
                session_state[state_key] = current_fingerprint

        fp1 = sha256(json.dumps(["fileA", "1000", "1250", "0.01"]).encode()).hexdigest()
        clear_if_changed("recon_input_fingerprint", fp1, "recon_result", "recon_ledger", "recon_parameters")
        session_state["recon_result"] = "PASS"
        session_state["recon_ledger"] = "dfA"
        session_state["recon_parameters"] = ("1000", "1250", "0.01")

        # Parameter change invalidates result, ledger, and parameters
        fp2 = sha256(json.dumps(["fileA", "1000", "1251", "0.01"]).encode()).hexdigest()
        clear_if_changed("recon_input_fingerprint", fp2, "recon_result", "recon_ledger", "recon_parameters")
        self.assertNotIn("recon_result", session_state)
        self.assertNotIn("recon_ledger", session_state)
        self.assertNotIn("recon_parameters", session_state)


if __name__ == "__main__":
    unittest.main()
