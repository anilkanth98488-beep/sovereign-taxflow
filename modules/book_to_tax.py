"""Draft book-to-tax adjustment support; no automatic tax conclusions."""
from decimal import Decimal, localcontext
from core.reconciliation import currency_stripper, InputValidationError, MONEY_CONTEXT
D = Decimal


def m3_threshold_flags(entity_type, total_assets, total_receipts="0", reportable_partner_50pct=False):
    if not isinstance(reportable_partner_50pct, bool):
        raise InputValidationError("reportable_partner_50pct must be a boolean True/False value.")
    assets = currency_stripper(total_assets)
    receipts = currency_stripper(total_receipts)
    if assets < 0 or receipts < 0:
        raise InputValidationError("Assets and receipts cannot be negative.")
    entity = str(entity_type).upper().replace("-", "").replace(" ", "")
    if entity not in {"1120", "1120S", "1065", "CORPORATION", "PARTNERSHIP"}:
        raise InputValidationError(f"Unsupported entity type: {entity_type!r}")
    preliminary = assets >= D("10000000")
    if entity in {"1065", "PARTNERSHIP"}:
        preliminary = preliminary or receipts >= D("35000000") or bool(reportable_partner_50pct)
    return {
        "schedule_m3_required_preliminary": preliminary,
        "schedule_m3_full_parts_ii_iii_threshold": assets >= D("50000000"),
        "total_assets": str(assets), "total_receipts": str(receipts),
        "review_note": "Screening flag only. Apply current form-specific instructions and partnership adjusted-asset, receipt and reportable-entity-partner tests."
    }


def build_book_to_tax_workpaper(items, tax_year, entity_type="1120"):
    if type(tax_year) is not int or tax_year < 2025 or tax_year > 2035:
        raise InputValidationError("Supported workpaper years are 2025–2035; verify current law before use.")
    if not isinstance(entity_type, str) or not entity_type.strip():
        raise InputValidationError("entity_type must be a non-empty string.")
    normalized_entity = entity_type.upper().replace("-", "").replace(" ", "")
    if normalized_entity not in {"1120", "1120S", "1065", "CORPORATION", "PARTNERSHIP"}:
        raise InputValidationError(f"Unsupported entity type: {entity_type!r}")
    with localcontext(MONEY_CONTEXT):
        return _compute_book_to_tax(items, tax_year, entity_type)


def _compute_book_to_tax(items, tax_year, entity_type):
    rows = []
    addbacks = exclusions = book_total = unresolved = D("0")
    for index, item in enumerate(items, 1):
        code = str(item.get("code", "")).strip().upper()
        amount = currency_stripper(item.get("amount"))
        if amount < 0:
            raise InputValidationError(f"Item {index}: amount must be nonnegative.")
        addback = exclusion = D("0")
        proposed_addback = "0"
        review_required = False
        note = "CPA classification and substantiation required."
        if code == "FINES_162F":
            # Do not automatically decide the §162(f) exception/identification facts.
            proposed_addback = "REVIEW_REQUIRED"
            unresolved += amount
            review_required = True
            note = "Potential §162(f) nondeductible amount. Determine whether statutory restitution, remediation, compliance, identification and other exception rules apply before quantifying an adjustment."
        elif code == "MEALS_274N":
            addback = amount * D("0.50")
            proposed_addback = str(addback)
            note = "50% limitation placeholder. Verify business purpose, substantiation, exceptions and special rules."
        elif code == "CONVENIENCE_MEALS_274O":
            addback = amount * (D("0.50") if tax_year == 2025 else D("1.00"))
            proposed_addback = str(addback)
            note = "2025 uses a provisional 50% placeholder; for amounts paid/incurred after 2025, covered §274(o) costs are generally disallowed. Confirm coverage and statutory exceptions."
        elif code == "MUNI_INTEREST_103":
            exclusion = amount
            note = "Potential §103 exclusion only. Verify instrument, ownership, private-activity bond and other statutory rules."
        else:
            raise InputValidationError(f"Item {index}: unsupported code {code!r}.")
        book_total += amount
        addbacks += addback
        exclusions += exclusion
        rows.append({
            "description": "" if item.get("description") is None else str(item.get("description")), "code": code,
            "book_amount": str(amount), "proposed_addback": proposed_addback,
            "proposed_exclusion": str(exclusion), "review_required": review_required,
            "unresolved_amount": str(amount if review_required else D("0")),
            "review_note": note
        })
    return {
        "tax_year": tax_year, "entity_type": entity_type, "items": rows,
        "book_amount_total": str(book_total), "quantified_proposed_addbacks_total": str(addbacks),
        "proposed_exclusions_total": str(exclusions),
        "unresolved_review_amount_total": str(unresolved),
        "net_quantified_proposed_adjustment": str(addbacks - exclusions),
        "review_note": "Draft M-1/M-3 support only. Items marked REVIEW_REQUIRED are excluded from quantified totals until a CPA resolves the facts. No tax return line mapping or filing conclusion is made."
    }
