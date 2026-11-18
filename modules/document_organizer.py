"""Deterministic filename routing. No AI, OCR, network, or external API calls."""
import re

ROUTES = {
    "1040": {"income": ["W-2", "1099-INT", "1099-DIV", "1099-NEC", "1099-MISC", "1099-R", "SSA-1099"],
             "deductions": ["1098", "1098-E", "1098-T", "CHARITY", "PROPERTY-TAX"],
             "identity": ["ID", "DEPENDENT", "SSN"]},
    "1120": {"corporate": ["TRIAL-BALANCE", "BALANCE-SHEET", "INCOME-STATEMENT", "PAYROLL", "FIXED-ASSET"]},
    "1120-S": {"s-corporation": ["TRIAL-BALANCE", "BALANCE-SHEET", "INCOME-STATEMENT", "PAYROLL", "SHAREHOLDER", "K-1"]},
    "1065": {"partnership": ["TRIAL-BALANCE", "BALANCE-SHEET", "INCOME-STATEMENT", "PARTNER", "K-1", "CAPITAL-ACCOUNT"]},
}


def classify_filename(filename):
    original = str(filename)
    name = re.sub(r"[^A-Z0-9]+", "-", original.upper()).strip("-")
    # Require explicit form tokens. A generic K-1 is ambiguous between 1065 and 1120-S.
    # Match the more specific 1120-S token first and remove it before
    # looking for 1120, otherwise every 1120-S filename appears ambiguous.
    form_matches = []
    if "1120-S" in name:
        form_matches.append("1120-S")
        name_for_other_forms = name.replace("1120-S", " ")
    else:
        name_for_other_forms = name
    for form in ("1065", "1120", "1040"):
        if re.search(rf"(?<![A-Z0-9]){re.escape(form)}(?![A-Z0-9])", name_for_other_forms):
            form_matches.append(form)
    if len(form_matches) == 1:
        form = form_matches[0]
    elif len(form_matches) > 1:
        form = "REVIEW"
    else:
        form = "REVIEW"
    category = "unclassified"
    if form in ROUTES:
        for group, tokens in ROUTES[form].items():
            if any(re.search(rf"(?<![A-Z0-9]){re.escape(token)}(?![A-Z0-9])", name) for token in tokens):
                category = group
                break
    return {
        "filename": original, "suggested_form": form, "category": category,
        "routing_basis": "Explicit form token and filename keywords only; human confirmation required."
    }


def missing_item_alerts(form, received_categories):
    form = str(form).upper()
    if form not in ROUTES:
        raise ValueError(f"Unsupported return type: {form}")
    received = {str(item).strip().lower() for item in received_categories if str(item).strip()}
    return sorted(set(ROUTES[form]) - received)
