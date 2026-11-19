"""Render one frozen synthetic workpaper run in three formats with its audit manifest."""
import json
import re
from datetime import datetime, timezone
from io import BytesIO
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

from docx import Document
from fpdf import FPDF
from openpyxl import Workbook, load_workbook
from core.reconciliation import sanitize_spreadsheet_text
from modules.form_1040_assembler_2025 import export_1040_workpaper_xlsx


def _zip(files):
    stream = BytesIO()
    with ZipFile(stream, "w") as archive:
        for name,data in sorted(files.items()):
            archive.writestr(ZipInfo(name, (2000,1,1,0,0,0)), data, compress_type=ZIP_DEFLATED)
    return stream.getvalue()


def _office(raw):
    with ZipFile(BytesIO(raw)) as archive:
        files = {name:archive.read(name) for name in archive.namelist()}
        name = "docProps/core.xml"
        files[name] = re.sub(rb"(<dcterms:(?:created|modified)[^>]*>)[^<]+",
                             rb"\g<1>2000-01-01T00:00:00Z", files[name])
        return _zip(files)


def _summary(m):
    lines = ["Synthetic draft | CPA review pending", f"Rule version: {m['version']}",
             f"Rule build SHA-256: {m['rule_build_sha256']}", f"Tax year: {m['year']}", f"Run UTC: {m['created_utc']}", f"Packet status: {m['status']}",
             "Reconciliation status: " + m["sources"].get("ledger", {}).get("status", "NOT RUN")]
    for role,source in m["sources"].items():
        lines += [f"{role} | {source['file']} | {source['status']}",
                  f"Rule: {source['rule']}", f"SHA-256: {source['sha256']}"]
    lines.append(f"Open findings: {len(m['findings'])}")
    lines.extend(f"{n['source']} | {n['status']} | {n['draft_question']}" for n in m["reviewer_notes"]["notes"])
    lines += ["Preparer: __________________", "Reviewer: __________________", "Sign-off date (UTC): __________________"]
    return lines


def _flatten(value, path=""):
    if isinstance(value, dict) and value:
        for key, item in value.items():
            yield from _flatten(item, f"{path}/{key}")
    elif isinstance(value, list) and value:
        for index,item in enumerate(value):
            yield from _flatten(item,f"{path}/{index}")
    else:
        yield path, json.dumps(value, ensure_ascii=False) if not isinstance(value,str) else value


def export_packet(manifest):
    lines = _summary(manifest)
    pdf = FPDF()
    pdf.set_creation_date(datetime(2000,1,1,tzinfo=timezone.utc))
    pdf.add_page()
    pdf.set_font("Helvetica","B",16)
    pdf.cell(0,10,"Workpaper Summary",new_x="LMARGIN",new_y="NEXT")
    pdf.set_font("Helvetica",size=10)
    memo = Document()
    memo.add_heading("CPA Review Memo", 0)
    for line in lines:
        memo.add_paragraph(line)
        # Core PDF fonts cover Latin-1. Escape other code points reversibly.
        pdf.multi_cell(0,6,line.encode("latin-1","backslashreplace").decode("latin-1"),new_x="LMARGIN",new_y="NEXT")
    word = BytesIO()
    memo.save(word)
    individual = manifest["results"].get("1040")
    wb = load_workbook(export_1040_workpaper_xlsx(individual)) if individual else Workbook()
    audit = wb.create_sheet("Packet audit") if individual else wb.active
    audit.title = "Packet audit"
    for line in lines:
        audit.append([sanitize_spreadsheet_text(line)])
    ws = wb.create_sheet("Workpaper values")
    ws.append(["Source / field", "Recorded value"])
    for path,value in _flatten(manifest["results"]):
        if len(value) > 32760:
            raise ValueError("Workpaper value exceeds the Excel cell limit.")
        ws.append([sanitize_spreadsheet_text(path),sanitize_spreadsheet_text(value)])
    audit.column_dimensions["A"].width=95
    ws.column_dimensions["A"].width=65
    ws.column_dimensions["B"].width=55
    stream=BytesIO()
    wb.save(stream)
    return _zip({"audit.json":json.dumps(manifest,ensure_ascii=False,sort_keys=True,indent=2).encode(),
                 "workpapers.xlsx":_office(stream.getvalue()),"summary.pdf":bytes(pdf.output()),
                 "review-memo.docx":_office(word.getvalue())})
