"""Tests for extractor/utils.py utilities (beyond _num())."""
from extractor.utils import _normalize_date


def test_normalize_date_formats():
    assert _normalize_date("20-Jul-26") == "20-Jul-2026"
    assert _normalize_date("20-Jul-2026") == "20-Jul-2026"
    assert _normalize_date("20/07/2026") == "20-Jul-2026"
    assert _normalize_date("20/07/26") == "20-Jul-2026"
    assert _normalize_date("2026-07-20") == "20-Jul-2026"
    assert _normalize_date("20-07-2026") == "20-Jul-2026"
    assert _normalize_date("20-07-26") == "20-Jul-2026"
    assert _normalize_date("July 20, 2026") == "20-Jul-2026"
    assert _normalize_date("20 July 2026") == "20-Jul-2026"


def test_normalize_date_invalid():
    # If parsing fails, original string should be preserved
    assert _normalize_date("InvalidDateString") == "InvalidDateString"
    assert _normalize_date(None) is None
    assert _normalize_date("") == ""
