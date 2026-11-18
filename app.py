"""Sovereign TaxFlow — local Streamlit workpaper demonstration."""
from hashlib import sha256
import csv
import json
import pandas as pd
import streamlit as st
from io import BytesIO

from core.reconciliation import Sovereign167VReconciler, InputValidationError, validate_headers
from modules.financial_statements import build_financial_statements
from modules.book_to_tax import build_book_to_tax_workpaper, m3_threshold_flags
from modules.depreciation_schedule import (
    build_depreciation_schedule, section_179_reference, partition_assets_by_tax_year
)
from modules.w2_tieout import SAMPLE, build_w2_tieout
from modules.document_organizer import classify_filename, missing_item_alerts

st.set_page_config(page_title="Sovereign TaxFlow", layout="wide")
st.title("Sovereign TaxFlow")
st.caption("Deterministic Workpaper Preparation & Quality-Control Assistant")
st.warning("CPA review required. This is not tax-filing software, tax advice, an audit opinion, or a compliance guarantee.")
st.sidebar.info("Synthetic or authorized data only. Do not upload SSNs, credentials, or confidential client data to this demonstration app.")

# Clear results whenever source bytes or calculation parameters change.
def read_csv_upload(upload):
    df = pd.read_csv(BytesIO(upload.getvalue()), dtype=str, keep_default_na=False, encoding="utf-8-sig")
    validate_headers(df)
    df.columns = [str(c).strip() for c in df.columns]
    return df

def upload_digest(upload):
    if upload is None:
        return "NO_FILE"
    return sha256(upload.getvalue()).hexdigest()

def clear_if_changed(state_key, current_fingerprint, result_key, *extra_keys):
    previous = st.session_state.get(state_key)
    if previous != current_fingerprint:
        st.session_state.pop(result_key, None)
        for key in extra_keys:
            st.session_state.pop(key, None)
        st.session_state[state_key] = current_fingerprint


tabs = st.tabs(["Reconciliation", "Financial Statements", "Book-to-Tax", "Depreciation", "Document Organizer", "1040 W-2"])

with tabs[0]:
    upload = st.file_uploader("Ledger CSV: Date, Amount, Type", type=["csv"], key="ledger_upload")
    col1, col2, col3 = st.columns(3)
    opening = col1.text_input("Opening balance", "1000.00", key="opening")
    closing = col2.text_input("Expected closing balance", "1250.00", key="closing")
    tolerance = col3.text_input("Tolerance", "0.01", key="tolerance")
    ledger_key = upload_digest(upload)
    recon_fingerprint = sha256(json.dumps([ledger_key, opening, closing, tolerance], separators=(",", ":")).encode()).hexdigest()
    clear_if_changed("recon_input_fingerprint", recon_fingerprint, "recon_result", "recon_ledger", "recon_parameters")
    if upload is not None:
        try:
            ledger = read_csv_upload(upload)
            st.dataframe(ledger, use_container_width=True)
            if st.button("Run reconciliation", key="run_reconciliation"):
                reconciler = Sovereign167VReconciler(ledger, opening, closing, tolerance)
                st.session_state["recon_result"] = reconciler.execute_reconciliation()
                st.session_state["recon_ledger"] = ledger
                st.session_state["recon_parameters"] = (opening, closing, tolerance)
        except Exception as exc:
            st.error(f"Could not read ledger: {exc}")
    result = st.session_state.get("recon_result")
    if result is not None:
        st.metric("Reconciliation status", result.status)
        st.json(result.to_dict())
        if result.status == "PASS":
            try:
                saved_ledger = st.session_state["recon_ledger"]
                saved_params = st.session_state["recon_parameters"]
                export_engine = Sovereign167VReconciler(saved_ledger, *saved_params)
                xlsx_bytes = export_engine.export_xlsx(result).getvalue()
                st.download_button(
                    "Download verified PASS workpaper (XLSX)", data=xlsx_bytes,
                    file_name="sovereign_reconciliation_workpaper.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    on_click="ignore"
                )
            except Exception as exc:
                st.error(f"Export blocked: {exc}")

with tabs[1]:
    upload = st.file_uploader("Trial balance CSV: Account, Debit, Credit, Statement, Category", type=["csv"], key="tb_upload")
    fp = upload_digest(upload)
    clear_if_changed("tb_fingerprint", fp, "fs_result")
    if upload:
        try:
            df = read_csv_upload(upload)
            st.dataframe(df, use_container_width=True)
            if st.button("Build draft statements", key="build_fs"):
                st.session_state["fs_result"] = build_financial_statements(df)
        except Exception as exc:
            st.error(str(exc))
    if st.session_state.get("fs_result"):
        st.json(st.session_state["fs_result"])

with tabs[2]:
    year = st.selectbox("Tax year", [2025, 2026], key="book_tax_year")
    upload = st.file_uploader("Book-to-tax CSV: code, amount, description", type=["csv"], key="book_tax_upload")
    fp = sha256((upload_digest(upload) + str(year)).encode()).hexdigest()
    clear_if_changed("bt_fingerprint", fp, "bt_result")
    if upload:
        try:
            if st.button("Build draft adjustment workpaper", key="build_bt"):
                items = read_csv_upload(upload).to_dict("records")
                st.session_state["bt_result"] = build_book_to_tax_workpaper(items, year)
        except Exception as exc:
            st.error(str(exc))
    if st.session_state.get("bt_result"):
        st.json(st.session_state["bt_result"])
    entity = st.selectbox("Entity form for preliminary M-3 screen", ["1120", "1120-S", "1065"])
    assets = st.text_input("Year-end total assets", "0")
    receipts = st.text_input("Total receipts (partnership screen)", "0")
    if st.button("Check preliminary M-3 flags", key="m3_check"):
        try:
            st.json(m3_threshold_flags(entity, assets, receipts))
        except Exception as exc:
            st.error(str(exc))

with tabs[3]:
    year = st.selectbox("Placed-in-service year", [2025, 2026], key="depreciation_year")
    upload = st.file_uploader("Asset CSV: asset, cost, acquisition_date, placed_in_service_date", type=["csv"], key="asset_upload")
    fp = sha256((upload_digest(upload) + str(year)).encode()).hexdigest()
    clear_if_changed("dep_fingerprint", fp, "dep_result")
    if upload:
        try:
            if st.button("Build depreciation reference", key="build_depreciation"):
                all_assets = read_csv_upload(upload).to_dict("records")
                selected_assets, other_year_assets, invalid_assets = partition_assets_by_tax_year(all_assets, year)
                if invalid_assets:
                    st.error(f"{len(invalid_assets)} asset row(s) have invalid placed-in-service dates. Correct them before generating this workpaper.")
                    st.dataframe(pd.DataFrame(invalid_assets), use_container_width=True)
                    st.session_state.pop("dep_result", None)
                elif not selected_assets:
                    st.warning(f"No assets in this file have a placed-in-service date in {year}.")
                    st.session_state.pop("dep_result", None)
                else:
                    if other_year_assets:
                        st.info(f"{len(other_year_assets)} asset row(s) from other tax years were excluded from this {year} workpaper.")
                    st.session_state["dep_result"] = build_depreciation_schedule(selected_assets, year)
        except Exception as exc:
            st.error(str(exc))
    if st.session_state.get("dep_result"):
        st.json(st.session_state["dep_result"])
    cost = st.text_input("Total §179 property cost placed in service", "0")
    election = st.text_input("Requested §179 election", "0")
    suv = st.checkbox("Apply configured SUV reference cap")
    if st.button("Check §179 reference limit", key="check_179"):
        try:
            st.json(section_179_reference(year, cost, election, suv=suv))
        except Exception as exc:
            st.error(str(exc))

with tabs[4]:
    names = st.text_area("Paste document filenames, one per line")
    docs_fp = sha256(names.encode()).hexdigest()
    clear_if_changed("docs_fingerprint", docs_fp, "doc_results")
    if st.button("Classify filenames", key="classify_docs"):
        st.session_state["doc_results"] = [classify_filename(name) for name in names.splitlines() if name.strip()]
    if st.session_state.get("doc_results"):
        st.dataframe(pd.DataFrame(st.session_state["doc_results"]), use_container_width=True)
    form = st.selectbox("Return type for missing-item checklist", ["1040", "1120", "1120-S", "1065"])
    received = st.text_input("Received categories (comma separated)", "income")
    missing_fp = sha256(json.dumps([form, received], separators=(",", ":")).encode()).hexdigest()
    clear_if_changed("missing_items_fingerprint", missing_fp, "missing_items_result")
    if st.button("Show missing-item alerts", key="missing_items"):
        try:
            st.session_state["missing_items_result"] = missing_item_alerts(form, [item.strip() for item in received.split(",") if item.strip()])
        except Exception as exc:
            st.error(str(exc))
    if "missing_items_result" in st.session_state:
        st.write(st.session_state["missing_items_result"])


with tabs[-1]:
    st.caption("2025 Form 1040 • Ordinary W-2 wages and withholding • CPA review pending")
    st.write("Compare one return using exact cents. Use document labels only. Review corrected forms, special wage treatments and whole-dollar rounding separately.")
    inventory = st.text_area("Expected W-2 labels, one per line", "W2-A\nW2-B", key="w2_inventory")
    source = st.text_area("W-2 source rows (synthetic example)", SAMPLE, key="w2_source")
    wages = st.text_input("Draft line 1a wages", "60000.00", key="w2_wages")
    withholding = st.text_input("Draft line 25a withholding", "5500.00", key="w2_withholding")
    fingerprint = sha256(json.dumps([inventory, source, wages, withholding]).encode()).hexdigest()
    clear_if_changed("w2_fingerprint", fingerprint, "w2_result")
    if st.button("Check W-2 amounts", key="run_w2"):
        try:
            st.session_state["w2_result"] = build_w2_tieout(source, inventory, wages, withholding)
        except (InputValidationError, csv.Error) as exc:
            st.error(str(exc))
    if st.session_state.get("w2_result"):
        workpaper = st.session_state["w2_result"]
        st.json(workpaper)
        st.download_button("Download W-2 workpaper (JSON)", data=json.dumps(workpaper, indent=2),
                           file_name="w2-tieout-2025.json", mime="application/json", on_click="ignore")
