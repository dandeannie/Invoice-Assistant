"""
Export. Takes the list of extracted invoices and writes:
  - an Excel workbook with two sheets:
        'Invoices'   - one row per invoice (header fields + validation status)
        'Line Items' - one row per line item, linked back to its invoice
  - optionally, the same two tables as CSV files.
"""
from __future__ import annotations
import csv
import os
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

from .models import Invoice

HEADER_FONT = Font(name="Arial", bold=True, color="FFFFFF")
HEADER_FILL = PatternFill("solid", fgColor="2F5B8F")
BODY_FONT = Font(name="Arial")
FLAG_FILL = PatternFill("solid", fgColor="FBE4D5")  # light orange for flagged rows
TOTALS_FILL = PatternFill("solid", fgColor="E7EEF6")  # light blue for totals rows
TOTALS_FONT = Font(name="Arial", bold=True)

BASE_INVOICE_COLS = ["source_file", "vendor", "invoice_number", "invoice_date",
                     "po_number", "subtotal", "tax", "total"]
TAIL_INVOICE_COLS = ["confidence", "validation_ok", "validation_notes",
                     "rule_failures", "duplicate_note"]


def _extra_keys(invoices):
    """Union of all vendor-specific field names across the batch, order preserved."""
    keys = []
    for inv in invoices:
        for k in inv.extra:
            if k not in keys and not k.startswith("_"):
                keys.append(k)
    return keys


def _invoice_value(inv, col):
    if col in ("validation_ok",):
        return "OK" if inv.validation_ok else "CHECK"
    if col == "validation_notes":
        return "; ".join(inv.validation_notes)
    if col == "rule_failures":
        return "; ".join(getattr(inv, "rule_failures", []) or [])
    if col == "duplicate_note":
        return getattr(inv, "duplicate_note", "") or ""
    if col in inv.extra:
        return inv.extra[col]
    return getattr(inv, col, None)


def _style_header(ws, ncols):
    for c in range(1, ncols + 1):
        cell = ws.cell(row=1, column=c)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="left")


def _autosize(ws, ncols):
    for c in range(1, ncols + 1):
        letter = get_column_letter(c)
        longest = max(
            (len(str(ws.cell(row=r, column=c).value or "")) for r in range(1, ws.max_row + 1)),
            default=10,
        )
        ws.column_dimensions[letter].width = min(max(longest + 2, 10), 55)


def _line_columns(invoices):
    """Ordered union of all line-item column names across the batch (template order)."""
    keys = []
    for inv in invoices:
        for li in inv.line_items:
            for k in li.cols:
                if k not in keys:
                    keys.append(k)
    # description first if present
    if "description" in keys:
        keys.remove("description")
        keys.insert(0, "description")
    return keys


def to_excel(invoices: list[Invoice], path: str):
    wb = Workbook()
    invoice_cols = BASE_INVOICE_COLS + _extra_keys(invoices) + TAIL_INVOICE_COLS

    # Sheet 1: invoices
    ws = wb.active
    ws.title = "Invoices"
    ws.append([c.replace("_", " ").title() for c in invoice_cols])
    for inv in invoices:
        ws.append([_invoice_value(inv, c) for c in invoice_cols])
        if not inv.validation_ok:
            for c in range(1, len(invoice_cols) + 1):
                ws.cell(row=ws.max_row, column=c).fill = FLAG_FILL
    for r in range(2, ws.max_row + 1):
        for c in range(1, len(invoice_cols) + 1):
            ws.cell(row=r, column=c).font = BODY_FONT
    _style_header(ws, len(invoice_cols))
    _autosize(ws, len(invoice_cols))
    ws.freeze_panes = "A2"

    # Sheet 2: line items (columns come straight from the template, in order)
    ws2 = wb.create_sheet("Line Items")
    li_cols = _line_columns(invoices)
    line_cols = ["source_file", "invoice_number"] + li_cols
    ws2.append([c.replace("_", " ").title() for c in line_cols])
    label_col = "description" if "description" in li_cols else (li_cols[0] if li_cols else None)
    for inv in invoices:
        items = inv.line_items
        for li in items:
            base = {"source_file": inv.source_file, "invoice_number": inv.invoice_number}
            ws2.append([base.get(c, li.cols.get(c)) for c in line_cols])
        # a totals row that sums each numeric column across this invoice's lines
        if items:
            totals = _line_totals_row(inv, items, line_cols, label_col)
            ws2.append(totals)
            for c in range(1, len(line_cols) + 1):
                cellx = ws2.cell(row=ws2.max_row, column=c)
                cellx.font = TOTALS_FONT
                cellx.fill = TOTALS_FILL
    for r in range(2, ws2.max_row + 1):
        for c in range(1, len(line_cols) + 1):
            if ws2.cell(row=r, column=c).font != TOTALS_FONT:
                ws2.cell(row=r, column=c).font = BODY_FONT
    _style_header(ws2, len(line_cols))
    _autosize(ws2, len(line_cols))
    ws2.freeze_panes = "A2"

    # Sheet 3: reconciliation vs the original PDF (only if we have the data)
    if any(inv.reconciliation for inv in invoices):
        ws3 = wb.create_sheet("Reconciliation")
        cols = ["source_file", "status", "printed_total", "extracted_total",
                "printed_subtotal", "extracted_subtotal", "printed_tax", "extracted_tax",
                "line_items_sum", "n_line_items", "notes"]
        ws3.append([c.replace("_", " ").title() for c in cols])
        for inv in invoices:
            r = inv.reconciliation or {}
            ws3.append([inv.source_file] + [r.get(c) for c in cols[1:]])
            fill = TOTALS_FILL if r.get("status") == "OK" else FLAG_FILL
            for c in range(1, len(cols) + 1):
                cellx = ws3.cell(row=ws3.max_row, column=c)
                cellx.font = BODY_FONT
                cellx.fill = fill
        _style_header(ws3, len(cols))
        _autosize(ws3, len(cols))
        ws3.freeze_panes = "A2"

    wb.save(path)
    return path


def _line_totals_row(inv, items, line_cols, label_col):
    """Build a totals row summing only the meaningful (money) line-item columns."""
    summable = set(getattr(inv, "line_total_columns", []) or [])
    row = []
    for c in line_cols:
        if c == "invoice_number":
            row.append(inv.invoice_number)
        elif c == label_col:
            row.append("TOTAL")
        elif c in summable:
            nums = [li.cols.get(c) for li in items if isinstance(li.cols.get(c), (int, float))]
            row.append(round(sum(nums), 2) if nums else "")
        else:
            row.append("")
    return row


def to_csv(invoices: list[Invoice], folder: str):
    """Write invoices and line items to CSV files in the given folder.
    Utility export function. Not used by the Streamlit UI — available for
    programmatic/API use by external callers importing the extractor package.
    Returns (invoices_csv_path, line_items_csv_path).
    """  # FIX 17: docstring added — clarifies intentional keep, not dead code
    os.makedirs(folder, exist_ok=True)
    inv_path = os.path.join(folder, "invoices.csv")
    line_path = os.path.join(folder, "line_items.csv")
    invoice_cols = BASE_INVOICE_COLS + _extra_keys(invoices) + TAIL_INVOICE_COLS

    with open(inv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(invoice_cols)
        for inv in invoices:
            w.writerow([_invoice_value(inv, c) for c in invoice_cols])

    with open(line_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        li_cols = _line_columns(invoices)
        line_cols = ["source_file", "invoice_number"] + li_cols
        label_col = "description" if "description" in li_cols else (li_cols[0] if li_cols else None)
        w.writerow(line_cols)
        for inv in invoices:
            items = inv.line_items
            for li in items:
                base = {"source_file": inv.source_file, "invoice_number": inv.invoice_number}
                w.writerow([base.get(c, li.cols.get(c)) for c in line_cols])
            if items:
                w.writerow(_line_totals_row(inv, items, line_cols, label_col))
    return inv_path, line_path
