"""Tests for generic extractor post-processing functions in extractor/generic.py."""
from extractor.generic import (
    invoice_from_data,
    _fallback_fields,
    _is_summary_row,
    _strip_ocr_markers,
    _has_math_failure,
    _score,
)
from extractor.models import Invoice, LineItem


def test_gst_summation_post_processing():
    data = {
        "vendor": "Test Vendor",
        "invoice_number": "INV-100",
        "invoice_date": "20-Jul-26",
        "subtotal": 1000.0,
        "cgst": 90.0,
        "sgst": 90.0,
        "igst": None,
        "total": 1180.0,
    }
    inv = invoice_from_data(data, "test.pdf")
    assert inv.cgst == 90.0
    assert inv.sgst == 90.0
    assert inv.tax == 180.0  # CGST + SGST summed correctly into tax


def test_po_number_fallback():
    inv = Invoice(source_file="test.pdf", vendor="ACME")
    text = "INVOICE\nInvoice No: INV-999\nPurchase Order No: PO-887766\nTotal: 500"
    inv = _fallback_fields(inv, text)
    assert inv.po_number == "PO-887766"


def test_date_normalization_fallback():
    inv = Invoice(source_file="test.pdf", vendor="ACME", invoice_date="20-Jul-26")
    inv = _fallback_fields(inv, "Invoice Date: 20-Jul-26")
    assert inv.invoice_date == "20-Jul-2026"


def test_is_summary_row():
    # Summary items should be filtered
    assert _is_summary_row(LineItem(cols={"description": "SUBTOTAL"})) is True
    assert _is_summary_row(LineItem(cols={"description": "Grand Total"})) is True
    assert _is_summary_row(LineItem(cols={"description": "Round Off"})) is True
    assert _is_summary_row(LineItem(cols={"description": "CGST 9%"})) is True
    assert _is_summary_row(LineItem(cols={"description": "Freight Charges"})) is True
    assert _is_summary_row(LineItem(cols={"description": ""})) is True

    # Real item should pass
    assert _is_summary_row(LineItem(cols={"description": "Steel Bolts M8"})) is False


def test_strip_ocr_markers():
    assert _strip_ocr_markers("[?ACME Corp?]") == "ACME Corp"
    assert _strip_ocr_markers("[??INV-1001??]") == "INV-1001"
    assert _strip_ocr_markers("Clean Text") == "Clean Text"
    assert _strip_ocr_markers(123) == 123


def test_has_math_failure():
    inv_ok = Invoice(source_file="t.pdf", vendor="A", validation_ok=True)
    assert _has_math_failure(inv_ok) is False

    inv_fail = Invoice(
        source_file="t.pdf",
        vendor="A",
        validation_ok=False,
        validation_notes=["Subtotal 100 + tax 5 != total 118"],
    )
    assert _has_math_failure(inv_fail) is True


def test_score():
    inv1 = Invoice(source_file="t.pdf", vendor="A", validation_ok=True, total=100.0, subtotal=90.0, tax=10.0)
    inv2 = Invoice(source_file="t.pdf", vendor="A", validation_ok=False, validation_notes=["Subtotal mismatch"])
    assert _score(inv1) > _score(inv2)
