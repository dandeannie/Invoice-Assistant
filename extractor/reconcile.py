"""
Reconcile extracted data against the ORIGINAL PDF.

The engine already checks a single invoice is internally consistent (subtotal + tax =
total, lines add up). This module adds an independent cross-check: it reads the totals
actually PRINTED on the PDF and compares them to what was extracted, so a missed line or
a misread figure is caught for human review.
"""
import re

import pdfplumber

from .utils import _num  # FIX 14: shared utility, replaces local int/float-only definition

TOL = 1.5  # rupees/dollars of slack for rounding differences


def _pdf_lines(pdf_path):
    out = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            txt = page.extract_text() or ""
            out.extend(l for l in txt.splitlines() if l.strip())
    return out


def _amounts(s):
    """All money-looking numbers on a line (require 2 decimals to avoid HSN/qty/years)."""
    return [float(m.replace(",", "")) for m in re.findall(r"\d[\d,]*\.\d{2}", s)]


def _labeled_amount(lines, labels, exclude=()):
    """Rightmost amount on the first line whose text contains one of `labels`
    (and none of `exclude`). Labels/excludes are matched case-insensitively."""
    for ln in lines:
        low = ln.lower()
        if any(x in low for x in exclude):
            continue
        if any(lb in low for lb in labels):
            amts = _amounts(ln)
            if amts:
                return amts[-1]
    return None


def _printed_total(lines):
    # try the most specific "final amount" labels first
    for labels in (["invoice total", "grand total", "total payable", "amount payable",
                    "total due", "net payable", "total amount", "balance due"],):
        v = _labeled_amount(lines, labels)
        if v is not None:
            return v
    # fall back to a bare "total" line, but not sub-total / tax / taxable lines
    return _labeled_amount(lines, ["total"],
                           exclude=["sub total", "subtotal", "taxable", "tax", "before"])


def _printed_subtotal(lines):
    return _labeled_amount(lines, ["sub total", "subtotal", "taxable value",
                                   "taxable amount", "total before tax", "amount before tax",
                                   "net amount", "net total", "total (excl"])


# FIX 14: _num() moved to extractor/utils.py — imported above


def reconcile(inv, pdf_path):
    """Compare the extracted invoice to the totals printed on its PDF.
    Returns a dict of checks and an overall PASS/REVIEW status."""
    lines = _pdf_lines(pdf_path)
    printed_total = _printed_total(lines)
    printed_sub = _printed_subtotal(lines)
    printed_tax = (round(printed_total - printed_sub, 2)
                   if printed_total is not None and printed_sub is not None else None)

    ex_total = _num(inv.total)
    ex_sub = _num(inv.subtotal)
    ex_tax = _num(inv.tax)
    line_sum = round(sum(li.amount for li in inv.line_items
                         if isinstance(li.amount, (int, float))), 2) if inv.line_items else None

    def cmp(a, b):
        if a is None or b is None:
            return None
        return abs(a - b) <= TOL

    def cmp_any(v, targets):
        ts = [t for t in targets if t is not None]
        if v is None or not ts:
            return None
        return any(abs(v - t) <= TOL for t in ts)

    # line amounts legitimately sum to EITHER the subtotal (tax added once at invoice
    # level) OR the grand total (tax included per line) - accept both
    lines_reconcile = cmp_any(line_sum, [printed_total, printed_sub])

    checks = {
        "printed_total": printed_total, "extracted_total": ex_total,
        "total_match": cmp(printed_total, ex_total),
        "printed_subtotal": printed_sub, "extracted_subtotal": ex_sub,
        "subtotal_match": cmp(printed_sub, ex_sub),
        "printed_tax": printed_tax, "extracted_tax": ex_tax,
        "tax_match": cmp(printed_tax, ex_tax),
        "line_items_sum": line_sum,
        "lines_reconcile": lines_reconcile,
        "n_line_items": len(inv.line_items),
        "internal_ok": bool(inv.validation_ok),
    }

    notes = []
    if printed_total is None:
        notes.append("couldn't find a printed grand total to compare against")
    if checks["total_match"] is False:
        notes.append(f"extracted total {ex_total} != printed {printed_total} "
                     f"(diff {round((ex_total or 0) - (printed_total or 0), 2)})")
    if checks["subtotal_match"] is False:
        notes.append(f"extracted subtotal {ex_sub} != printed {printed_sub}")
    if lines_reconcile is False and line_sum is not None:
        notes.append(f"sum of line totals {line_sum} matches neither printed subtotal "
                     f"({printed_sub}) nor total ({printed_total}) - a line may be "
                     "missing or misread")
    if not inv.validation_ok:
        notes.append("failed internal arithmetic check")

    hard_fail = any(checks[k] is False for k in
                    ("total_match", "subtotal_match", "lines_reconcile"))
    checks["status"] = "OK" if (printed_total is not None and not hard_fail
                                and inv.validation_ok) else "REVIEW"
    checks["notes"] = "; ".join(notes)
    return checks
