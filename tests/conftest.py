"""Shared pytest fixtures for Invoice Extractor test suite."""
import pytest
from extractor.models import Invoice, LineItem


@pytest.fixture
def sample_invoice():
    """Fully populated invoice with realistic test data."""
    return Invoice(
        source_file="test_invoice.pdf",
        vendor="ACME Corporation",
        invoice_number="INV-1001",
        invoice_date="2026-06-01",
        po_number="PO-5501",
        subtotal=100.00,
        tax=18.00,
        total=118.00,
        line_items=[
            LineItem(cols={"description": "Widget A", "quantity": 2, "amount": 60.00}),
            LineItem(cols={"description": "Widget B", "quantity": 1, "amount": 40.00}),
        ],
    )


@pytest.fixture
def minimal_invoice():
    """Invoice with only the required Pydantic fields."""
    return Invoice(source_file="min.pdf", vendor="Test Vendor")
