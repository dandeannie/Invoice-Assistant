"""
Validation. This is what turns raw extraction into TRUSTWORTHY extraction.
We check the maths: do the line items add up to the subtotal? Does subtotal + tax
equal the total? Anything that doesn't reconcile gets flagged so a human can glance
at it instead of the wrong number silently ending up in your spreadsheet.
"""
from __future__ import annotations
from .models import Invoice

TOLERANCE = 0.02  # allow 2 cents of rounding difference


def validate(inv: Invoice) -> Invoice:
    notes = []
    score = 1.0

    # If the invoice shows a subtotal and a total but no separate tax line, the tax is
    # simply the difference (often zero on tax-free receipts).
    if inv.tax is None and inv.subtotal is not None and inv.total is not None:
        inv.tax = round(inv.total - inv.subtotal, 2)

    # Which key fields did we manage to read?
    for field in ("invoice_number", "invoice_date", "total"):
        if getattr(inv, field) in (None, ""):
            notes.append(f"Missing {field.replace('_', ' ')}")
            score -= 0.15

    # Do the line items add up? Depending on the vendor, line amounts may be pre-tax
    # (sum to the subtotal) or tax-inclusive (sum to the total). Accept either.
    line_sum = sum(li.amount for li in inv.line_items if li.amount is not None)
    if inv.line_items:
        targets = [t for t in (inv.subtotal, inv.total) if t is not None]
        if targets and not any(abs(line_sum - t) <= TOLERANCE for t in targets):
            shown = " / ".join(f"{t:.2f}" for t in targets)
            notes.append(f"Line items sum to {line_sum:.2f}, expected {shown}")
            score -= 0.25

    # Does subtotal + tax equal the total?
    if inv.subtotal is not None and inv.total is not None:
        tax = inv.tax or 0.0
        if abs((inv.subtotal + tax) - inv.total) > TOLERANCE:
            notes.append(
                f"Subtotal {inv.subtotal:.2f} + tax {tax:.2f} != total {inv.total:.2f}"
            )
            score -= 0.25

    inv.validation_notes = notes
    inv.validation_ok = len(notes) == 0
    inv.confidence = round(max(0.0, score), 2)
    return inv
