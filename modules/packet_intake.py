"""Strict rectangular CSV, single-sheet XLSX and text-PDF intake for synthetic packets."""
import csv
from datetime import date, datetime, time
from io import BytesIO, StringIO
from pathlib import Path
from decimal import Decimal
from defusedxml.ElementTree import iterparse
from zipfile import ZipFile

import pdfplumber
from openpyxl import load_workbook

from core.reconciliation import InputValidationError
from modules.csv_mapper import map_bank_csv_to_ledger


def csv_bytes(rows):
    stream = StringIO(newline="")
    csv.writer(stream).writerows(rows)
    return stream.getvalue().encode("utf-8")


def _excel(raw, sheet):
    with ZipFile(BytesIO(raw)) as archive:
        if sum(entry.file_size for entry in archive.infolist()) > 32_000_000:
            raise InputValidationError("Expanded XLSX exceeds packet limit.")
    wb = load_workbook(BytesIO(raw), read_only=True, data_only=False)
    try:
        if sheet is None and len(wb.sheetnames) != 1:
            raise InputValidationError("Select one XLSX sheet explicitly.")
        ws = wb[sheet or wb.sheetnames[0]]
        if (ws.max_row or 0) > 10001 or (ws.max_column or 0) > 100:
            raise InputValidationError("Worksheet exceeds packet limits.")
        # openpyxl converts numeric cells to binary floats. Read their stored
        # decimal tokens from the selected sheet before building monetary rows.
        numbers = {}
        with ZipFile(BytesIO(raw)) as archive, archive.open(ws._worksheet_path) as xml:
            for _, element in iterparse(xml, events=("end",)):
                if element.tag.endswith("}c"):
                    token = element.find("{*}v")
                    if element.get("t", "n") == "n" and token is not None and token.text:
                        numbers[element.get("r")] = token.text
                    element.clear()
        rows = []
        for cells in ws.rows:
            row = []
            for cell in cells:
                value = cell.value
                if cell.data_type in {"f", "e", "b"}:
                    raise InputValidationError("Formula, error or boolean cell requires source evidence.")
                if isinstance(value, datetime):
                    if value.time() != time.min:
                        raise InputValidationError("A date with a time requires explicit conversion.")
                    value = value.date()
                if isinstance(value, date):
                    value = value.isoformat()
                if isinstance(value, (float, int)):
                    exact = Decimal(numbers[cell.coordinate])
                    if not exact.is_finite() or len(exact.as_tuple().digits) > 15 or abs(exact.adjusted()) > 50:
                        raise InputValidationError("Use text for high-precision Excel numbers.")
                    value = format(exact, "f")
                row.append("" if value is None else str(value))
            rows.append(row)
        return rows
    finally:
        wb.close()


def _pdf(raw):
    rows = []
    with pdfplumber.open(BytesIO(raw)) as doc:
        if len(doc.pages) > 40:
            raise InputValidationError("PDF exceeds the 40-page packet limit.")
        for page in doc.pages:
            if page.images:
                raise InputValidationError("Image-bearing PDF needs independent transcription.")
            tables = page.find_tables()
            if tables:
                if len(tables) != 1:
                    raise InputValidationError("Expected one ruled table per PDF page.")
                table = tables[0]
                if page.outside_bbox(table.bbox).extract_words():
                    raise InputValidationError("Text outside the PDF table requires review.")
                part = table.extract()
            else:
                lines = (page.extract_text() or "").splitlines()
                if not lines or any("|" not in line for line in lines):
                    raise InputValidationError("Expected a text table with explicit pipe separators or ruled cells.")
                part = [line.split("|") for line in lines]
            if not part or (rows and part[0] != rows[0]):
                raise InputValidationError("Every PDF page needs the same explicit header.")
            rows.extend(part[1:] if rows else part)
    return rows


def read_table(filename, raw, sheet=None):
    if not raw or len(raw) > 10_000_000:
        raise InputValidationError("Empty source or file larger than 10 MB.")
    suffix = Path(filename).suffix.lower()
    if suffix == ".csv":
        rows = list(csv.reader(StringIO(raw.decode("utf-8-sig"), newline=""), strict=True))
    elif suffix == ".xlsx":
        rows = _excel(raw, sheet)
    elif suffix == ".pdf":
        rows = _pdf(raw)
    else:
        raise InputValidationError("Choose CSV, XLSX or a text PDF.")
    if len(rows) < 2 or len(rows) > 10001:
        raise InputValidationError("Expected 1 to 10,000 data rows.")
    headers = [str(v or "").lstrip("\ufeff").strip() for v in rows[0]]
    keys = [v.casefold() for v in headers]
    if not all(keys) or len(set(keys)) != len(keys) or len(keys) > 100:
        raise InputValidationError("Blank, duplicate or excessive headers.")
    records = []
    for n, row in enumerate(rows[1:], 2):
        if len(row) != len(headers) or not any(str(v or "").strip() for v in row):
            raise InputValidationError(f"Malformed or blank row {n}.")
        records.append(dict(zip(headers, [str(v or "").strip() for v in row])))
    return records


def ledger_from(records, mapping):
    headers = list(records[0])
    if not mapping:
        # Each alias denotes one specific direction or a signed amount.
        aliases = {"date_col": ("date", "transaction date", "posting date"),
                   "amount_col": ("amount", "net"), "type_col": ("type",),
                   "debit_col": ("debit", "withdrawal", "withdrawals", "money spent"),
                   "credit_col": ("credit", "deposit", "deposits", "money received")}
        mapping = {}
        for key, choices in aliases.items():
            hits = [h for h in headers if h.casefold() in choices]
            if len(hits) > 1:
                raise InputValidationError(f"Ambiguous {key}. Supply explicit mapping.")
            mapping[key] = hits[0] if hits else None
        if mapping["amount_col"] and not mapping["type_col"] and mapping["amount_col"].casefold() != "net":
            raise InputValidationError("Specify a type column or explicitly map a signed amount column.")
        if (mapping["debit_col"] or mapping["credit_col"]) and (mapping["amount_col"] or mapping["type_col"]):
            raise InputValidationError("Conflicting amount layouts. Supply explicit mapping.")
    raw = csv_bytes([headers] + [list(row.values()) for row in records])
    return map_bank_csv_to_ledger(raw, **mapping)
