"""
Shared PDF utility functions for text extraction using pdfplumber.
Prevents circular dependencies between generic.py and ocr.py.
"""
from __future__ import annotations
import contextlib
import re
import pdfplumber

@contextlib.contextmanager
def _open_pdf(pdf_path: str, pdf_doc=None):
    if pdf_doc is not None:
        yield pdf_doc
    else:
        with pdfplumber.open(pdf_path) as pdf:
            yield pdf

_TABLE_SETTINGS = {
    "vertical_strategy": "lines",
    "horizontal_strategy": "lines",
    "snap_tolerance": 3,
    "join_tolerance": 3,
    "edge_min_length": 10,
    "min_words_vertical": 1,
    "min_words_horizontal": 1,
    "keep_blank_chars": False,
    "text_tolerance": 3,
    "text_x_tolerance": 3,
    "text_y_tolerance": 3,
    "intersection_tolerance": 3,
}


def _pdf_text(pdf_path: str, pdf_doc=None) -> str:
    """Extract both structured tables (as clean Markdown) and layout text from all
    pages so the model gets explicit visibility over line-item tables and numbers."""
    parts = []
    with _open_pdf(pdf_path, pdf_doc) as pdf:
        for p_idx, page in enumerate(pdf.pages, start=1):
            parts.append(f"--- PAGE {p_idx} ---")

            try:
                tables = page.extract_tables(_TABLE_SETTINGS)
                if not tables:
                    tables = page.extract_tables({
                        "vertical_strategy": "text",
                        "horizontal_strategy": "lines",
                        "snap_tolerance": 3,
                    })
                if not tables:
                    tables = page.extract_tables()

                if tables:
                    parts.append("=== STRUCTURED TABLES ===")
                    for t_idx, table in enumerate(tables, start=1):
                        parts.append(f"[Table {t_idx}]")
                        for row in table:
                            if row and any(cell and str(cell).strip() for cell in row):
                                clean_row = [str(cell or "").replace("\n", " ").strip() for cell in row]
                                parts.append(" | ".join(clean_row))
                    parts.append("")
            except Exception:
                pass

            parts.append("=== RAW PAGE TEXT ===")
            try:
                txt = page.extract_text(layout=True) or ""
            except Exception:
                txt = page.extract_text() or ""
            parts.append(txt)

    return "\n".join(parts)


HEADER_KEYWORDS = {
    'description': ['description', 'particulars', 'item', 'product',
                    'goods', 'details', 'name', 'narration'],
    'hsn':         ['hsn', 'sac', 'hsn/sac', 'hsn code'],
    'quantity':    ['qty', 'quantity', 'nos', 'pcs', 'units', 'qnty'],
    'unit':        ['unit', 'uom', 'u/m'],
    'rate':        ['rate', 'price', 'unit price', 'unit rate', 'mrp'],
    'discount':    ['discount', 'disc', 'disc%', 'discount%'],
    'taxable_value': ['taxable', 'taxable value', 'assessable',
                      'basic amount'],
    'cgst_rate':   ['cgst%', 'cgst rate'],
    'sgst_rate':   ['sgst%', 'sgst rate'],
    'igst_rate':   ['igst%', 'igst rate'],
    'amount':      ['amount', 'total', 'value', 'line total',
                    'net amount', 'total amount'],
}

SUMMARY_SKIP = re.compile(
    r'^\s*(total|grand total|subtotal|sub total|taxable value|'
    r'cgst|sgst|igst|gst|vat|round off|discount|freight|'
    r'amount in words|rupees|rs\.?)\b',
    re.IGNORECASE
)


def extract_table_with_columns(pdf_path: str, pdf_doc=None) -> list[dict]:
    """
    Extract line item rows from a PDF using X-coordinate column detection.

    Strategy:
    1. Find the table header row by looking for known column header keywords
    2. Record the X-coordinate (x0) of each header cell
    3. For each subsequent row, assign cell values to the nearest header column
    4. Carry column map forward across multi-page tables when page 2+ lacks a header
    5. Return list of dicts: {column_name: value, ...}

    This preserves column relationships that pdfplumber loses in plain text mode.
    """
    rows_out = []
    carried_col_map = {}

    try:
        with _open_pdf(pdf_path, pdf_doc) as pdf:
            for page in pdf.pages:
                words = page.extract_words(
                    x_tolerance=5,
                    y_tolerance=5,
                    keep_blank_chars=False,
                    use_text_flow=False,
                )
                if not words:
                    continue

                # Group words into lines by Y coordinate (within 5px tolerance)
                lines = _group_words_into_lines(words, y_tol=5)

                # Find header row — line where most words match header keywords
                header_row_idx, col_map = _detect_header_row(
                    lines, HEADER_KEYWORDS
                )

                if col_map:
                    carried_col_map = col_map
                    start_idx = header_row_idx + 1
                elif carried_col_map:
                    col_map = carried_col_map
                    start_idx = 0
                else:
                    continue  # no header found yet, skip page

                # Extract data rows after header (or from top on continuation pages)
                for line in lines[start_idx:]:
                    # Skip summary rows
                    line_text = ' '.join(w['text'] for w in line)
                    if SUMMARY_SKIP.match(line_text.strip()):
                        continue

                    # Map each word to nearest column by X position
                    row_dict = _map_words_to_columns(line, col_map)

                    # Skip rows with no description
                    if not row_dict.get('description', '').strip():
                        continue

                    rows_out.append(row_dict)

    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(
            "extract_table_with_columns failed: %s", e
        )

    if not rows_out:
        rows_out = extract_table_by_column_position(pdf_path, pdf_doc=pdf_doc)

    rows_out = _merge_multiline_rows(rows_out)
    rows_out = _fix_hsn_in_rows(rows_out)
    rows_out = _fix_exempt_rows(rows_out)
    return rows_out


def _merge_multiline_rows(rows: list[dict]) -> list[dict]:
    """
    Merge rows where description is a continuation of the previous row.

    A row is a continuation if:
    - Its description is non-empty text
    - All numeric fields (quantity, rate, amount, taxable_value) are empty
    - The previous row has a non-empty description

    In that case, append this row's description to the previous row's
    description with a space separator.
    """
    if not rows:
        return rows

    NUMERIC_FIELDS = {'quantity', 'rate', 'amount', 'taxable_value',
                      'cgst_rate', 'sgst_rate', 'igst_rate', 'discount'}

    merged = []
    for row in rows:
        desc = row.get('description', '').strip()
        numeric_vals = [row.get(f, '').strip() for f in NUMERIC_FIELDS]
        all_numeric_empty = all(not v for v in numeric_vals)

        if merged and desc and all_numeric_empty:
            # Continuation row — append description to previous
            merged[-1]['description'] = (
                merged[-1].get('description', '') + ' ' + desc
            ).strip()
        else:
            merged.append(dict(row))

    return merged


def _fix_hsn_in_rows(rows: list[dict]) -> list[dict]:
    """
    Post-process extracted rows to rescue HSN codes that landed in the
    wrong column.

    Strategy:
    - If 'hsn' field is empty, scan all other fields for a 4-8 digit
      pure-numeric value that looks like an HSN code.
    - If found, move it to 'hsn' field.
    - Don't move values that are in 'quantity' (usually 1-3 digits).
    """
    HSN_RE = re.compile(r'^\d{4,8}$')
    SKIP_FIELDS = {
        'quantity', 'description', 'rate', 'unit_price', 'amount',
        'total', 'cgst', 'sgst', 'igst',
        'total_amount', 'net_amount', 'gross_amount', 'tax_amount'
    }

    fixed = []
    for row in rows:
        row = dict(row)
        if not row.get('hsn', '').strip():
            for field in list(row.keys()):
                if field in SKIP_FIELDS:
                    continue
                val = row.get(field, '').strip()
                if HSN_RE.match(val):
                    row['hsn'] = val
                    row[field] = ''  # clear from wrong column
                    break
        fixed.append(row)
    return fixed


def _fix_exempt_rows(rows: list[dict]) -> list[dict]:
    """
    Post-process rows to set GST = 0 for exempt/nil-rated items.
    """
    EXEMPT_RE = re.compile(
        r'\b(exempt|nil|nil\s?rated|0\s?%|zero\s?rated)\b',
        re.IGNORECASE
    )
    TAX_FIELDS = {'cgst_rate', 'sgst_rate', 'igst_rate',
                  'cgst_amount', 'sgst_amount', 'igst_amount'}

    fixed = []
    for row in rows:
        row = dict(row)
        row_text = ' '.join(str(v) for v in row.values())
        if EXEMPT_RE.search(row_text):
            for f in TAX_FIELDS:
                if f in row:
                    row[f] = '0'
        fixed.append(row)
    return fixed


def extract_financial_summary(pdf_path: str, pdf_doc=None) -> dict:
    """
    Extract the financial summary block from an invoice PDF.

    Looks for labelled rows near the bottom of the document that match
    known summary keywords. Returns a dict of canonical field -> value.

    Returns: {
        'subtotal': str,
        'cgst': str,
        'sgst': str,
        'igst': str,
        'total_tax': str,
        'round_off': str,
        'grand_total': str,
        'discount': str,
    }
    """
    SUMMARY_LABELS = {
        'subtotal': [
            'subtotal', 'sub total', 'taxable value', 'taxable amount',
            'assessable value', 'basic amount', 'total before tax',
        ],
        'cgst': ['cgst', 'central gst', 'central tax'],
        'sgst': ['sgst', 'state gst', 'state tax', 'utgst'],
        'igst': ['igst', 'integrated gst', 'integrated tax'],
        'total_tax': ['total tax', 'tax amount', 'total gst', 'gst amount'],
        'round_off': ['round off', 'rounding', 'round-off'],
        'grand_total': [
            'grand total', 'total amount', 'net amount', 'invoice total',
            'amount payable', 'total payable', 'net payable',
        ],
        'discount': ['discount', 'total discount', 'less discount'],
    }

    # Regex: extract numeric value from a line (handles ₹, commas, decimals)
    VALUE_RE = re.compile(r'[\d,]+\.?\d*')

    result = {}

    try:
        with _open_pdf(pdf_path, pdf_doc) as pdf:
            # Focus on last 2 pages where summary usually appears
            pages_to_check = pdf.pages[-2:] if len(pdf.pages) > 1 else pdf.pages

            for page in pages_to_check:
                words = page.extract_words(
                    x_tolerance=5, y_tolerance=5,
                    keep_blank_chars=False, use_text_flow=False,
                )
                if not words:
                    continue

                lines = _group_words_into_lines(words, y_tol=5)

                for line in lines:
                    line_text = ' '.join(w['text'] for w in line).strip()
                    line_lower = line_text.lower()

                    for field, aliases in SUMMARY_LABELS.items():
                        if field in result:
                            continue  # already found, don't overwrite
                        for alias in aliases:
                            if alias in line_lower:
                                # Extract rightmost number on this line
                                numbers = VALUE_RE.findall(line_text)
                                if numbers:
                                    # Remove commas, take last number
                                    val = numbers[-1].replace(',', '')
                                    result[field] = val
                                break

    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(
            "extract_financial_summary failed: %s", e
        )

    return result


def group_words_into_lines(words: list[dict], y_tolerance: float = 3.0) -> list[list[dict]]:
    """Canonical word-to-line grouper. Sort words by top-y then x0, cluster by y_tolerance."""
    if not words:
        return []
    sorted_words = sorted(words, key=lambda w: (round(w["top"] / y_tolerance), w["x0"]))
    lines: list[list[dict]] = []
    current_line: list[dict] = []
    last_y = None
    for word in sorted_words:
        y = round(word["top"] / y_tolerance)
        if last_y is None or y == last_y:
            current_line.append(word)
        else:
            lines.append(current_line)
            current_line = [word]
        last_y = y
    if current_line:
        lines.append(current_line)
    return lines


def _group_words_into_lines(words: list[dict], y_tol: float = 3.0) -> list[list[dict]]:
    """Legacy internal wrapper mapping y_tol parameter to y_tolerance."""
    return group_words_into_lines(words, y_tolerance=y_tol)


def _detect_header_row(
    lines: list[list], header_keywords: dict
) -> tuple[int | None, dict]:
    """
    Find the table header row and return (row_index, col_map).
    col_map = {canonical_col_name: x0_coordinate}
    """
    best_idx = None
    best_map = {}
    best_score = 0

    for idx, line in enumerate(lines):
        col_map = {}
        score = 0
        for word in line:
            text = word['text'].strip().lower()
            for canonical, aliases in header_keywords.items():
                if any(text == alias or text.startswith(alias)
                       for alias in aliases):
                    if canonical not in col_map:
                        col_map[canonical] = word['x0']
                        score += 1
        if score > best_score:
            best_score = score
            best_idx = idx
            best_map = col_map

    # Only accept if at least 2 column headers found
    if best_score < 2:
        return None, {}

    return best_idx, best_map


def _map_words_to_columns(
    line: list, col_map: dict
) -> dict:
    """
    Map words in a line to column names using nearest X-coordinate.
    col_map = {col_name: x0_anchor}
    """
    if not col_map:
        return {}

    col_names = list(col_map.keys())
    result = {c: [] for c in col_names}

    for word in line:
        wx = word['x0']
        # Find nearest column anchor
        nearest = min(col_names, key=lambda c: abs(col_map[c] - wx))
        result[nearest].append(word['text'])

    # Join multi-word cells
    return {c: ' '.join(result[c]).strip() for c in col_names}


def extract_table_by_column_position(pdf_path: str, pdf_doc=None) -> list[dict]:
    """
    Fallback table extraction when no header row is detected.

    Strategy:
    1. Extract all words with bounding boxes
    2. Cluster X positions into columns using gap detection
    3. Label columns as positional column names (col_0, col_1, ...)
    4. Return rows with positional column names
    """
    rows_out = []
    try:
        with _open_pdf(pdf_path, pdf_doc) as pdf:
            for page in pdf.pages:
                words = page.extract_words(
                    x_tolerance=5, y_tolerance=5,
                    keep_blank_chars=False, use_text_flow=False,
                )
                if not words:
                    continue

                # Find column boundaries by clustering X positions
                x_positions = sorted(set(
                    round(w['x0'] / 10) * 10 for w in words
                ))
                col_boundaries = _find_column_gaps(x_positions, min_gap=20)

                if len(col_boundaries) < 2:
                    continue

                lines = _group_words_into_lines(words, y_tol=5)
                for line in lines:
                    row = _assign_to_boundaries(line, col_boundaries)
                    if any(v.strip() for v in row.values()):
                        rows_out.append(row)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(
            "extract_table_by_column_position failed: %s", e
        )
    return rows_out


def _find_column_gaps(x_positions: list, min_gap: int = 20) -> list[int]:
    """Find significant gaps in X positions to identify column boundaries."""
    if not x_positions:
        return []
    boundaries = [x_positions[0]]
    for i in range(1, len(x_positions)):
        if x_positions[i] - x_positions[i - 1] >= min_gap:
            boundaries.append(x_positions[i])
    return boundaries


def _assign_to_boundaries(line: list, boundaries: list) -> dict:
    """Assign words to column slots based on X boundary positions."""
    cols = {f'col_{i}': [] for i in range(len(boundaries))}
    for word in line:
        # Find which boundary this word falls into
        col_idx = 0
        for i, b in enumerate(boundaries):
            if word['x0'] >= b:
                col_idx = i
        cols[f'col_{col_idx}'].append(word['text'])
    return {k: ' '.join(v).strip() for k, v in cols.items()}
