"""Tests for shared _num() utility in extractor/utils.py."""
from extractor.utils import _num


def test_none():
    assert _num(None) is None


def test_int():
    res = _num(42)
    assert res == 42.0
    assert isinstance(res, float)


def test_float():
    res = _num(3.14)
    assert res == 3.14
    assert isinstance(res, float)


def test_string_int():
    assert _num("42") == 42.0


def test_string_float():
    assert _num("3.14") == 3.14


def test_comma_formatted():
    assert _num("1,234.56") == 1234.56


def test_currency_string():
    assert _num("$1,234.56") == 1234.56


def test_spaces():
    assert _num("  99.5  ") == 99.5


def test_negative_string():
    assert _num("-42.5") == -42.5


def test_empty_string():
    assert _num("") is None


def test_non_numeric():
    assert _num("abc") is None


def test_mixed_prefix():
    assert _num("abc123") == 123.0


def test_dash_only():
    assert _num("-") is None


def test_dot_only():
    assert _num(".") is None


def test_bool_true():
    assert _num(True) == 1.0


def test_large_float():
    assert _num(1234567.89) == 1234567.89
