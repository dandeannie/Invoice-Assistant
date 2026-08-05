"""Tests for extractor/validators.py (Fix 11, 15, 16, 17)."""
from extractor.validators import validate_invoice_number, validate_po_number, validate_line_items


def test_validate_invoice_number():
    # Phone number rejection
    val, conf = validate_invoice_number("9876543210")
    assert conf == 0.1

    # Very short pure number
    val, conf = validate_invoice_number("42")
    assert conf == 0.2

    # Date rejection
    val, conf = validate_invoice_number("20-07-2024")
    assert conf == 0.05

    # Label word rejection
    val, conf = validate_invoice_number("Invoice")
    assert conf == 0.1

    # Good alphanumeric with separators
    val, conf = validate_invoice_number("INV-2024-001")
    assert conf == 0.95
    assert val == "INV-2024-001"

    # Good alphanumeric slash
    val, conf = validate_invoice_number("AE/4081/2627")
    assert conf == 0.95

    # Pure numeric reasonable length
    val, conf = validate_invoice_number("123456")
    assert conf == 0.75

    # Empty value
    val, conf = validate_invoice_number("")
    assert conf == 0.0


def test_validate_po_number():
    # Bad values (adjacent labels)
    val, conf = validate_po_number("Dated")
    assert conf == 0.05

    val, conf = validate_po_number("Tel No")
    assert conf == 0.05

    # Short alpha word
    val, conf = validate_po_number("Date")
    assert conf == 0.05

    # Date-like PO
    val, conf = validate_po_number("15/08/2024")
    assert conf == 0.05

    # Valid PO
    val, conf = validate_po_number("PO-99812")
    assert conf == 0.9

    # Empty PO
    val, conf = validate_po_number("")
    assert conf == 0.0


def test_validate_line_items_math():
    rows = [
        {"description": "Item 1", "quantity": "2", "rate": "100", "taxable_value": "200"},
        {"description": "Item 2", "quantity": "3", "rate": "50", "taxable_value": "300"},  # Mismatch: 3*50 = 150 != 300
    ]
    res = validate_line_items(rows)
    assert not res[0].get("_math_mismatch")
    assert res[1].get("_math_mismatch") is True
