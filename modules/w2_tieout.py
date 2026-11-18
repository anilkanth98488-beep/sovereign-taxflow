"""2025 ordinary W-2 control comparison for a single federal return."""
import csv
import re
from decimal import Decimal, localcontext
from io import StringIO

from core.reconciliation import InputValidationError, MONEY_CONTEXT

SAMPLE = """year,reference,box1,box2
2025,W2-A,45000.00,4500.00
2025,W2-B,15000.00,1200.00"""
HEADERS = ["year", "reference", "box1", "box2"]
AUTHORITY = "https://www.irs.gov/pub/irs-prior/f1040--2025.pdf"


def references(values):
    result = {}
    for value in values:
        label = value.strip()
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", label):
            raise InputValidationError("Use a unique document label such as W2-A for each entry.")
        key = label.casefold()
        if key in result:
            raise InputValidationError(f"Duplicate document label: {label}")
        result[key] = label
    return result


def amount(text):
    text = text.strip()
    if not text:
        return None
    if not re.fullmatch(r"[0-9]{1,48}(?:\.[0-9]{1,2})?", text):
        raise InputValidationError("Use nonnegative USD amounts with at most two decimal places.")
    return Decimal(text)


def build_w2_tieout(source, inventory, wages, withholding):
    expected = references(inventory.splitlines())
    rows = list(csv.reader(StringIO(source.lstrip("\ufeff")), strict=True))
    if not rows or [field.strip() for field in rows[0]] != HEADERS:
        raise InputValidationError("Expected CSV columns: " + ",".join(HEADERS))
    if len(rows) > 10001:
        raise InputValidationError("Maximum 10,000 W-2 records.")
    evidence = []
    for row in rows[1:]:
        if len(row) != 4 or row[0].strip() != "2025":
            raise InputValidationError("Every row needs four fields and tax year 2025.")
        evidence.append({"reference": row[1].strip(), "box1": row[2].strip(), "box2": row[3].strip()})
    received = references(item["reference"] for item in evidence)
    missing = [label for key, label in expected.items() if key not in received]
    unexpected = [label for key, label in received.items() if key not in expected]
    inventory_ok = bool(expected) and not missing and not unexpected
    checks = []
    with localcontext(MONEY_CONTEXT):
        for field, line, draft in (("box1", "1a", wages), ("box2", "25a", withholding)):
            control = amount(draft)
            values = [amount(item[field]) for item in evidence]
            blank = [item["reference"] for item, value in zip(evidence, values) if value is None]
            total = sum(values, Decimal(0)) if inventory_ok and not blank else None
            difference = total - control if total is not None and control is not None else None
            checks.append({"line": line, "box": field, "blank_on": blank,
                           "source_total_usd": None if total is None else format(total, ".2f"),
                           "draft_usd": None if control is None else format(control, ".2f"),
                           "source_minus_draft_usd": None if difference is None else format(difference, ".2f"),
                           "status": "MATCH" if difference == 0 else "REVIEW_REQUIRED"})
    return {"year": 2025, "authority": AUTHORITY, "reviewer_approval": "PENDING",
            "expected_documents": list(expected.values()), "missing_documents": missing,
            "unexpected_documents": unexpected, "evidence": evidence, "checks": checks}
