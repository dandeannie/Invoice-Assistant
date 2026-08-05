"""extractor/utils.py — shared numeric and text utilities."""
from datetime import datetime
import re as _re


def _num(val) -> float | None:
    """Parse a numeric value from int, float, or string.
    Strips currency symbols, commas, and whitespace before parsing.
    Returns None if the value cannot be converted.

    This is the canonical implementation shared across generic.py and reconcile.py.
    FIX 14: consolidated from two divergent local copies — see extractor/generic.py
    (full string-aware version) and extractor/reconcile.py (int/float-only version).
    """
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = _re.sub(r"[^0-9.\-]", "", str(val).replace(",", ""))
    try:
        return float(s) if s not in ("", "-", ".") else None
    except ValueError:
        return None


def _normalize_date(raw: str) -> str:
    """Normalize a date string to DD-MMM-YYYY format.
    Preserves the original string if parsing fails — never silently corrupts.
    """
    if not raw or not isinstance(raw, str):
        return raw
    raw = raw.strip()
    formats = [
        "%d-%b-%y",    # 20-Jul-26
        "%d-%b-%Y",    # 20-Jul-2026
        "%d/%m/%Y",    # 20/07/2026
        "%d/%m/%y",    # 20/07/26
        "%Y-%m-%d",    # 2026-07-20
        "%d-%m-%Y",    # 20-07-2026
        "%d-%m-%y",    # 20-07-26
        "%B %d, %Y",   # July 20, 2026
        "%d %B %Y",    # 20 July 2026
        "%d %b %Y",    # 20 Jul 2026
        "%b %d, %Y",   # Jul 20, 2026
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(raw, fmt)
            # Always output as DD-MMM-YYYY for consistency
            return dt.strftime("%d-%b-%Y")
        except ValueError:
            continue
    # If nothing matched, return original — never corrupt the date
    return raw
