"""Tests for validate() function in extractor/validate.py."""
from extractor.models import Invoice, LineItem
from extractor.validate import validate, TOLERANCE


def test_valid_invoice(sample_invoice):
    inv = validate(sample_invoice)
    assert inv.validation_ok is True
    assert len(inv.validation_notes) == 0
    assert inv.confidence == 1.0


def test_missing_invoice_number():
    inv = Invoice(
        source_file="test.pdf",
        vendor="ACME",
        invoice_date="2026-06-01",
        total=100.0,
    )
    inv = validate(inv)
    assert inv.validation_ok is False
    assert any("Missing invoice number" in note for note in inv.validation_notes)


def test_missing_total():
    inv = Invoice(
        source_file="test.pdf",
        vendor="ACME",
        invoice_number="INV-1",
        invoice_date="2026-06-01",
    )
    inv = validate(inv)
    assert inv.validation_ok is False
    assert any("Missing total" in note for note in inv.validation_notes)


def test_missing_invoice_date():
    inv = Invoice(
        source_file="test.pdf",
        vendor="ACME",
        invoice_number="INV-1",
        total=100.0,
    )
    inv = validate(inv)
    assert inv.validation_ok is False
    assert any("Missing invoice date" in note for note in inv.validation_notes)


def test_line_items_correct_sum():
    inv = Invoice(
        source_file="test.pdf",
        vendor="ACME",
        invoice_number="INV-1",
        invoice_date="2026-06-01",
        subtotal=100.0,
        tax=0.0,
        total=100.0,
        line_items=[
            LineItem(cols={"description": "Item 1", "amount": 60.0}),
            LineItem(cols={"description": "Item 2", "amount": 40.0}),
        ],
    )
    inv = validate(inv)
    assert inv.validation_ok is True


def test_line_items_wrong_sum():
    inv = Invoice(
        source_file="test.pdf",
        vendor="ACME",
        invoice_number="INV-1",
        invoice_date="2026-06-01",
        subtotal=100.0,
        tax=18.0,
        total=118.0,
        line_items=[
            LineItem(cols={"description": "Item 1", "amount": 50.0}),
            LineItem(cols={"description": "Item 2", "amount": 40.0}),  # Sums to 90.0, expected 100 or 118
        ],
    )
    inv = validate(inv)
    assert inv.validation_ok is False
    assert any("Line items sum to 90.00" in note for note in inv.validation_notes)


def test_empty_line_items():
    inv = Invoice(
        source_file="test.pdf",
        vendor="ACME",
        invoice_number="INV-1",
        invoice_date="2026-06-01",
        subtotal=100.0,
        tax=18.0,
        total=118.0,
        line_items=[],
    )
    inv = validate(inv)
    # Empty line_items doesn't trigger line item sum check error if subtotal+tax==total
    assert inv.validation_ok is True


def test_subtotal_plus_tax_mismatch():
    inv = Invoice(
        source_file="test.pdf",
        vendor="ACME",
        invoice_number="INV-1",
        invoice_date="2026-06-01",
        subtotal=100.0,
        tax=5.0,
        total=118.0,  # 100 + 5 != 118
    )
    inv = validate(inv)
    assert inv.validation_ok is False
    assert any("Subtotal 100.00 + tax 5.00 != total 118.00" in note for note in inv.validation_notes)


def test_tax_inference():
    inv = Invoice(
        source_file="test.pdf",
        vendor="ACME",
        invoice_number="INV-1",
        invoice_date="2026-06-01",
        subtotal=100.0,
        tax=None,
        total=118.0,
    )
    inv = validate(inv)
    assert inv.tax == 18.0
    assert inv.validation_ok is True


def test_confidence_decrements():
    # Missing all 3 key fields
    inv = Invoice(
        source_file="test.pdf",
        vendor="ACME",
    )
    inv = validate(inv)
    # score starts at 1.0, minus 3 * 0.15 = 0.55
    assert inv.confidence == 0.55
