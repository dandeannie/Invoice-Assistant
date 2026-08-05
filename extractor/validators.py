"""
Validation utilities for invoice fields and line item math consistency.
"""
from __future__ import annotations
import re


def validate_invoice_number(value: str) -> tuple[str, float]:
    """
    Validate and score an extracted invoice number.
    Returns (cleaned_value, confidence_score 0.0-1.0).

    Low confidence triggers are:
    - Purely numeric and 10+ digits (likely a phone number)
    - Contains only digits and is < 3 chars (too short)
    - Matches date patterns or non-invoice label strings
    """
    if not value:
        return value, 0.0

    cleaned = value.strip()

    # Reject phone-number-like values
    phone_re = re.compile(r'^[6-9]\d{9,}$')
    if phone_re.match(cleaned.replace(' ', '')):
        return cleaned, 0.1  # very low confidence

    # Reject very short pure numbers
    if re.match(r'^\d{1,2}$', cleaned):
        return cleaned, 0.2

    # Reject if value looks like a date (DD-Mon-YY, DD/MM/YYYY etc.)
    date_re = re.compile(
        r'^\d{1,2}[-/]\d{1,2}[-/]\d{2,4}$'
        r'|^\d{1,2}[-/][A-Za-z]{3}[-/]\d{2,4}$'
    )
    if date_re.match(cleaned):
        return cleaned, 0.05  # almost certainly wrong

    # Reject if value is a single word with no digits (grabbed a label)
    if re.match(r'^[A-Za-z\s]+$', cleaned) and len(cleaned) < 20:
        return cleaned, 0.1

    # Pure numeric but reasonable length (3-9 digits)
    if re.match(r'^\d{3,9}$', cleaned):
        return cleaned, 0.75

    # Good patterns: alphanumeric with separators
    good_re = re.compile(r'^[A-Za-z0-9][A-Za-z0-9/_\-]{2,}$')
    if good_re.match(cleaned):
        return cleaned, 0.95

    return cleaned, 0.6


def validate_po_number(value: str) -> tuple[str, float]:
    """
    Validate an extracted PO number.
    Returns (cleaned_value, confidence_score 0.0-1.0).
    """
    if not value:
        return value, 0.0

    cleaned = value.strip()

    # Reject known bad values that are actually labels
    BAD_VALUES = {
        'dated', 'date', 'tel', 'telno', 'tel no', 'phone', 'mobile',
        'reference', 'ref', 'gstin', 'pan', 'cin', 'challan',
        'receiver', 'buyer', 'vendor', 'supplier', 'party',
    }
    if cleaned.lower() in BAD_VALUES:
        return cleaned, 0.05

    # Reject single-word all-alpha values under 5 chars (likely a label)
    if re.match(r'^[A-Za-z]{1,4}$', cleaned):
        return cleaned, 0.1

    # Reject date-like values
    date_re = re.compile(
        r'^\d{1,2}[-/]\d{1,2}[-/]\d{2,4}$'
        r'|^\d{1,2}[-/][A-Za-z]{3}[-/]\d{2,4}$'
    )
    if date_re.match(cleaned):
        return cleaned, 0.05

    # Good: alphanumeric with separators
    if re.match(r'^[A-Za-z0-9][A-Za-z0-9/_\-\s]{1,}$', cleaned):
        return cleaned, 0.9

    return cleaned, 0.6


def validate_line_items(rows: list[dict]) -> list[dict]:
    """
    Validate Qty × Rate ≈ Taxable Value for each line item row.

    Tolerance: 2% (handles rounding differences).

    For each row where qty, rate, and taxable_value are all present:
      - Compute expected = qty * rate
      - If abs(expected - taxable_value) / taxable_value > 0.02:
          mark row with _math_mismatch = True

    Returns the same rows with _math_mismatch flags added where needed.
    """
    def _parse_num(val: str) -> float | None:
        if not val:
            return None
        cleaned = re.sub(r'[^\d.]', '', str(val))
        try:
            return float(cleaned)
        except ValueError:
            return None

    result = []
    for row in rows:
        row = dict(row)
        qty = _parse_num(row.get('quantity', ''))
        rate = _parse_num(row.get('rate', ''))
        taxable = _parse_num(row.get('taxable_value', ''))

        if qty is not None and rate is not None and taxable is not None:
            if taxable > 0:
                expected = qty * rate
                deviation = abs(expected - taxable) / taxable
                if deviation > 0.02:
                    row['_math_mismatch'] = True

        result.append(row)
    return result
