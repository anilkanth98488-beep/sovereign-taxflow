"""2025 Form 1040 automated end-to-end workpaper assembler & multi-tab XLSX exporter.

Chains Sovereign TaxFlow's 2025 deterministic modules (1099 Tie-Out, Schedule C/SE,
Schedule D, Schedule E, Schedule A, Tax & Credits, and Payments/Refund) into a
single Drake-style diagnostic workpaper and sanitized multi-sheet XLSX workbook.
"""
from __future__ import annotations

from decimal import Decimal, localcontext
from io import BytesIO
from typing import Any

from core.reconciliation import (
    InputValidationError,
    MONEY_CONTEXT,
    currency_stripper,
    sanitize_spreadsheet_text,
)
from modules.form_1099_tieout_2025 import build_1099_tieout
from modules.payments_and_refund_2025 import build_payments_and_refund_workpaper
from modules.schedule_a_2025 import build_schedule_a_workpaper
from modules.schedule_d_2025 import build_schedule_d_workpaper
from modules.schedule_e_2025 import build_schedule_e_workpaper
from modules.schedule_se_2025 import build_schedule_se_workpaper
from modules.tax_and_credits_2025 import build_tax_and_credits_workpaper

ZERO = Decimal("0")


def _parse_nonneg(value: Any, label: str) -> Decimal:
    amt = currency_stripper(value)
    if amt < ZERO:
        raise InputValidationError(f"{label} cannot be negative.")
    return amt


def assemble_2025_form_1040_workpaper(
    *,
    taxpayer_label: str = "Synthetic Taxpayer",
    filing_status: str = "single",
    w2_wages: Any = "0",
    w2_withholding: Any = "0",
    w2_social_security_wages: Any = "0",
    w2_medicare_wages: Any = "0",
    form_1099_docs: list[dict[str, Any]] | None = None,
    draft_1040_for_1099: dict[str, Any] | None = None,
    schedule_c_gross: Any = "0",
    schedule_c_expenses: Any = "0",
    schedule_d_transactions: list[dict[str, Any]] | None = None,
    rentals: list[dict[str, Any]] | None = None,
    k1_items: list[dict[str, Any]] | None = None,
    other_adjustments_line_26: Any = "0",
    eligible_medical_expenses: Any = "0",
    medical_reimbursements: Any = "0",
    state_and_local_taxes_paid: Any = "0",
    mortgage_interest: Any = "0",
    charitable_contributions: Any = "0",
    qualifying_children_under_17: int = 0,
    other_dependents: int = 0,
    estimated_payments: Any = "0",
    extension_payment: Any = "0",
    refundable_credits: Any = "0",
) -> dict[str, Any]:
    """Assemble an integrated 2025 Form 1040 workpaper packet with Drake-style diagnostics."""
    with localcontext(MONEY_CONTEXT):
        wages_val = _parse_nonneg(w2_wages, "w2_wages")
        w2_wh_val = _parse_nonneg(w2_withholding, "w2_withholding")
        adj_other_val = _parse_nonneg(other_adjustments_line_26, "other_adjustments_line_26")

        docs_1099 = [] if form_1099_docs is None else form_1099_docs
        draft_1099 = {} if draft_1040_for_1099 is None else draft_1040_for_1099
        tieout_1099 = build_1099_tieout(docs_1099, draft_1099, tax_year=2025) if docs_1099 or draft_1099 else None

        # Pull 1099 totals (default 0 if no 1099s)
        interest_val = ZERO
        ord_div_val = ZERO
        qual_div_val = ZERO
        taxable_dist_val = ZERO
        wh_1099_val = ZERO
        if tieout_1099 is not None:
            by_line = {c["line"]: c for c in tieout_1099["checks"]}
            interest_val = Decimal(by_line["2b"]["source_total_usd"] or "0")
            ord_div_val = Decimal(by_line["3b"]["source_total_usd"] or "0")
            qual_div_val = Decimal(by_line["3a"]["source_total_usd"] or "0")
            taxable_dist_val = Decimal(by_line["5b"]["source_total_usd"] or "0")
            wh_1099_val = Decimal(by_line["25b"]["source_total_usd"] or "0")

        se_res = build_schedule_se_workpaper(
            tax_year=2025,
            filing_status=filing_status,
            gross_receipts=schedule_c_gross,
            deductible_expenses=schedule_c_expenses,
            w2_social_security_wages=w2_social_security_wages,
            w2_medicare_wages=w2_medicare_wages,
        )
        sch_c_net = Decimal(se_res.get("schedule_c_net_profit", "0"))
        se_tax_val = Decimal(se_res.get("total_se_tax", "0"))
        half_se_ded = Decimal(se_res.get("deductible_half_se_tax_line_15", "0"))

        sch_d_res = build_schedule_d_workpaper(
            [] if schedule_d_transactions is None else schedule_d_transactions,
            tax_year=2025,
            filing_status=filing_status,
        )
        sch_d_line_7 = Decimal(sch_d_res.get("schedule_d_for_1040_line_7", "0"))

        sch_e_res = build_schedule_e_workpaper(
            tax_year=2025,
            rentals=rentals,
            k1_items=k1_items,
        )
        sch_e_total = Decimal(sch_e_res.get("schedule_e_total_for_schedule_1_line_5", "0"))

        total_income = wages_val + interest_val + ord_div_val + taxable_dist_val + sch_c_net + sch_d_line_7 + sch_e_total
        agi_val = max(ZERO, total_income - half_se_ded - adj_other_val)

        sch_a_res = build_schedule_a_workpaper(
            tax_year=2025,
            filing_status=filing_status,
            agi=str(agi_val),
            eligible_medical_expenses=eligible_medical_expenses,
            medical_reimbursements=medical_reimbursements,
            state_and_local_taxes_paid=state_and_local_taxes_paid,
            mortgage_interest=mortgage_interest,
            charitable_contributions=charitable_contributions,
        )
        std_ded = Decimal(sch_a_res["standard_deduction_reference"])
        item_ded = Decimal(sch_a_res["total_itemized_deductions"])
        deduction_taken = max(std_ded, item_ded)

        has_pref_rates = (qual_div_val > ZERO) or (Decimal(sch_d_res.get("net_long_term", "0")) > ZERO)
        tax_res = build_tax_and_credits_workpaper(
            tax_year=2025,
            filing_status=filing_status,
            agi=str(agi_val),
            deduction_taken=str(deduction_taken),
            qualifying_children_under_17=qualifying_children_under_17,
            other_dependents=other_dependents,
            qualified_dividends_or_ltcg_present=has_pref_rates,
        )
        reg_tax_after_credits = Decimal(tax_res["tax_after_nonrefundable_credits"])

        pay_res = build_payments_and_refund_workpaper(
            tax_year=2025,
            regular_tax_after_credits=str(reg_tax_after_credits),
            self_employment_tax=str(se_tax_val),
            w2_withholding_line_25a=str(w2_wh_val),
            form_1099_withholding_line_25b=str(wh_1099_val),
            estimated_payments_line_26=estimated_payments,
            extension_payment=extension_payment,
            refundable_credits=refundable_credits,
        )

        diagnostics: list[dict[str, str]] = []
        if tieout_1099 is not None:
            nec_line = {c["line"]: c for c in tieout_1099["checks"]}.get("Schedule 1 / Sch C", {})
            nec_amt = Decimal(nec_line.get("source_total_usd") or "0")
            if nec_amt > _parse_nonneg(schedule_c_gross, "schedule_c_gross"):
                diagnostics.append({
                    "module": "cross_form_1099_nec",
                    "severity": "REVIEW_REQUIRED",
                    "message": f"1099-NEC total ({nec_amt}) exceeds Schedule C gross receipts ({schedule_c_gross}).",
                })
        schedule_results = {
            "1099_tieout": tieout_1099,
            "schedule_se": se_res,
            "schedule_d": sch_d_res,
            "schedule_e": sch_e_res,
            "schedule_a": sch_a_res,
            "tax_and_credits": tax_res,
            "payments_and_refund": pay_res,
        }
        for name, mod_res in schedule_results.items():
            if mod_res is None:
                continue
            if mod_res.get("status") == "REVIEW_REQUIRED":
                diagnostics.append({
                    "module": name,
                    "severity": "REVIEW_REQUIRED",
                    "message": str(mod_res.get("review_note") or "Reviewer check required."),
                })

        overall_status = "REVIEW_REQUIRED" if diagnostics else "DRAFT_READY"
        return {
            "rule_id": "form_1040_assembler_2025",
            "tax_year": 2025,
            "taxpayer_label": str(taxpayer_label),
            "filing_status": filing_status,
            "status": overall_status,
            "summary": {
                "w2_wages_line_1a": str(wages_val),
                "taxable_interest_line_2b": str(interest_val),
                "ordinary_dividends_line_3b": str(ord_div_val),
                "capital_gain_loss_line_7": str(sch_d_line_7),
                "schedule_c_net_profit": str(sch_c_net),
                "schedule_e_total": str(sch_e_total),
                "total_income_line_9": str(total_income),
                "half_se_tax_deduction": str(half_se_ded),
                "agi_line_11": str(agi_val),
                "deduction_method": sch_a_res["deduction_recommendation"],
                "deduction_taken_line_12": str(deduction_taken),
                "taxable_income_line_15": tax_res["taxable_income"],
                "total_tax_line_24": pay_res["total_tax_line_24"],
                "total_payments_line_33": pay_res["total_payments_line_33"],
                "overpayment_refund_line_34": pay_res["overpayment_refund_line_34"],
                "amount_you_owe_line_37": pay_res["amount_you_owe_line_37"],
            },
            "diagnostics": diagnostics,
            "schedules": schedule_results,
        }


def export_1040_workpaper_xlsx(assembled: dict[str, Any]) -> BytesIO:
    """Export an assembled 2025 Form 1040 workpaper packet to a sanitized multi-tab XLSX."""
    if not isinstance(assembled, dict) or assembled.get("rule_id") != "form_1040_assembler_2025":
        raise InputValidationError("Expected output from assemble_2025_form_1040_workpaper().")

    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    wb = Workbook()
    header_font = Font(bold=True)
    header_fill = PatternFill("solid", fgColor="D9EAF7")

    # Tab 1: 1040_Summary
    ws_sum = wb.active
    ws_sum.title = "1040_Summary"
    ws_sum.append(["Line / Metric", "Value"])
    ws_sum[1][0].font = ws_sum[1][1].font = header_font
    ws_sum[1][0].fill = ws_sum[1][1].fill = header_fill
    ws_sum.append(["taxpayer_label", sanitize_spreadsheet_text(assembled["taxpayer_label"])])
    ws_sum.append(["tax_year", sanitize_spreadsheet_text(assembled["tax_year"])])
    ws_sum.append(["filing_status", sanitize_spreadsheet_text(assembled["filing_status"])])
    ws_sum.append(["overall_status", sanitize_spreadsheet_text(assembled["status"])])
    for key, val in assembled["summary"].items():
        ws_sum.append([sanitize_spreadsheet_text(key), sanitize_spreadsheet_text(val)])
    ws_sum.freeze_panes = "A2"
    ws_sum.column_dimensions["A"].width = 34
    ws_sum.column_dimensions["B"].width = 36

    # Tab 2: Diagnostics
    ws_diag = wb.create_sheet("Diagnostics")
    ws_diag.append(["Module", "Severity", "Diagnostic Note"])
    for cell in ws_diag[1]:
        cell.font = header_font
        cell.fill = header_fill
    if assembled["diagnostics"]:
        for diag in assembled["diagnostics"]:
            ws_diag.append([
                sanitize_spreadsheet_text(diag["module"]),
                sanitize_spreadsheet_text(diag["severity"]),
                sanitize_spreadsheet_text(diag["message"]),
            ])
    else:
        ws_diag.append(["ALL", "CLEAR", "No REVIEW_REQUIRED diagnostics raised."])
    ws_diag.freeze_panes = "A2"
    ws_diag.column_dimensions["A"].width = 22
    ws_diag.column_dimensions["B"].width = 18
    ws_diag.column_dimensions["C"].width = 75

    out = BytesIO()
    wb.save(out)
    out.seek(0)
    return out
