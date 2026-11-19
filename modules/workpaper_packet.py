"""Synthetic 2025 workpapers. Each explicitly named source is independent evidence."""
import inspect
import json
from datetime import datetime, timezone
from decimal import localcontext
from hashlib import sha256
from pathlib import Path

import pandas as pd
from functools import lru_cache

from core.reconciliation import MONEY_CONTEXT, InputValidationError, Sovereign167VReconciler, currency_stripper
from modules.packet_intake import read_table, ledger_from
from modules.form_1040_assembler_2025 import assemble_2025_form_1040_workpaper
from modules.business_1120_1065_2025 import build_business_return_workpaper
from modules.payroll_941_tieout_2025 import build_payroll_941_tieout
from modules.financial_statements import build_financial_statements
from modules.book_to_tax import build_book_to_tax_workpaper, m3_threshold_flags
from modules.depreciation_schedule import build_depreciation_schedule, section_179_reference
from modules.document_organizer import classify_filename
from modules.form_1099_tieout_2025 import build_1099_tieout
from modules.fiduciary_1041_2025 import build_1041_workpaper
from modules.exempt_990_2025 import build_990_workpaper
from modules.scorp_1120s_2025 import build_1120s_workpaper
from modules.qbi_199a_2025 import build_qbi_199a_workpaper
from modules.schedule_a_2025 import build_schedule_a_workpaper
from modules.schedule_d_2025 import build_schedule_d_workpaper
from modules.schedule_e_2025 import build_schedule_e_workpaper
from modules.schedule_se_2025 import build_schedule_se_workpaper
from modules.tax_and_credits_2025 import build_tax_and_credits_workpaper
from modules.payments_and_refund_2025 import build_payments_and_refund_workpaper
from modules.w2_tieout import build_w2_tieout
from modules.reviewer_notes import draft_reviewer_notes

VERSION = "synthetic-packet-2025-v1"
RULES = {"1040": assemble_2025_form_1040_workpaper, "business": build_business_return_workpaper,
         "payroll": build_payroll_941_tieout, "1099": build_1099_tieout, "w2": build_w2_tieout,
         "1041": build_1041_workpaper, "990": build_990_workpaper, "1120s": build_1120s_workpaper,
         "qbi": build_qbi_199a_workpaper, "schedule_a": build_schedule_a_workpaper,
         "schedule_d": build_schedule_d_workpaper, "schedule_e": build_schedule_e_workpaper,
         "schedule_se": build_schedule_se_workpaper, "tax_credits": build_tax_and_credits_workpaper,
         "payments": build_payments_and_refund_workpaper, "book_tax": build_book_to_tax_workpaper,
         "m3": m3_threshold_flags, "assets": build_depreciation_schedule, "section179": section_179_reference}
ROLES = ("ledger", "trial_balance", "documents", *RULES)


class Evidence(dict):
    """Producer defaults cannot turn absent nested evidence into zero."""
    def get(self, key, default=None):
        if key not in self:
            raise InputValidationError(f"Missing nested evidence: {key}")
        return self[key]


def unique_object(pairs):
    result = Evidence()
    for key, value in pairs:
        if key in result:
            raise InputValidationError(f"Duplicate field: {key}")
        result[key] = value
    return result


def facts(rows, engine):
    if set(rows[0]) != {"Field", "JSON"}:
        raise InputValidationError("Form tables require Field and JSON columns.")
    pairs = []
    for row in rows:
        value = json.loads(row["JSON"], parse_float=str, object_pairs_hook=unique_object,
                           parse_constant=lambda x: invalid(f"Invalid JSON number {x}"))
        pairs.append((row["Field"], value))
    args = unique_object(pairs)
    if set(args) != set(inspect.signature(engine).parameters):
        raise InputValidationError("Supply every named field exactly once: " +
                                   ", ".join(inspect.signature(engine).parameters))
    def reject_unknown(value):
        if value is None:
            raise InputValidationError("Null form fact. Supply evidence, an explicit zero, or an explicit empty collection.")
        if isinstance(value, (list, dict)):
            for item in (value.values() if isinstance(value, dict) else value):
                reject_unknown(item)
    reject_unknown(args)
    if "tax_year" in args and args["tax_year"] != 2025:
        raise InputValidationError("This packet accepts 2025 form inputs only.")
    for key, param in inspect.signature(engine).parameters.items():
        if isinstance(param.default, bool) and type(args[key]) is not bool:
            raise InputValidationError(f"Explicit boolean required: {key}")
    if engine is assemble_2025_form_1040_workpaper and args["form_1099_docs"]:
        check = build_1099_tieout(args["form_1099_docs"], args["draft_1040_for_1099"])
        if check["status"] != "MATCH":
            raise InputValidationError("Resolve 1099 source discrepancies before assembling 1040; run the 1099 role for the individual findings.")
    if engine is build_business_return_workpaper:
        if type(args["reportable_partner_50pct"]) is not bool:
            raise InputValidationError("Explicit yes/no partner fact required.")
        if args["entity_form"] == "1065" and not args["partner_allocations"]:
            raise InputValidationError("Partnership allocation evidence required.")
    if engine is build_depreciation_schedule:
        for asset in args["assets"]:
            for key in ("long_production_period", "binding_contract_before_cutoff"):
                if asset.get(key) not in ("yes", "no", "true", "false", True, False):
                    raise InputValidationError(f"Explicit asset fact required: {key}")
    return args


def invalid(message):
    raise InputValidationError(message)


def issues_in(obj, path=""):
    if isinstance(obj, list):
        if path.endswith(("/exceptions", "/review_reasons")):
            yield from (f"{path}: {reason}" for reason in obj)
        else:
            for i, v in enumerate(obj):
                yield from issues_in(v, f"{path}/{i}")
    elif isinstance(obj, dict):
        for k,v in obj.items():
            if isinstance(v, str) and v in {"REVIEW_REQUIRED","OUT OF BALANCE","FAIL","INPUT ERROR","REVIEW"}:
                yield f"{path}/{k}: {v}"
            elif (k == "review_required" or k.endswith("_review_required") or k == "schedule_m3_required_preliminary") and v is True:
                yield f"{path}/{k}: review required"
            elif k == "message" and "/diagnostics/" in path:
                yield str(v)
            else:
                yield from issues_in(v, f"{path}/{k}")


@lru_cache(maxsize=1)
def rule_build():
    """Identify the precise local Python rule sources, including shared dependencies."""
    root = Path(__file__).resolve().parents[1]
    digest = sha256()
    for folder in ("core", "modules"):
        for path in sorted((root / folder).glob("*.py")):
            digest.update(path.relative_to(root).as_posix().encode() + b"\0")
            digest.update(sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def run_packet(sources, opening, closing, tolerance="0.01", mapping=None):
    """sources maps a role to (filename, original bytes, explicitly selected sheet or None)."""
    controls = dict(opening=opening, closing=closing, tolerance=tolerance, mapping=mapping or {})
    result = dict(version=VERSION, rule_build_sha256=rule_build(), year=2025, approval="PENDING", controls=controls,
                  created_utc=datetime.now(timezone.utc).isoformat(), sources={}, results={}, findings=[])
    if not sources:
        raise InputValidationError("Choose at least one synthetic source.")
    for role,(name,raw,sheet) in sorted(sources.items()):
        source = {"file":Path(name).name, "sha256":sha256(raw).hexdigest(), "sheet":sheet}
        source["rule"] = f"{role}/{VERSION}"
        result["sources"][role] = source
        try:
            if role not in ROLES:
                invalid("Unknown source role.")
            rows = read_table(name,raw,sheet)
            source["row_count"] = len(rows)
            source["input_columns"] = list(rows[0])
            with localcontext(MONEY_CONTEXT):
                if role == "ledger":
                    frame = ledger_from(rows,mapping)
                    out = Sovereign167VReconciler(frame,opening,closing,tolerance).execute_reconciliation().to_dict()
                elif role == "trial_balance":
                    out = build_financial_statements(pd.DataFrame(rows))
                elif role == "documents":
                    if set(rows[0]) != {"filename"}: invalid("Expected filename column.")
                    out = {"items":[classify_filename(row["filename"]) for row in rows]}
                else:
                    engine = RULES[role]
                    out = engine(**facts(rows,engine))
            result["results"][role] = out
            source["rule"] = out.get("rule_id") or out.get("protocol") or f"{role}/{VERSION}"
            reasons = list(dict.fromkeys(issues_in(out)))
            if role in {"schedule_a", "tax_credits"}:
                reasons.append("Provisional 2025 reference values require independent CPA verification.")
            if role == "m3" or (role == "business" and out["entity_form"] == "1065"):
                reasons.append("Preliminary M-3 screen; adjusted total assets require independent review.")
            if role == "1040":
                reasons.append("2025 assembler uses provisional deduction and tax references; CPA recalculation required.")
            if role == "ledger" and out["status"] == "FAIL":
                reasons.append(f"Calculated minus expected = {out['variance']}; tolerance = {out['tolerance']}.")
            if role == "trial_balance" and out["trial_balance_status"] == "OUT OF BALANCE":
                reasons.append(f"Debits minus credits = {out['trial_balance_difference']}.")
            if role == "payroll":
                reasons.extend(f"{c['field']}: quarterly {c['total_941']}, annual {c['total_w3']}, difference {c['difference']}."
                               for c in out["checks"] if c["status"] != "MATCH")
            status = out.get("status") or out.get("trial_balance_status") or "CALCULATED"
            if reasons and status not in {"OUT OF BALANCE","FAIL","INPUT ERROR"}:
                status = "REVIEW_REQUIRED"
            source["status"] = status
            if role == "w2":
                result["w2_notes"] = draft_reviewer_notes(out)
        except Exception as exc:
            source["status"] = "INPUT ERROR"
            reasons = [str(exc) or type(exc).__name__]
        result["findings"].extend({"source":role,"status":source["status"],"detail":r} for r in reasons)
    statuses = [s["status"] for s in result["sources"].values()]
    result["status"] = next((s for s in ("INPUT ERROR","OUT OF BALANCE","FAIL","REVIEW_REQUIRED") if s in statuses),"DRAFT_READY")
    result["reviewer_notes"] = draft_reviewer_notes({"schema":"packet_exceptions_v1","findings":result["findings"]})
    return result
