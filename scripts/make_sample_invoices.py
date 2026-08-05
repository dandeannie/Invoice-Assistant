# Moved to scripts/ — FIX 15: keep repo root clean
"""
Generates sample NATIVE (text-based) PDF invoices for two fictional vendors,
each with a different layout. These are only for testing the extractor.
Run:  python scripts/make_sample_invoices.py
"""
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
import os

OUT = os.path.join(os.path.dirname(__file__), "..", "sample_invoices")
os.makedirs(OUT, exist_ok=True)


def acme_invoice(path, number, date, po, rows):
    c = canvas.Canvas(path, pagesize=A4)
    w, h = A4
    c.setFont("Helvetica-Bold", 18)
    c.drawString(20 * mm, h - 25 * mm, "ACME Corporation")
    c.setFont("Helvetica", 9)
    c.drawString(20 * mm, h - 31 * mm, "123 Industrial Way, Springfield")

    c.setFont("Helvetica", 10)
    y = h - 45 * mm
    c.drawString(20 * mm, y, f"Invoice Number: {number}")
    c.drawString(120 * mm, y, f"Invoice Date: {date}")
    c.drawString(20 * mm, y - 6 * mm, f"PO Number: {po}")

    # Table header
    ty = h - 65 * mm
    c.setFont("Helvetica-Bold", 10)
    c.drawString(20 * mm, ty, "Description")
    c.drawString(110 * mm, ty, "Quantity")
    c.drawString(140 * mm, ty, "Unit Price")
    c.drawString(175 * mm, ty, "Amount")
    c.line(20 * mm, ty - 2 * mm, 195 * mm, ty - 2 * mm)

    c.setFont("Helvetica", 10)
    ry = ty - 9 * mm
    subtotal = 0.0
    for desc, qty, price in rows:
        amount = qty * price
        subtotal += amount
        c.drawString(20 * mm, ry, desc)
        c.drawString(110 * mm, ry, str(qty))
        c.drawString(140 * mm, ry, f"{price:,.2f}")
        c.drawString(175 * mm, ry, f"{amount:,.2f}")
        ry -= 7 * mm

    tax = round(subtotal * 0.10, 2)
    total = round(subtotal + tax, 2)
    c.setFont("Helvetica", 10)
    c.drawString(140 * mm, ry - 4 * mm, "Subtotal:")
    c.drawString(175 * mm, ry - 4 * mm, f"{subtotal:,.2f}")
    c.drawString(140 * mm, ry - 10 * mm, "Tax:")
    c.drawString(175 * mm, ry - 10 * mm, f"{tax:,.2f}")
    c.setFont("Helvetica-Bold", 10)
    c.drawString(140 * mm, ry - 16 * mm, "Total Due:")
    c.drawString(175 * mm, ry - 16 * mm, f"{total:,.2f}")
    c.save()


def globex_invoice(path, number, date, po, rows):
    # Different layout / different labels to prove the template idea
    c = canvas.Canvas(path, pagesize=A4)
    w, h = A4
    c.setFont("Helvetica-Bold", 20)
    c.drawString(20 * mm, h - 22 * mm, "GLOBEX LTD")
    c.setFont("Helvetica", 9)
    c.drawString(20 * mm, h - 28 * mm, "Global Exports Division")

    c.setFont("Helvetica", 10)
    # Labels stacked on the right side
    c.drawString(130 * mm, h - 40 * mm, f"Bill No.: {number}")
    c.drawString(130 * mm, h - 46 * mm, f"Dated: {date}")
    c.drawString(130 * mm, h - 52 * mm, f"Order Ref: {po}")

    ty = h - 68 * mm
    c.setFont("Helvetica-Bold", 10)
    c.drawString(20 * mm, ty, "Item")
    c.drawString(120 * mm, ty, "Qty")
    c.drawString(145 * mm, ty, "Rate")
    c.drawString(175 * mm, ty, "Value")
    c.line(20 * mm, ty - 2 * mm, 195 * mm, ty - 2 * mm)

    c.setFont("Helvetica", 10)
    ry = ty - 9 * mm
    subtotal = 0.0
    for desc, qty, price in rows:
        amount = qty * price
        subtotal += amount
        c.drawString(20 * mm, ry, desc)
        c.drawString(120 * mm, ry, str(qty))
        c.drawString(145 * mm, ry, f"{price:,.2f}")
        c.drawString(175 * mm, ry, f"{amount:,.2f}")
        ry -= 7 * mm

    tax = round(subtotal * 0.18, 2)  # different tax rate
    total = round(subtotal + tax, 2)
    c.setFont("Helvetica", 10)
    c.drawString(145 * mm, ry - 4 * mm, "Net Amount:")
    c.drawString(175 * mm, ry - 4 * mm, f"{subtotal:,.2f}")
    c.drawString(145 * mm, ry - 10 * mm, "GST:")
    c.drawString(175 * mm, ry - 10 * mm, f"{tax:,.2f}")
    c.setFont("Helvetica-Bold", 10)
    c.drawString(145 * mm, ry - 16 * mm, "Grand Total:")
    c.drawString(175 * mm, ry - 16 * mm, f"{total:,.2f}")
    c.save()


# Two ACME invoices
acme_invoice(
    os.path.join(OUT, "acme_001.pdf"), "INV-1001", "2026-06-01", "PO-5501",
    [("Steel bolts M8", 100, 0.45), ("Hex nuts M8", 100, 0.20), ("Washers", 200, 0.08)],
)
acme_invoice(
    os.path.join(OUT, "acme_002.pdf"), "INV-1002", "2026-06-15", "PO-5522",
    [("Aluminium sheet 2mm", 5, 42.00), ("Copper wire 10m", 12, 8.50)],
)
# One GLOBEX invoice (different vendor / layout)
globex_invoice(
    os.path.join(OUT, "globex_001.pdf"), "GBX-77", "15/06/2026", "ORD-990",
    [("Consulting hours", 20, 75.00), ("Travel reimbursement", 1, 340.00)],
)

print("Created sample invoices in:", OUT)
for f in sorted(os.listdir(OUT)):
    print(" -", f)
