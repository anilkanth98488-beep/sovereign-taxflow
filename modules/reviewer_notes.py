"""Deterministic AI-assisted reviewer-notes drafter for verified TaxFlow workpapers.

Python owns all facts, figures, decimal strings, and approval boundaries.
An optional selector may choose among approved question templates; invalid or
unavailable selections fall back deterministically. Generated notes are always
draft-only and never modify the input workpaper or grant reviewer approval.
"""
from __future__ import annotations

import copy
import json
import re
from typing import Any, Callable

APPROVED_TEMPLATES: dict[str, str] = {
    "w2_discrepancy_default": (
        "The W-2s show ${source_amount} in {field_label}. "
        "Draft Form 1040 line {line} shows ${draft_amount}. "
        "The workpaper reports a ${difference_amount} difference. "
        "Which source entry or draft figure needs correction?"
    ),
    "w2_discrepancy_audit": (
        "Reconciliation variance on Form 1040 line {line} ({field_label}): "
        "W-2 total is ${source_amount} versus draft return ${draft_amount} "
        "(difference ${difference_amount}). Please identify whether the W-2 input "
        "or the draft Form 1040 line requires adjustment."
    ),
    "w2_missing_evidence": (
        "Missing or blank evidence for Form 1040 line {line} ({field_label}): "
        "{missing_detail}. Please provide the missing W-2 document or confirmed "
        "exact-cent figure before reviewer sign-off."
    ),
    "w2_incomplete_check": (
        "Incomplete reconciliation check for Form 1040 line {line} ({field_label}): "
        "W-2 total is ${source_amount} and draft Form 1040 shows ${draft_amount}, "
        "but the workpaper did not supply a quantified difference. "
        "Please rerun the workpaper before reviewer sign-off."
    ),
    "student_loan_special_worksheet": (
        "Schedule 1, line {line} ({tax_year}) requires the special IRS Publication 970 "
        "worksheet rather than the standard phaseout screen "
        "(qualified interest ${qualified_interest}, modified AGI ${modified_agi}). "
        "Please complete and attach the Publication 970 worksheet for reviewer sign-off."
    ),
    "student_loan_missing_evidence": (
        "Missing or unresolved inputs for Schedule 1, line {line} ({tax_year}): "
        "{missing_detail}. Please supply the confirmed figures before reviewer sign-off."
    ),
}

_NUMERIC_RE = re.compile(r"^[+-]?\d+(?:\.\d+)?$")


def _group_digits(digits: str) -> str:
    """Insert thousands commas purely by string slicing (arbitrary digit length)."""
    rev = digits[::-1]
    chunks = [rev[i : i + 3] for i in range(0, len(rev), 3)]
    return ",".join(chunks)[::-1]


def _format_exact_decimal_string(raw: Any) -> str:
    """Format a numeric string with comma grouping without float or Decimal arithmetic."""
    text = str(raw).strip()
    if not _NUMERIC_RE.fullmatch(text):
        return text
    sign = ""
    if text[0] in "+-":
        if text[0] == "-":
            sign = "-"
        text = text[1:]
    if "." in text:
        int_part, frac_part = text.split(".", 1)
        grouped_int = f"{int(int_part):,}" if len(int_part) <= 15 else _group_digits(int_part)
        return f"{sign}{grouped_int}.{frac_part}"
    return f"{sign}{_group_digits(text)}"


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def _first_present(mapping: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in mapping:
            return mapping[key]
    return None


def _extract_evidence_refs(workpaper: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    for item in workpaper.get("source_references") or []:
        refs.append(str(item))
    for ev in workpaper.get("evidence") or []:
        if isinstance(ev, dict) and not _is_blank(ev.get("reference")):
            refs.append(str(ev["reference"]))
        elif isinstance(ev, str) and ev.strip():
            refs.append(ev)
    return refs


def _select_template(
    default_id: str,
    allowed_ids: tuple[str, ...],
    context: dict[str, Any],
    template_selector: Callable[[dict[str, Any]], str] | None,
) -> tuple[str, str]:
    if template_selector is not None:
        try:
            chosen = template_selector(copy.deepcopy(context))
            if isinstance(chosen, str) and chosen in allowed_ids and chosen in APPROVED_TEMPLATES:
                return chosen, "model_selected"
        except Exception:
            pass
    return default_id, "deterministic_fallback"


def _detect_schema(workpaper: dict[str, Any]) -> str:
    schema = str(workpaper.get("schema") or workpaper.get("rule_id") or "").strip().lower()
    if schema in {"w2_tieout", "2025_w2_tieout", "1040_w2_tieout", "w2_tieout_2025"}:
        return "w2_tieout"
    if schema in {"student_loan_interest_2025", "schedule_1_line_21", "student_loan_2025"}:
        return "student_loan_interest_2025"
    checks = workpaper.get("checks")
    if isinstance(checks, list) and any(
        isinstance(c, dict)
        and any(k in c for k in ("source_total_usd", "draft_usd", "source_minus_draft_usd", "w2_total", "draft_1040"))
        for c in checks
    ):
        return "w2_tieout"
    if any(k in workpaper for k in ("worksheet_magi", "modified_agi")) and any(
        k in workpaper for k in ("deduction_usd", "deduction_amount", "schedule_1_line", "special_worksheet_required")
    ):
        return "student_loan_interest_2025"
    return "UNSUPPORTED_SCHEMA"


def _build_w2_notes(
    workpaper: dict[str, Any],
    template_selector: Callable[[dict[str, Any]], str] | None,
) -> list[dict[str, Any]]:
    notes: list[dict[str, Any]] = []
    rule_id = str(workpaper.get("rule_id") or "1040_w2_tieout")
    tax_year = _first_present(workpaper, "year", "tax_year") or 2025
    source_refs = _extract_evidence_refs(workpaper)

    missing_docs = list(workpaper.get("missing_documents") or [])
    if missing_docs:
        missing_detail = f"expected W-2 document(s) not received: {', '.join(str(d) for d in missing_docs)}"
        ctx = {
            "rule_id": rule_id,
            "tax_year": tax_year,
            "line": "1a / 25a",
            "field_label": "W-2 completeness",
            "missing_detail": missing_detail,
        }
        tid, mode = _select_template("w2_missing_evidence", ("w2_missing_evidence",), ctx, template_selector)
        notes.append({
            "note_type": "MISSING_EVIDENCE",
            "rule_id": rule_id,
            "tax_year": tax_year,
            "line": "1a / 25a",
            "source_references": source_refs + [str(d) for d in missing_docs],
            "amounts": {},
            "status": "REVIEW_REQUIRED",
            "template_id": tid,
            "selection_mode": mode,
            "draft_question": APPROVED_TEMPLATES[tid].format(**ctx),
            "draft_only": True,
            "approval_granted": False,
        })

    unexpected_docs = list(workpaper.get("unexpected_documents") or [])
    if unexpected_docs:
        unexpected_detail = f"unexpected W-2 document(s) present: {', '.join(str(d) for d in unexpected_docs)}"
        ctx = {
            "rule_id": rule_id,
            "tax_year": tax_year,
            "line": "1a / 25a",
            "field_label": "W-2 completeness",
            "missing_detail": unexpected_detail,
        }
        tid, mode = _select_template("w2_missing_evidence", ("w2_missing_evidence",), ctx, template_selector)
        notes.append({
            "note_type": "UNEXPECTED_DOCUMENT",
            "rule_id": rule_id,
            "tax_year": tax_year,
            "line": "1a / 25a",
            "source_references": source_refs + [str(d) for d in unexpected_docs],
            "amounts": {},
            "status": "REVIEW_REQUIRED",
            "template_id": tid,
            "selection_mode": mode,
            "draft_question": APPROVED_TEMPLATES[tid].format(**ctx),
            "draft_only": True,
            "approval_granted": False,
        })

    for check in workpaper.get("checks") or []:
        if not isinstance(check, dict):
            continue
        status = str(check.get("status") or "").strip().upper()
        if status == "MATCH":
            continue

        box = str(check.get("box") or "").removeprefix("box")
        default_label = "federal withholding" if box == "2" else ("wages" if box == "1" else "W-2 amount")
        field_label = str(_first_present(check, "field_label", "field", "label") or default_label)
        default_line = "25a" if box == "2" else ("1a" if box == "1" else "")
        line = str(check.get("line") or default_line)

        src_raw = _first_present(check, "source_total_usd", "w2_total")
        draft_raw = _first_present(check, "draft_usd", "draft_1040")
        diff_raw = _first_present(check, "source_minus_draft_usd", "difference")
        blank_on = list(check.get("blank_on") or []) if isinstance(check.get("blank_on"), (list, tuple)) else (
            [str(check["blank_on"])] if not _is_blank(check.get("blank_on")) else []
        )
        check_refs = _extract_evidence_refs(check) or source_refs

        if _is_blank(src_raw) or _is_blank(draft_raw) or blank_on or status in {"MISSING_EVIDENCE", "MISSING_DOCUMENT"}:
            missing_parts = []
            if _is_blank(src_raw) or "source" in blank_on:
                missing_parts.append("W-2 source amount is blank")
            if _is_blank(draft_raw) or "draft" in blank_on:
                missing_parts.append("draft Form 1040 figure is blank")
            if not missing_parts:
                missing_parts.append(str(check.get("reason") or "required W-2 evidence is missing"))
            missing_detail = "; ".join(missing_parts)
            ctx = {
                "rule_id": rule_id,
                "tax_year": tax_year,
                "line": line,
                "field_label": field_label,
                "missing_detail": missing_detail,
            }
            tid, mode = _select_template("w2_missing_evidence", ("w2_missing_evidence",), ctx, template_selector)
            notes.append({
                "note_type": "MISSING_EVIDENCE",
                "rule_id": rule_id,
                "tax_year": tax_year,
                "line": line,
                "source_references": check_refs,
                "amounts": {
                    "source_total_usd": None if _is_blank(src_raw) else str(src_raw),
                    "draft_usd": None if _is_blank(draft_raw) else str(draft_raw),
                    "source_minus_draft_usd": None if _is_blank(diff_raw) else str(diff_raw),
                },
                "status": status or "REVIEW_REQUIRED",
                "template_id": tid,
                "selection_mode": mode,
                "draft_question": APPROVED_TEMPLATES[tid].format(**ctx),
                "draft_only": True,
                "approval_granted": False,
            })
            continue

        src_fmt = _format_exact_decimal_string(src_raw)
        draft_fmt = _format_exact_decimal_string(draft_raw)

        if _is_blank(diff_raw):
            ctx = {
                "rule_id": rule_id,
                "tax_year": tax_year,
                "line": line,
                "field_label": field_label,
                "source_amount": src_fmt,
                "draft_amount": draft_fmt,
            }
            tid, mode = _select_template("w2_incomplete_check", ("w2_incomplete_check",), ctx, template_selector)
            notes.append({
                "note_type": "INCOMPLETE_CHECK",
                "rule_id": rule_id,
                "tax_year": tax_year,
                "line": line,
                "source_references": check_refs,
                "amounts": {
                    "source_total_usd": str(src_raw),
                    "draft_usd": str(draft_raw),
                    "source_minus_draft_usd": None,
                },
                "status": status or "REVIEW_REQUIRED",
                "template_id": tid,
                "selection_mode": mode,
                "draft_question": APPROVED_TEMPLATES[tid].format(**ctx),
                "draft_only": True,
                "approval_granted": False,
            })
            continue

        diff_fmt = _format_exact_decimal_string(diff_raw)
        ctx = {
            "rule_id": rule_id,
            "tax_year": tax_year,
            "line": line,
            "field_label": field_label,
            "source_amount": src_fmt,
            "draft_amount": draft_fmt,
            "difference_amount": diff_fmt,
        }
        tid, mode = _select_template(
            "w2_discrepancy_default",
            ("w2_discrepancy_default", "w2_discrepancy_audit"),
            ctx,
            template_selector,
        )
        notes.append({
            "note_type": "DISCREPANCY",
            "rule_id": rule_id,
            "tax_year": tax_year,
            "line": line,
            "source_references": check_refs,
            "amounts": {
                "source_total_usd": str(src_raw),
                "draft_usd": str(draft_raw),
                "source_minus_draft_usd": str(diff_raw),
            },
            "status": status or "REVIEW_REQUIRED",
            "template_id": tid,
            "selection_mode": mode,
            "draft_question": APPROVED_TEMPLATES[tid].format(**ctx),
            "draft_only": True,
            "approval_granted": False,
        })
    return notes


def _build_student_loan_notes(
    workpaper: dict[str, Any],
    template_selector: Callable[[dict[str, Any]], str] | None,
) -> list[dict[str, Any]]:
    status = str(workpaper.get("status") or "").strip().upper()
    # Handle producer status first: CALCULATED, INELIGIBLE, and MATCH emit no exception note.
    if status in {"CALCULATED", "INELIGIBLE", "MATCH"}:
        return []

    rule_id = str(workpaper.get("rule_id") or "student_loan_interest_2025")
    tax_year = _first_present(workpaper, "tax_year", "year") or 2025
    raw_line = str(_first_present(workpaper, "schedule_1_line", "line") or "21")
    line = raw_line.replace("Schedule 1, line ", "").strip() or "21"
    source_refs = _extract_evidence_refs(workpaper)
    qi = _first_present(workpaper, "qualified_interest_usd", "qualified_interest")
    magi = _first_present(workpaper, "worksheet_magi", "modified_agi")
    deduction = _first_present(workpaper, "deduction_usd", "deduction_amount")
    special = workpaper.get("special_worksheet_required") is True

    if status == "REVIEW_REQUIRED" and special:
        ctx = {
            "rule_id": rule_id,
            "tax_year": tax_year,
            "line": line,
            "qualified_interest": "missing" if _is_blank(qi) else _format_exact_decimal_string(qi),
            "modified_agi": "missing" if _is_blank(magi) else _format_exact_decimal_string(magi),
        }
        tid, mode = _select_template(
            "student_loan_special_worksheet",
            ("student_loan_special_worksheet",),
            ctx,
            template_selector,
        )
        return [{
            "note_type": "SPECIAL_WORKSHEET_REFERRAL",
            "rule_id": rule_id,
            "tax_year": tax_year,
            "line": f"Schedule 1, line {line}",
            "source_references": source_refs,
            "amounts": {
                "qualified_interest_usd": None if _is_blank(qi) else str(qi),
                "worksheet_magi": None if _is_blank(magi) else str(magi),
                "deduction_usd": None if _is_blank(deduction) else str(deduction),
            },
            "status": status,
            "template_id": tid,
            "selection_mode": mode,
            "draft_question": APPROVED_TEMPLATES[tid].format(**ctx),
            "draft_only": True,
            "approval_granted": False,
        }]

    missing_fields = []
    if _is_blank(qi):
        missing_fields.append("qualified_interest")
    if _is_blank(magi):
        missing_fields.append("worksheet_magi")
    if _is_blank(workpaper.get("filing_status")):
        missing_fields.append("filing_status")

    if missing_fields or status == "REVIEW_REQUIRED":
        detail = (
            f"missing field(s): {', '.join(missing_fields)}"
            if missing_fields
            else str(workpaper.get("reason") or "reviewer confirmation required")
        )
        ctx = {
            "rule_id": rule_id,
            "tax_year": tax_year,
            "line": line,
            "missing_detail": detail,
        }
        tid, mode = _select_template(
            "student_loan_missing_evidence",
            ("student_loan_missing_evidence",),
            ctx,
            template_selector,
        )
        return [{
            "note_type": "MISSING_EVIDENCE",
            "rule_id": rule_id,
            "tax_year": tax_year,
            "line": f"Schedule 1, line {line}",
            "source_references": source_refs,
            "amounts": {
                "qualified_interest_usd": None if _is_blank(qi) else str(qi),
                "worksheet_magi": None if _is_blank(magi) else str(magi),
                "deduction_usd": None if _is_blank(deduction) else str(deduction),
            },
            "status": status or "REVIEW_REQUIRED",
            "template_id": tid,
            "selection_mode": mode,
            "draft_question": APPROVED_TEMPLATES[tid].format(**ctx),
            "draft_only": True,
            "approval_granted": False,
        }]
    return []


def draft_reviewer_notes(
    workpaper: dict[str, Any] | str,
    template_selector: Callable[[dict[str, Any]], str] | None = None,
) -> dict[str, Any]:
    """Generate draft reviewer follow-up notes from a supported TaxFlow workpaper."""
    if isinstance(workpaper, str):
        try:
            parsed = json.loads(workpaper)
        except Exception as exc:
            return {
                "status": "MALFORMED_JSON",
                "schema": None,
                "draft_only": True,
                "approval_granted": False,
                "notes": [],
                "error": f"Malformed JSON input: {exc}",
            }
        if not isinstance(parsed, dict):
            return {
                "status": "UNSUPPORTED_SCHEMA",
                "schema": None,
                "draft_only": True,
                "approval_granted": False,
                "notes": [],
            }
        payload = parsed
    elif isinstance(workpaper, dict):
        payload = copy.deepcopy(workpaper)
    else:
        return {
            "status": "UNSUPPORTED_SCHEMA",
            "schema": None,
            "draft_only": True,
            "approval_granted": False,
            "notes": [],
        }

    if payload.get("schema") == "packet_exceptions_v1":
        findings = payload.get("findings")
        if not isinstance(findings, list) or any(
            not isinstance(row, dict) or not all(isinstance(row.get(k), str) for k in ("source", "status", "detail"))
            for row in findings
        ):
            return {"status": "UNSUPPORTED_SCHEMA", "notes": [], "draft_only": True, "approval_granted": False}
        notes = [{"source": row["source"], "status": row["status"],
                  "draft_question": f"{row['detail']} Which source record resolves this finding?",
                  "draft_only": True, "approval_granted": False} for row in findings]
        return {"status": "DRAFT_READY" if notes else "NO_EXCEPTIONS", "notes": notes,
                "draft_only": True, "approval_granted": False, "note_count": len(notes)}

    schema = _detect_schema(payload)
    if schema == "UNSUPPORTED_SCHEMA":
        return {
            "status": "UNSUPPORTED_SCHEMA",
            "schema": None,
            "draft_only": True,
            "approval_granted": False,
            "notes": [],
        }

    if schema == "w2_tieout":
        notes = _build_w2_notes(payload, template_selector)
    else:
        notes = _build_student_loan_notes(payload, template_selector)

    return {
        "status": "DRAFT_READY" if notes else "NO_EXCEPTIONS",
        "schema": schema,
        "tax_year": _first_present(payload, "year", "tax_year"),
        "draft_only": True,
        "approval_granted": False,
        "note_count": len(notes),
        "notes": notes,
    }
