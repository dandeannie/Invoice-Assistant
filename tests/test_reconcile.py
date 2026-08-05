"""Tests for reconcile() function and helpers in extractor/reconcile.py."""
from unittest.mock import patch
from extractor.models import Invoice, LineItem
from extractor.reconcile import reconcile, TOL


def test_perfect_match(sample_invoice):
    mock_lines = [
        "ACME Corp Invoice",
        "Subtotal: 100.00",
        "Tax: 18.00",
        "Grand Total: 118.00",
    ]
    with patch("extractor.reconcile._pdf_lines", return_value=mock_lines):
        res = reconcile(sample_invoice, "dummy.pdf")
        assert res["status"] == "OK"
        assert res["total_match"] is True
        assert res["subtotal_match"] is True


def test_within_tolerance():
    # Subtotal 100.00, Tax 18.00, Extracted Total 117.20 (diff 0.80 <= TOL 1.5)
    inv = Invoice(
        source_file="dummy.pdf",
        vendor="ACME",
        subtotal=100.00,
        tax=18.00,
        total=117.20,
        validation_ok=True,
    )
    mock_lines = ["Subtotal: 100.00", "Grand Total: 118.00"]
    with patch("extractor.reconcile._pdf_lines", return_value=mock_lines):
        res = reconcile(inv, "dummy.pdf")
        assert res["status"] == "OK"
        assert res["total_match"] is True


def test_math_mismatch(sample_invoice):
    mock_lines = ["Subtotal: 100.00", "Grand Total: 500.00"]
    with patch("extractor.reconcile._pdf_lines", return_value=mock_lines):
        res = reconcile(sample_invoice, "dummy.pdf")
        assert res["status"] == "REVIEW"
        assert res["total_match"] is False


def test_missing_printed_total(sample_invoice):
    mock_lines = ["No numbers here", "Just plain text"]
    with patch("extractor.reconcile._pdf_lines", return_value=mock_lines):
        res = reconcile(sample_invoice, "dummy.pdf")
        assert res["status"] == "REVIEW"
        assert res["printed_total"] is None


def test_ocr_used_guidance():
    """
    Note: For OCR-processed invoices, reconciliation is skipped upstream in
    app.py / pages/1_Extract_Any_Invoice.py using `if not getattr(inv, 'ocr_used', False):`.
    This test verifies that if reconcile() is called directly on an OCR invoice,
    it behaves normally according to printed lines.
    """
    inv = Invoice(
        source_file="scanned.pdf",
        vendor="Scanned Corp",
        subtotal=100.00,
        tax=18.00,
        total=118.00,
        ocr_used=True,
        validation_ok=True,
    )
    mock_lines = ["Subtotal: 100.00", "Grand Total: 118.00"]
    with patch("extractor.reconcile._pdf_lines", return_value=mock_lines):
        res = reconcile(inv, "scanned.pdf")
        assert res["status"] == "OK"
