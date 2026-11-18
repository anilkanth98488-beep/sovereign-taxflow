"""Fixed-asset reference workpapers; not a complete MACRS calculation."""
from datetime import date, datetime
import re
from decimal import Decimal, localcontext
from core.reconciliation import currency_stripper, InputValidationError, MONEY_CONTEXT
D = Decimal

SECTION_179_LIMITS = {
    2025: {"maximum": D("2500000"), "phaseout_start": D("4000000"), "suv_cap": D("31300")},
    2026: {"maximum": D("2560000"), "phaseout_start": D("4090000"), "suv_cap": D("32000")},
}


_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def _date(value, label):
    if isinstance(value, datetime):
        raise InputValidationError(f"Invalid {label}; pass a date or YYYY-MM-DD string, not datetime.")
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not _ISO_DATE.fullmatch(text):
        raise InputValidationError(f"Invalid {label}; use YYYY-MM-DD.")
    try:
        return date.fromisoformat(text)
    except Exception as exc:
        raise InputValidationError(f"Invalid {label}; use YYYY-MM-DD.") from exc


def _require_bool(value, label):
    if not isinstance(value, bool):
        raise InputValidationError(f"{label} must be an actual boolean True/False value.")
    return value


def bonus_rate(acquisition_date, placed_in_service_date, long_production_period=False,
               binding_contract_before_cutoff=False):
    long_production_period = _require_bool(long_production_period, "long_production_period")
    binding_contract_before_cutoff = _require_bool(
        binding_contract_before_cutoff, "binding_contract_before_cutoff"
    )
    acquired = _date(acquisition_date, "acquisition date")
    placed = _date(placed_in_service_date, "placed-in-service date")
    if acquired > placed:
        raise InputValidationError("Acquisition date cannot be after placed-in-service date.")
    if placed.year not in (2025, 2026):
        raise InputValidationError("Configured bonus-rate reference years are 2025 and 2026 only.")
    if long_production_period:
        raise InputValidationError("Long-production-period property requires separate statutory analysis; automated rate is withheld.")
    cutoff = date(2025, 1, 19)
    if acquired > cutoff and placed > cutoff and not binding_contract_before_cutoff:
        return D("1.00")
    if placed.year == 2025:
        return D("0.40")
    if placed.year == 2026:
        return D("0.20")
    return D("0")


def section_179_reference(tax_year, total_cost_placed_in_service, requested_election="0", suv=False):
    if type(tax_year) is not int or tax_year not in SECTION_179_LIMITS:
        raise InputValidationError("Configured §179 reference limits are 2025 and 2026 only.")
    cost = currency_stripper(total_cost_placed_in_service)
    requested = currency_stripper(requested_election)
    if cost < 0 or requested < 0:
        raise InputValidationError("Costs and election cannot be negative.")
    if requested > cost:
        raise InputValidationError("Requested §179 election cannot exceed the total cost being evaluated.")
    if not isinstance(suv, bool):
        raise InputValidationError("suv must be an actual boolean True/False value.")
    limits = SECTION_179_LIMITS[tax_year]
    with localcontext(MONEY_CONTEXT):
        reduced = max(D("0"), limits["maximum"] - max(D("0"), cost - limits["phaseout_start"]))
    if suv:
        reduced = min(reduced, limits["suv_cap"])
    return {
        "tax_year": tax_year, "statutory_reference_limit": str(reduced),
        "requested_election": str(requested), "within_reference_limit": requested <= reduced,
        "review_note": "Reference ceiling only. Eligible property, taxable-income limitation, business-use, related-party, SUV definition and elections are not determined. Verify current law and IRS instructions."
    }


def _parse_optional_bool(value, label):
    if value is None or str(value).strip() == "":
        return False
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "y"}:
        return True
    if normalized in {"0", "false", "no", "n"}:
        return False
    raise InputValidationError(f"{label} must be blank or one of yes/no, true/false, or 1/0.")


def build_depreciation_schedule(assets, tax_year):
    if type(tax_year) is not int or tax_year not in (2025, 2026):
        raise InputValidationError("This reference helper is configured for tax years 2025 and 2026 only.")
    with localcontext(MONEY_CONTEXT):
        return _compute_depreciation_schedule(assets, tax_year)


def _compute_depreciation_schedule(assets, tax_year):
    rows = []
    for index, asset in enumerate(assets, 1):
        cost = currency_stripper(asset.get("cost"))
        acquired = _date(asset.get("acquisition_date"), "acquisition date")
        placed = _date(asset.get("placed_in_service_date"), "placed-in-service date")
        if cost < 0 or placed.year != tax_year:
            raise InputValidationError(f"Asset {index}: negative cost or placed-in-service year mismatch.")
        long_production = _parse_optional_bool(asset.get("long_production_period", ""), "long_production_period")
        binding = _parse_optional_bool(asset.get("binding_contract_before_cutoff", ""), "binding_contract_before_cutoff")
        rate = bonus_rate(acquired, placed, long_production, binding)
        raw_name = asset.get("asset")
        asset_name = f"Asset {index}" if raw_name is None or not str(raw_name).strip() else str(raw_name)
        rows.append({
            "asset": asset_name, "cost": str(cost),
            "acquisition_date": acquired.isoformat(), "placed_in_service_date": placed.isoformat(),
            "illustrative_bonus_rate": str(rate), "illustrative_bonus_amount": str(cost * rate),
            "method": "Reference screen only; no MACRS method, convention, eligibility or election determined."
        })
    return {
        "tax_year": tax_year, "assets": rows,
        "total_cost": str(sum((D(row["cost"]) for row in rows), D("0"))),
        "total_illustrative_bonus": str(sum((D(row["illustrative_bonus_amount"]) for row in rows), D("0"))),
        "section_179_reference": {k: str(v) for k, v in SECTION_179_LIMITS[tax_year].items()},
        "review_note": "Not a MACRS schedule. Long-production-period property is withheld for separate review. Verify acquisition/binding-contract rules, qualified-property status, class life, convention, business use, listed property and elections."
    }


def partition_assets_by_tax_year(assets, tax_year):
    """Separate assets by placed-in-service year and report invalid date rows.

    Returns (selected, other_year, invalid). Invalid rows are never silently
    discarded by the UI; callers should display them and require correction.
    """
    if type(tax_year) is not int:
        raise InputValidationError("tax_year must be an integer year.")
    selected, other_year, invalid = [], [], []
    for index, asset in enumerate(assets, 1):
        try:
            placed = _date(asset.get("placed_in_service_date"), "placed-in-service date")
        except InputValidationError as exc:
            invalid.append({"row_number": index, "asset": str(asset.get("asset", f"Asset {index}")),
                            "reason": str(exc), "source_row": dict(asset)})
            continue
        (selected if placed.year == tax_year else other_year).append(dict(asset))
    return selected, other_year, invalid
