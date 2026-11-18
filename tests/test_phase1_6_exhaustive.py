"""Exhaustive Phase 1.6 tests: mocked Streamlit E2E app.py execution, fuzzing, security AST scan, and config checks."""
import ast
from decimal import Decimal
from io import BytesIO
import json
from pathlib import Path
import random
import sys
import tomllib
import types
import unittest

import pandas as pd
from openpyxl import load_workbook

from core.reconciliation import (
    InputValidationError,
    Sovereign167VReconciler,
    currency_stripper,
    sanitize_spreadsheet_text,
)
from modules.document_organizer import classify_filename

ROOT = Path(__file__).resolve().parents[1]


class _FakeUploadedFile:
    def __init__(self, data: bytes, name: str = "upload.csv"):
        self._data = data
        self.name = name

    def getvalue(self) -> bytes:
        return self._data


class _FakeContext:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeSidebar:
    def __init__(self, log):
        self._log = log

    def info(self, msg):
        self._log.append(("sidebar.info", msg))


class _FakeColumn:
    def __init__(self, harness):
        self._h = harness

    def text_input(self, label, value="", key=None):
        return self._h._widget_value(key or label, value)


def _build_mock_streamlit(harness):
    st = types.ModuleType("streamlit")
    st.session_state = harness.session_state
    st.sidebar = _FakeSidebar(harness.events)
    st.set_page_config = lambda **kw: harness.events.append(("set_page_config", kw))
    st.title = lambda txt: harness.events.append(("title", txt))
    st.caption = lambda txt: harness.events.append(("caption", txt))
    st.warning = lambda txt: harness.events.append(("warning", str(txt)))
    st.error = lambda txt: harness.events.append(("error", str(txt)))
    st.info = lambda txt: harness.events.append(("info", str(txt)))
    st.metric = lambda label, val: harness.events.append(("metric", label, val))
    st.json = lambda obj: harness.events.append(("json", obj))
    st.write = lambda obj: harness.events.append(("write", obj))
    st.dataframe = lambda df, **kw: harness.events.append(("dataframe", len(df)))
    st.tabs = lambda labels: [_FakeContext() for _ in labels]
    st.columns = lambda n: [_FakeColumn(harness) for _ in range(n)]
    st.file_uploader = lambda label, type=None, key=None: harness._widget_value(key or label, None)
    st.text_input = lambda label, value="", key=None: harness._widget_value(key or label, value)
    st.text_area = lambda label, value="", key=None: harness._widget_value(key or label, value)
    st.selectbox = lambda label, options, key=None: harness._widget_value(key or label, options[0])
    st.checkbox = lambda label, value=False, key=None: harness._widget_value(key or label, value)
    st.button = lambda label, key=None: harness._button_clicked(key or label)
    st.download_button = lambda label, data, file_name, mime, on_click=None: harness.downloads.append(
        {"label": label, "data": data, "file_name": file_name, "mime": mime, "on_click": on_click}
    )
    return st


class _AppHarness:
    def __init__(self):
        self.session_state = {}
        self.widgets = {}
        self.clicked = set()
        self.events = []
        self.downloads = []

    def _widget_value(self, key, default):
        return self.widgets.get(key, default)

    def _button_clicked(self, key):
        return key in self.clicked

    def run(self, clicked=None, **widget_updates):
        self.widgets.update(widget_updates)
        self.clicked = set(clicked or [])
        self.events.clear()
        self.downloads.clear()
        mock_st = _build_mock_streamlit(self)
        prev = sys.modules.get("streamlit")
        sys.modules["streamlit"] = mock_st
        try:
            code = (ROOT / "app.py").read_text(encoding="utf-8")
            ns = {"__file__": str(ROOT / "app.py"), "__name__": "__main__"}
            exec(compile(code, str(ROOT / "app.py"), "exec"), ns)
        finally:
            if prev is None:
                sys.modules.pop("streamlit", None)
            else:
                sys.modules["streamlit"] = prev


class ExhaustivePhase16Tests(unittest.TestCase):
    def test_app_e2e_all_five_tabs_and_stale_invalidation(self):
        h = _AppHarness()
        ledger_bytes = (ROOT / "sample_data" / "sample_ledger.csv").read_bytes()
        tb_bytes = (ROOT / "sample_data" / "sample_trial_balance.csv").read_bytes()
        bt_bytes = (ROOT / "sample_data" / "sample_book_to_tax.csv").read_bytes()
        assets_bytes = (ROOT / "sample_data" / "sample_assets.csv").read_bytes()

        # Run 1: execute all 5 tabs with valid/sample inputs
        h.run(
            clicked=[
                "run_reconciliation",
                "build_fs",
                "build_bt",
                "m3_check",
                "build_depreciation",
                "check_179",
                "classify_docs",
                "missing_items",
            ],
            ledger_upload=_FakeUploadedFile(ledger_bytes, "sample_ledger.csv"),
            opening="1000.00",
            closing="1250.00",
            tolerance="0.01",
            tb_upload=_FakeUploadedFile(tb_bytes, "sample_trial_balance.csv"),
            book_tax_year=2026,
            book_tax_upload=_FakeUploadedFile(bt_bytes, "sample_book_to_tax.csv"),
            depreciation_year=2026,
            asset_upload=_FakeUploadedFile(assets_bytes, "sample_assets.csv"),
            **{
                "Paste document filenames, one per line": "Client_1040_W2.pdf\nGeneric_K1.pdf",
                "Received categories (comma separated)": "",
            },
        )
        self.assertEqual(h.session_state["recon_result"].status, "PASS")
        self.assertEqual(len(h.downloads), 1)
        wb = load_workbook(BytesIO(h.downloads[0]["data"]), data_only=True)
        self.assertIn("Reconciliation", wb.sheetnames)
        self.assertEqual(h.session_state["fs_result"]["trial_balance_status"], "OUT OF BALANCE")
        self.assertEqual(h.session_state["bt_result"]["unresolved_review_amount_total"], "250.00")
        self.assertEqual(h.session_state["dep_result"]["tax_year"], 2026)
        self.assertEqual(h.session_state["doc_results"][0]["suggested_form"], "1040")
        self.assertEqual(h.session_state["doc_results"][1]["suggested_form"], "REVIEW")
        self.assertEqual(h.session_state["missing_items_result"], ["deductions", "identity", "income"])

        # Run 2: change expected closing & book_tax_year -> stale results & download must vanish
        h.run(closing="1251.00", book_tax_year=2025)
        self.assertNotIn("recon_result", h.session_state)
        self.assertNotIn("recon_ledger", h.session_state)
        self.assertNotIn("recon_parameters", h.session_state)
        self.assertNotIn("bt_result", h.session_state)
        self.assertEqual(h.downloads, [])

        # Run 3: upload invalid asset date -> error displayed and dep_result withheld
        bad_assets = b"asset,cost,acquisition_date,placed_in_service_date\nLaptop,1000,2026-01-01,bad-date\n"
        h.run(clicked=["build_depreciation"], asset_upload=_FakeUploadedFile(bad_assets, "bad.csv"))
        self.assertNotIn("dep_result", h.session_state)
        self.assertTrue(any(ev[0] == "error" and "invalid placed-in-service dates" in ev[1] for ev in h.events))

        # Run 4: upload empty / corrupt CSV -> graceful st.error, no unhandled exception
        h.run(ledger_upload=_FakeUploadedFile(b"", "empty.csv"))
        self.assertTrue(any(ev[0] == "error" and "Could not read ledger" in ev[1] for ev in h.events))

    def test_fuzz_currency_stripper_500_cases(self):
        rng = random.Random(2026)
        bad_tokens = ["", " ", "\t", "abc", "1 2", "1,23", "$1$", "1$", "($-1)", "($+1)", "1e5", "NaN", "inf", "1..2"]
        for tok in bad_tokens:
            with self.assertRaises(InputValidationError):
                currency_stripper(tok)
        for _ in range(500):
            whole = rng.randint(0, 999_999_999)
            frac = f"{rng.randint(0, 999999):06d}"
            raw = f"${whole:,}.{frac}"
            parsed = currency_stripper(raw)
            self.assertEqual(parsed, Decimal(f"{whole}.{frac}"))
            # Negative parenthetical
            self.assertEqual(currency_stripper(f"({whole:,}.{frac})"), -parsed)

    def test_fuzz_reconciler_high_precision_200_scenarios(self):
        rng = random.Random(999)
        for _ in range(200):
            opening = Decimal(f"{rng.randint(0, 50000)}.{rng.randint(0, 999999):06d}")
            rows = []
            credits = Decimal("0")
            debits = Decimal("0")
            for _ in range(rng.randint(1, 12)):
                amt = Decimal(f"{rng.randint(0, 5000)}.{rng.randint(0, 999999):06d}")
                if rng.choice([True, False]):
                    rows.append({"Date": "2026-05-01", "Amount": f"${amt:,.6f}", "Type": "CREDIT"})
                    credits += amt
                else:
                    rows.append({"Date": "2026-05-02", "Amount": str(amt), "Type": "DEBIT"})
                    debits += amt
            expected = opening + credits - debits
            res = Sovereign167VReconciler(pd.DataFrame(rows), str(opening), str(expected), "0").execute_reconciliation()
            self.assertEqual(res.status, "PASS")
            self.assertEqual(Decimal(res.calculated_closing_balance), expected)

    def test_fuzz_formula_sanitization_unicode_prefixes(self):
        prefixes = ["", " ", "\t", "\n", "\r", "\ufeff", "\u2003", "\u200b", "\x00"]
        triggers = ["=", "+", "-", "@"]
        for p in prefixes:
            for t in triggers:
                out = sanitize_spreadsheet_text(f"{p}{t}CMD()")
                self.assertTrue(out.startswith("'"), msg=f"Failed to neutralize {p!r}{t!r}")

    def test_fuzz_document_router_adversarial_filenames(self):
        tricky = [
            ("..\\..\\Client_1040_W2.pdf", "1040"),
            ("=HYPERLINK(\"http://evil\",\"1040_W2.pdf\")", "1040"),
            ("1040_1065_combined.pdf", "REVIEW"),
            ("Client_1120S_K1.pdf", "REVIEW"),
            ("Client_1120-S_K1.pdf", "1120-S"),
            ("", "REVIEW"),
        ]
        for name, expected in tricky:
            with self.subTest(name=name):
                self.assertEqual(classify_filename(name)["suggested_form"], expected)

    def test_security_ast_no_network_or_shell_execution_in_source(self):
        forbidden_modules = {"subprocess", "socket", "urllib", "requests", "http", "ftplib", "telnetlib"}
        forbidden_calls = {"eval", "exec", "__import__", "system", "popen"}
        for py_file in sorted(ROOT.rglob("*.py")):
            if py_file.parent.name == "tests":
                continue
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        top = alias.name.split(".")[0]
                        self.assertNotIn(top, forbidden_modules, f"{py_file}: forbidden import {top}")
                elif isinstance(node, ast.ImportFrom) and node.module:
                    top = node.module.split(".")[0]
                    self.assertNotIn(top, forbidden_modules, f"{py_file}: forbidden import {top}")
                elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    self.assertNotIn(node.func.id, forbidden_calls, f"{py_file}: forbidden call {node.func.id}")

    def test_streamlit_config_and_github_workflow_valid(self):
        cfg = tomllib.loads((ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8"))
        self.assertEqual(cfg["server"]["maxUploadSize"], 10)
        self.assertFalse(cfg["browser"]["gatherUsageStats"])
        wf = (ROOT / ".github" / "workflows" / "python-tests.yml").read_text(encoding="utf-8")
        self.assertIn('python-version: "3.11"', wf)
        self.assertIn("python -m unittest discover -s tests -v", wf)


    def test_csv_headers_with_surrounding_spaces_normalized(self):
        df = pd.DataFrame([{" Date ": "2026-01-01", " Amount ": "50.00", " Type ": "CREDIT"}])
        res = Sovereign167VReconciler(df, "100.00", "150.00", "0.00").execute_reconciliation()
        self.assertEqual(res.status, "PASS")

        tb = pd.DataFrame([
            {" Account ": "Cash", " Debit ": "100", " Credit ": "0", " Statement ": "BALANCE SHEET", " Category ": "Assets"},
            {" Account ": "Cap", " Debit ": "0", " Credit ": "100", " Statement ": "BALANCE SHEET", " Category ": "Equity"},
        ])
        from modules.financial_statements import build_financial_statements
        self.assertEqual(build_financial_statements(tb)["trial_balance_status"], "BALANCED")

    def test_document_router_enforces_keyword_boundaries(self):
        res = classify_filename("Client_1120_NOTTRIAL-BALANCE.pdf")
        self.assertEqual(res["suggested_form"], "1120")
        self.assertEqual(res["category"], "unclassified")

    def test_book_to_tax_rejects_banana_entity(self):
        from modules.book_to_tax import build_book_to_tax_workpaper
        with self.assertRaises(InputValidationError):
            build_book_to_tax_workpaper([], 2025, entity_type="BANANA")

    def test_bonus_rate_rejects_unsupported_year_and_compact_date(self):
        from modules.depreciation_schedule import bonus_rate
        with self.assertRaises(InputValidationError):
            bonus_rate("2025-01-20", "2027-02-01")
        with self.assertRaises(InputValidationError):
            bonus_rate("20250101", "2025-06-01")

    def test_randomized_reconciliation_2000_cases(self):
        rng = random.Random(16700)
        for _ in range(2000):
            opening = rng.randint(0, 100_000)
            c = rng.randint(0, 10_000)
            d = rng.randint(0, 10_000)
            df = pd.DataFrame([
                {"Date": "2026-01-01", "Amount": str(c), "Type": "CREDIT"},
                {"Date": "2026-01-02", "Amount": str(d), "Type": "DEBIT"},
            ])
            expected = opening + c - d
            res = Sovereign167VReconciler(df, str(opening), str(expected), "0").execute_reconciliation()
            self.assertEqual(res.status, "PASS")

    def test_large_csv_100000_rows_reconciliation(self):
        n = 100_000
        df = pd.DataFrame({
            "Date": ["2026-01-01"] * n,
            "Amount": ["1.00"] * n,
            "Type": ["CREDIT"] * n,
        })
        res = Sovereign167VReconciler(df, "0.00", "100000.00", "0.00").execute_reconciliation()
        self.assertEqual(res.status, "PASS")
        self.assertEqual(res.row_count, n)

    def test_remaining_branch_coverage_across_all_modules(self):
        from modules.book_to_tax import build_book_to_tax_workpaper
        from modules.depreciation_schedule import (
            bonus_rate, build_depreciation_schedule, section_179_reference
        )

        # reconciliation.py: int input, unsupported type, empty string sanitization
        self.assertEqual(currency_stripper(1000), Decimal("1000"))
        with self.assertRaises(InputValidationError):
            currency_stripper(["100"])
        self.assertEqual(sanitize_spreadsheet_text(""), "")

        # book_to_tax.py: negative item amount
        with self.assertRaises(InputValidationError):
            build_book_to_tax_workpaper([{"code": "MEALS_274N", "amount": "-10"}], 2025)

        # depreciation_schedule.py: invalid calendar date, negative 179 cost, suv=True, optional bools, year mismatch
        with self.assertRaises(InputValidationError):
            bonus_rate("2025-02-30", "2025-06-01")
        with self.assertRaises(InputValidationError):
            section_179_reference(2025, "-1", "0")
        suv_res = section_179_reference(2026, "100000", "32000", suv=True)
        self.assertEqual(suv_res["statutory_reference_limit"], "32000")
        self.assertTrue(suv_res["within_reference_limit"])
        sched = build_depreciation_schedule([{
            "asset": "Machinery", "cost": "1000", "acquisition_date": "2025-02-01",
            "placed_in_service_date": "2025-06-01", "long_production_period": "no",
            "binding_contract_before_cutoff": "yes"
        }], 2025)
        self.assertEqual(sched["assets"][0]["illustrative_bonus_rate"], "0.40")
        with self.assertRaises(InputValidationError):
            build_depreciation_schedule([{
                "asset": "WrongYear", "cost": "1000", "acquisition_date": "2025-02-01",
                "placed_in_service_date": "2026-06-01"
            }], 2025)

    def test_app_error_and_warning_paths_all_tabs(self):
        h = _AppHarness()
        # No assets in selected year warning (assets in 2025, selected 2026)
        assets_2025 = b" asset , cost , acquisition_date , placed_in_service_date \nDesk,500,2025-02-01,2025-06-01\n"
        h.run(
            clicked=["build_fs", "build_bt", "m3_check", "build_depreciation", "check_179", "missing_items"],
            tb_upload=_FakeUploadedFile(b"bad,csv\n1,2\n", "bad_tb.csv"),
            book_tax_year=2026,
            book_tax_upload=_FakeUploadedFile(b" code , amount , description \nUNKNOWN,10,bad\n", "bad_bt.csv"),
                        depreciation_year=2026,
            asset_upload=_FakeUploadedFile(assets_2025, "assets_2025.csv"),
            **{"Year-end total assets": "bad-number", "Total §179 property cost placed in service": "bad-cost", "Return type for missing-item checklist": "9999"}
        )
        warnings = [ev[1] for ev in h.events if ev[0] == "warning"]
        errors = [ev[1] for ev in h.events if ev[0] == "error"]
        self.assertTrue(any("No assets in this file" in w for w in warnings))
        self.assertGreaterEqual(len(errors), 5)

    def test_high_precision_32_digit_reconciliation_no_rounding(self):
        big = "123456789012345678901234567890.12"
        df = pd.DataFrame([
            {"Date": "2026-01-01", "Amount": big, "Type": "CREDIT"},
            {"Date": "2026-01-02", "Amount": "0.01", "Type": "DEBIT"},
        ])
        res = Sovereign167VReconciler(df, "100.00", "123456789012345678901234567990.11", "0.00").execute_reconciliation()
        self.assertEqual(res.status, "PASS")
        self.assertEqual(res.calculated_closing_balance, "123456789012345678901234567990.11")

    def test_high_precision_across_fs_book_to_tax_and_depreciation(self):
        from modules.financial_statements import build_financial_statements
        from modules.book_to_tax import build_book_to_tax_workpaper
        from modules.depreciation_schedule import build_depreciation_schedule

        big = "123456789012345678901234567890.12"
        tb = pd.DataFrame([
            {"Account": "Cash", "Debit": big, "Credit": "0", "Statement": "BALANCE SHEET", "Category": "Assets"},
            {"Account": "Equity", "Debit": "0", "Credit": big, "Statement": "BALANCE SHEET", "Category": "Equity"},
        ])
        fs = build_financial_statements(tb)
        self.assertEqual(fs["trial_balance_status"], "BALANCED")
        self.assertEqual(fs["total_debits"], big)

        bt = build_book_to_tax_workpaper([{"code": "MEALS_274N", "amount": big}], 2025)
        self.assertEqual(bt["book_amount_total"], big)

        dep = build_depreciation_schedule(
            [{"asset": "BigAsset", "cost": big, "acquisition_date": "2025-02-01", "placed_in_service_date": "2025-06-01"}],
            2025,
        )
        self.assertEqual(dep["total_cost"], big)

    def test_rejects_monetary_input_exceeding_50_significant_digits(self):
        too_big = "9" * 51 + ".12"
        with self.assertRaises(InputValidationError):
            currency_stripper(too_big)

    def test_accounting_invariant_pnl_plus_bs_equals_tb_difference(self):
        from modules.financial_statements import build_financial_statements
        tb = pd.DataFrame([
            {"Account": "Cash", "Debit": "1000.25", "Credit": "0", "Statement": "BALANCE SHEET", "Category": "Assets"},
            {"Account": "Sales", "Debit": "0", "Credit": "750.10", "Statement": "P&L", "Category": "Revenue"},
            {"Account": "Rent", "Debit": "100.00", "Credit": "0", "Statement": "P&L", "Category": "Expense"},
        ])
        fs = build_financial_statements(tb)
        self.assertEqual(
            Decimal(fs["p_and_l_net"]) + Decimal(fs["balance_sheet_net"]),
            Decimal(fs["trial_balance_difference"]),
        )

if __name__ == "__main__":
    unittest.main()
