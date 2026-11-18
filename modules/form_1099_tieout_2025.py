"""2025 Form 1099 (INT, DIV, NEC, R) tie-out against draft Form 1040 lines.

Deterministic arithmetic using 64-digit MONEY_CONTEXT. Emits exact PR #5-aligned
keys (year, box, line, source_total_usd, draft_usd, source_minus_draft_usd,
blank_on, missing_documents, unexpected_documents, evidence, status).
"""
from __future__ import annotations

from decimal import Decimal, localcontext
from typing import Any

from core.reconciliation import InputValidationError, MONEY_CONTEXT, currency_stripper

ZERO = Decimal("0")

FORM_1099_MAPPINGS = (
    ("1099-INT", "Box 1", "2b", "taxable_interest", "taxable interest (1099-INT Box 1)"),
    ("1099-DIV", "Box 1a", "3b", "ordinary_dividends", "ordinary dividends (1099-DIV Box 1a)"),
    ("1099-DIV", "Box 1b", "3a", "qualified_dividends", "qualified dividends (1099-DIV Box 1b)"),
    ("1099-NEC", "Box 1", "Schedule 1 / Sch C", "nonemployee_comp", "nonemployee compensation (1099-NEC Box 1)"),
    ("1099-R", "Box 1", "5a", "gross_distribution", "gross retirement distribution (1099-R Box 1)"),
    ("1099-R", "Box 2a", "5b", "taxable_distribution", "taxable retirement distribution (1099-R Box 2a)"),
    ("ALL_1099", "Box 4", "25b", "federal_withholding", "federal income tax withheld (1099 Box 4)"),
)


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def _parse_nonneg(value: Any, label: str) -> Decimal:
    amt = currency_stripper(value)
    if amt < ZERO:
        raise InputValidationError(f"{label} cannot be negative.")
    return amt


def build_1099_tieout(
    documents: list[dict[str, Any]],
    draft_1040: dict[str, Any],
    expected_documents: list[str] | None = None,
    tax_year: int = 2025,
) -> dict[str, Any]:
    """Reconcile 2025 Form 1099 source documents against draft Form 1040 lines."""
    if type(tax_year) is not int or tax_year != 2025:
        raise InputValidationError("Configured Form 1099 tie-out year is 2025 only.")
    if not isinstance(documents, list):
        raise InputValidationError("documents must be a list of Form 1099 records.")
    if not isinstance(draft_1040, dict):
        raise InputValidationError("draft_1040 must be a dictionary of draft return lines.")

    with localcontext(MONEY_CONTEXT):
        seen_ids: list[str] = []
        seen_forms: set[str] = set()
        evidence: list[dict[str, str]] = []
        totals: dict[str, Decimal] = {key: ZERO for _, _, _, key, _ in FORM_1099_MAPPINGS}
        blank_source_keys: set[str] = set()
        box2b_not_determined = False

        for idx, doc in enumerate(documents, 1):
            if not isinstance(doc, dict):
                raise InputValidationError(f"Document {idx} must be a dict.")
            form_type = str(doc.get("form_type") or "").strip().upper()
            if form_type not in {"1099-INT", "1099-DIV", "1099-NEC", "1099-R"}:
                raise InputValidationError(f"Document {idx}: unsupported form_type {form_type!r}.")
            raw_ref = doc.get("reference") if not _is_blank(doc.get("reference")) else doc.get("doc_id")
            ref = f"{form_type}_{idx}" if _is_blank(raw_ref) else str(raw_ref).strip()
            seen_ids.append(ref)
            seen_forms.add(form_type)
            evidence.append({"form_type": form_type, "reference": ref})

            # Federal withholding (Box 4) applies across all 1099 types
            wh_raw = doc.get("federal_withholding", "0.00")
            if "federal_withholding" in doc and _is_blank(doc.get("federal_withholding")):
                blank_source_keys.add("federal_withholding")
            elif not _is_blank(wh_raw):
                totals["federal_withholding"] += _parse_nonneg(wh_raw, f"{ref} federal_withholding")

            if form_type == "1099-INT":
                raw = doc.get("taxable_interest")
                if _is_blank(raw):
                    blank_source_keys.add("taxable_interest")
                else:
                    totals["taxable_interest"] += _parse_nonneg(raw, f"{ref} taxable_interest")

            elif form_type == "1099-DIV":
                ord_raw = doc.get("ordinary_dividends")
                qual_raw = doc.get("qualified_dividends", "0.00")
                ord_amt: Decimal | None = None
                if _is_blank(ord_raw):
                    blank_source_keys.add("ordinary_dividends")
                else:
                    ord_amt = _parse_nonneg(ord_raw, f"{ref} ordinary_dividends")
                    totals["ordinary_dividends"] += ord_amt

                if "qualified_dividends" in doc and _is_blank(doc.get("qualified_dividends")):
                    blank_source_keys.add("qualified_dividends")
                elif not _is_blank(qual_raw):
                    qual_amt = _parse_nonneg(qual_raw, f"{ref} qualified_dividends")
                    if ord_amt is not None and qual_amt > ord_amt:
                        raise InputValidationError(
                            f"{ref}: qualified dividends ({qual_amt}) cannot exceed ordinary dividends ({ord_amt})."
                        )
                    totals["qualified_dividends"] += qual_amt

            elif form_type == "1099-NEC":
                raw = doc.get("nonemployee_comp")
                if _is_blank(raw):
                    blank_source_keys.add("nonemployee_comp")
                else:
                    totals["nonemployee_comp"] += _parse_nonneg(raw, f"{ref} nonemployee_comp")

            elif form_type == "1099-R":
                gross_raw = doc.get("gross_distribution")
                tax_raw = doc.get("taxable_distribution")
                if "taxable_amount_not_determined" in doc and doc.get("taxable_amount_not_determined") is not None:
                    flag = doc.get("taxable_amount_not_determined")
                    if not isinstance(flag, bool):
                        raise InputValidationError(
                            f"{ref}: taxable_amount_not_determined must be a boolean True/False."
                        )
                    if flag:
                        box2b_not_determined = True
                if _is_blank(gross_raw):
                    blank_source_keys.add("gross_distribution")
                else:
                    totals["gross_distribution"] += _parse_nonneg(gross_raw, f"{ref} gross_distribution")
                if _is_blank(tax_raw):
                    blank_source_keys.add("taxable_distribution")
                else:
                    totals["taxable_distribution"] += _parse_nonneg(tax_raw, f"{ref} taxable_distribution")

        if len(seen_ids) != len(set(seen_ids)):
            raise InputValidationError("Duplicate Form 1099 reference/doc_id values are rejected.")

        missing_docs: list[str] = []
        unexpected_docs: list[str] = []
        if expected_documents is not None:
            if not isinstance(expected_documents, list):
                raise InputValidationError("expected_documents must be a list of strings.")
            exp_clean: list[str] = []
            for item in expected_documents:
                if not isinstance(item, str) or not item.strip():
                    raise InputValidationError("expected_documents cannot contain blank or non-string entries.")
                exp_clean.append(item.strip())
            if len(exp_clean) != len(set(exp_clean)):
                raise InputValidationError("Duplicate expected_documents entries are rejected.")
            missing_docs = sorted(set(exp_clean) - set(seen_ids))
            unexpected_docs = sorted(set(seen_ids) - set(exp_clean))

        checks: list[dict[str, Any]] = []
        for form_label, box, line, key, field_label in FORM_1099_MAPPINGS:
            line_in_draft = line in draft_1040
            draft_raw = draft_1040.get(line)
            form_applicable = (form_label in seen_forms) or (form_label == "ALL_1099" and bool(seen_forms))

            blank_on: list[str] = []
            if key in blank_source_keys:
                blank_on.append("source")
            if form_applicable and _is_blank(draft_raw):
                blank_on.append("draft")
            elif line_in_draft and _is_blank(draft_raw):
                blank_on.append("draft")

            src_val = totals[key]
            if not form_applicable and not line_in_draft:
                draft_val = ZERO
                draft_str: str | None = "0.00"
            elif _is_blank(draft_raw):
                draft_val = ZERO
                draft_str = None
            else:
                draft_val = _parse_nonneg(draft_raw, f"draft line {line}")
                draft_str = str(draft_val)

            if blank_on or missing_docs or unexpected_docs or (key == "taxable_distribution" and box2b_not_determined):
                status = "REVIEW_REQUIRED"
                diff_str = None
            else:
                diff_val = src_val - draft_val
                diff_str = str(diff_val)
                # 1099-NEC always requires Schedule C / SE tax review even if gross ties
                if key == "nonemployee_comp" and src_val > ZERO:
                    status = "REVIEW_REQUIRED"
                else:
                    status = "MATCH" if diff_val == ZERO else "REVIEW_REQUIRED"

            checks.append({
                "form": form_label,
                "box": box,
                "line": line,
                "field_label": field_label,
                "source_total_usd": None if "source" in blank_on else str(src_val),
                "draft_usd": draft_str,
                "source_minus_draft_usd": diff_str,
                "blank_on": blank_on,
                "status": status,
            })

        overall = "MATCH" if (not missing_docs and not unexpected_docs and all(c["status"] == "MATCH" for c in checks)) else "REVIEW_REQUIRED"
        return {
            "rule_id": "1040_1099_tieout_2025",
            "year": tax_year,
            "status": overall,
            "missing_documents": missing_docs,
            "unexpected_documents": unexpected_docs,
            "evidence": evidence,
            "checks": checks,
            "review_note": "Workpaper tie-out only. 1099-NEC Schedule C/SE tax applicability and 1099-R Box 2b taxable-amount determinations require CPA review.",
        }
