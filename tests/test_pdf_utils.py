"""Tests for layout-aware table extraction in extractor/pdf_utils.py."""
from unittest.mock import MagicMock, patch
from extractor.pdf_utils import (
    _group_words_into_lines,
    _detect_header_row,
    _map_words_to_columns,
    _find_column_gaps,
    _assign_to_boundaries,
    _merge_multiline_rows,
    _fix_hsn_in_rows,
    _fix_exempt_rows,
    extract_table_with_columns,
    extract_financial_summary,
    HEADER_KEYWORDS,
)
from extractor.generic import _format_structured_rows, _format_financial_summary


def test_group_words_into_lines():
    words = [
        {"text": "Item", "top": 100, "x0": 10},
        {"text": "Qty", "top": 102, "x0": 100},
        {"text": "Rate", "top": 101, "x0": 200},
        {"text": "Widget A", "top": 120, "x0": 10},
        {"text": "2", "top": 121, "x0": 100},
    ]
    lines = _group_words_into_lines(words, y_tol=5)
    assert len(lines) == 2
    assert [w["text"] for w in lines[0]] == ["Item", "Qty", "Rate"]
    assert [w["text"] for w in lines[1]] == ["Widget A", "2"]


def test_detect_header_row():
    lines = [
        [{"text": "Invoice", "x0": 10}, {"text": "Details", "x0": 50}],
        [{"text": "Description", "x0": 10}, {"text": "Quantity", "x0": 150}, {"text": "Amount", "x0": 300}],
    ]
    row_idx, col_map = _detect_header_row(lines, HEADER_KEYWORDS)
    assert row_idx == 1
    assert "description" in col_map
    assert "quantity" in col_map
    assert "amount" in col_map


def test_map_words_to_columns():
    col_map = {"description": 10, "quantity": 150, "amount": 300}
    line = [
        {"text": "Steel", "x0": 10},
        {"text": "Bolts", "x0": 30},
        {"text": "5", "x0": 152},
        {"text": "250.00", "x0": 305},
    ]
    res = _map_words_to_columns(line, col_map)
    assert res["description"] == "Steel Bolts"
    assert res["quantity"] == "5"
    assert res["amount"] == "250.00"


def test_find_column_gaps():
    x_positions = [10, 15, 20, 150, 155, 300, 310]
    gaps = _find_column_gaps(x_positions, min_gap=20)
    assert len(gaps) == 3
    assert gaps == [10, 150, 300]


def test_assign_to_boundaries():
    boundaries = [10, 150, 300]
    line = [
        {"text": "Item", "x0": 12},
        {"text": "10", "x0": 155},
        {"text": "500", "x0": 302},
    ]
    res = _assign_to_boundaries(line, boundaries)
    assert res["col_0"] == "Item"
    assert res["col_1"] == "10"
    assert res["col_2"] == "500"


def test_format_structured_rows():
    rows = [
        {"description": "Item 1", "quantity": "2", "amount": "100"},
        {"description": "Item 2", "quantity": "1", "amount": "50"},
    ]
    formatted = _format_structured_rows(rows)
    assert "STRUCTURED TABLE" in formatted
    assert "description | quantity | amount" in formatted
    assert "Item 1 | 2 | 100" in formatted


def test_format_financial_summary():
    summary = {
        "subtotal": "1000.00",
        "cgst": "90.00",
        "sgst": "90.00",
        "grand_total": "1180.00",
    }
    formatted = _format_financial_summary(summary)
    assert "FINANCIAL SUMMARY" in formatted
    assert "Subtotal / Taxable Value: 1000.00" in formatted
    assert "CGST: 90.00" in formatted
    assert "Grand Total: 1180.00" in formatted


def test_extract_table_with_columns_multipage():
    """Mock a 2-page PDF where page 1 has header + 2 items, page 2 has 2 items (continuation)."""
    p1_words = [
        {"text": "Description", "top": 10, "x0": 10},
        {"text": "Amount", "top": 10, "x0": 200},
        {"text": "Widget 1", "top": 30, "x0": 10},
        {"text": "100.00", "top": 30, "x0": 200},
        {"text": "Widget 2", "top": 50, "x0": 10},
        {"text": "200.00", "top": 50, "x0": 200},
    ]
    p2_words = [
        {"text": "Widget 3", "top": 30, "x0": 10},
        {"text": "300.00", "top": 30, "x0": 200},
        {"text": "Widget 4", "top": 50, "x0": 10},
        {"text": "400.00", "top": 50, "x0": 200},
    ]

    mock_p1 = MagicMock()
    mock_p1.extract_words.return_value = p1_words

    mock_p2 = MagicMock()
    mock_p2.extract_words.return_value = p2_words

    mock_pdf = MagicMock()
    mock_pdf.pages = [mock_p1, mock_p2]

    with patch("pdfplumber.open", return_value=MagicMock(__enter__=MagicMock(return_value=mock_pdf))):
        rows = extract_table_with_columns("dummy.pdf")
        assert len(rows) == 4
        assert rows[0]["description"] == "Widget 1"
        assert rows[3]["description"] == "Widget 4"


def test_extract_financial_summary_parsing():
    """Mock a PDF page with a financial summary block."""
    words = [
        {"text": "Subtotal", "top": 100, "x0": 10},
        {"text": "₹", "top": 100, "x0": 150},
        {"text": "4,50,000.00", "top": 100, "x0": 180},
        {"text": "Total", "top": 120, "x0": 10},
        {"text": "Tax", "top": 120, "x0": 50},
        {"text": "₹", "top": 120, "x0": 150},
        {"text": "81,000.00", "top": 120, "x0": 180},
        {"text": "Grand", "top": 140, "x0": 10},
        {"text": "Total", "top": 140, "x0": 60},
        {"text": "₹", "top": 140, "x0": 150},
        {"text": "5,31,000.00", "top": 140, "x0": 180},
    ]
    mock_page = MagicMock()
    mock_page.extract_words.return_value = words

    mock_pdf = MagicMock()
    mock_pdf.pages = [mock_page]

    with patch("pdfplumber.open", return_value=MagicMock(__enter__=MagicMock(return_value=mock_pdf))):
        summary = extract_financial_summary("dummy.pdf")
        assert summary.get("subtotal") == "450000.00"
        assert summary.get("total_tax") == "81000.00"
        assert summary.get("grand_total") == "531000.00"


def test_merge_multiline_rows():
    rows = [
        {"description": "Enterprise Resource Planning", "quantity": "1", "rate": "5000", "amount": "5000"},
        {"description": "software licence", "quantity": "", "rate": "", "amount": ""},
        {"description": "annual subscription", "quantity": "", "rate": "", "amount": ""},
    ]
    merged = _merge_multiline_rows(rows)
    assert len(merged) == 1
    assert merged[0]["description"] == "Enterprise Resource Planning software licence annual subscription"


def test_fix_hsn_in_rows():
    rows = [
        {"description": "Item A", "hsn": "", "taxable_value": "84713010", "amount": "500"},
    ]
    fixed = _fix_hsn_in_rows(rows)
    assert fixed[0]["hsn"] == "84713010"
    assert fixed[0]["taxable_value"] == ""


def test_fix_exempt_rows():
    rows = [
        {"description": "Exempt Service", "cgst_rate": "18", "sgst_rate": "18"},
    ]
    fixed = _fix_exempt_rows(rows)
    assert fixed[0]["cgst_rate"] == "0"
    assert fixed[0]["sgst_rate"] == "0"
