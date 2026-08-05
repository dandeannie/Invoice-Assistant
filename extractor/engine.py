"""
The extraction engine.

How it works (plain English):
  1. Open the PDF and read every word together with its position on the page
     (x = distance from left, top = distance from top).
  2. Group words into lines (words with the same 'top' are on the same line).
  3. For each field (invoice number, date, total, ...) the template tells us an
     ANCHOR - a label like "Invoice Number". We find that label on the page and
     grab the text sitting just to the right of it. That is the field's value.
  4. For the line-item table, the template tells us the header words ("Description",
     "Quantity", ...). We find the header row, note the x-position of each column,
     then read every row underneath and drop each number into the right column
     based on where it sits horizontally.

Because a vendor's invoices always look the same, one template works for all of
that vendor's invoices - which is exactly the design you asked for.
"""
from __future__ import annotations
import re
import pdfplumber

from .models import Invoice, LineItem


# ---- small helpers ---------------------------------------------------------

def _norm(text: str) -> str:
    """Lowercase and strip surrounding punctuation, for tolerant matching."""
    return text.lower().strip(":.,;-()[]% ").strip()


def _to_number(text: str):
    """Turn '1,234.50' or '$1,234.50' into the number 1234.5. Return None if not a number."""
    if text is None:
        return None
    cleaned = re.sub(r"[^0-9.\-]", "", str(text).replace(",", ""))
    if cleaned in ("", "-", ".", "-."):
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


_DATE_FORMATS = ["%d-%b-%Y", "%d-%B-%Y", "%d %b %Y", "%d %B %Y",
                 "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%y",
                 "%Y-%m-%d", "%b %d, %Y", "%B %d, %Y"]


def _to_date(text):
    """Normalise a date to YYYY-MM-DD when recognised, else return the text
    unchanged (so nothing is lost). Numeric dates like 15/06/2026 are read
    day-first, the common convention outside the US."""
    if not text:
        return None
    from datetime import datetime
    s = str(text).strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return s


def _convert(raw, ftype):
    """Apply a field's declared type to the raw extracted text."""
    if ftype in ("money", "number"):
        return _to_number(raw)
    if ftype == "date":
        return _to_date(raw)
    return raw or None


def clean_text(t: str) -> str:
    """Some PDFs map characters the font can't describe to NUL (\x00) - typically a
    hyphen, dash or colon. Restore a hyphen and drop any other control characters, so
    values like 'KJOT4RJQ\x000008' read as 'KJOT4RJQ-0008'."""
    if not t:
        return t
    t = t.replace("\x00", "-")
    return "".join(ch for ch in t if ch == "\t" or ord(ch) >= 32)


def _cluster_lines(words, y_tol: float = 3.0):
    """Group words that sit on the same horizontal line. Returns a list of lines,
    each line being a list of word-dicts sorted left to right."""
    lines = []
    for w in sorted(words, key=lambda w: (round(w["top"]), w["x0"])):
        placed = False
        for line in lines:
            if abs(line[0]["top"] - w["top"]) <= y_tol:
                line.append(w)
                placed = True
                break
        if not placed:
            lines.append([w])
    for line in lines:
        line.sort(key=lambda w: w["x0"])
    lines.sort(key=lambda line: line[0]["top"])
    return lines


def _find_anchor_in_line(line, anchor_tokens):
    """If the anchor (a sequence of words) appears in this line, return the index
    of the word right after the anchor. Otherwise return None."""
    norm_words = [_norm(w["text"]) for w in line]
    n = len(anchor_tokens)
    for i in range(len(norm_words) - n + 1):
        if norm_words[i:i + n] == anchor_tokens:
            return i + n  # position just after the last anchor word
    return None


def _is_punct(text: str) -> bool:
    """True if the token is only punctuation (like a standalone ':')."""
    return _norm(text) == ""


def _value_to_right(line, start_idx, gap_threshold: float = 55.0, max_words: int | None = None):
    """Collect words to the right of the anchor that belong together as one value.
    Skips a leading standalone punctuation token (e.g. the ':' in 'Number : X') but
    keeps internal punctuation (e.g. the '-' in '6E - 6348'). Stops after max_words
    tokens if given, otherwise stops at a big horizontal gap."""
    collected = []
    prev_x1 = None
    for w in line[start_idx:]:
        # skip a leading standalone separator like ':' before any value is collected
        if not collected and _is_punct(w["text"]):
            continue
        if max_words is None and prev_x1 is not None and (w["x0"] - prev_x1) > gap_threshold:
            break
        collected.append(w["text"])
        prev_x1 = w["x1"]
        if max_words is not None and len(collected) >= max_words:
            break
    return " ".join(collected).strip()


def _numbers_right_of_anchor(lines, anchor_tokens, occurrence=1):
    """Find the line containing the anchor, then return every number printed to its
    right, in order. Used for reading a totals row (e.g. 'Grand Total 433 0 11 11 455').
    `occurrence` selects which matching line to use when the label repeats."""
    hits = []
    for line in lines:
        after = _find_anchor_in_line(line, anchor_tokens)
        if after is not None:
            nums = []
            for w in line[after:]:
                v = _to_number(w["text"])
                if v is not None:
                    nums.append(v)
            hits.append(nums)
    if not hits:
        return []
    if occurrence == "last":
        return hits[-1]
    idx = int(occurrence) - 1
    return hits[idx] if 0 <= idx < len(hits) else []


# ---- field extraction ------------------------------------------------------

def _extract_field(lines, field_cfg):
    """Extract one field using its anchor. Supported field_cfg options:
       anchor      : the label printed on the invoice (required)
       type        : 'text' (default) or 'money'
       max_words   : only take this many words as the value (good on crowded lines)
       nth         : take the Nth number printed to the right of the anchor (1-based)
       sum_nth     : list of positions to add together, e.g. [4,5,6,7] to total taxes
       gap         : override the gap that separates a value from the next label
       occurrence  : which match to use when a label appears more than once -
                     1 (default), 2, 3 ... or "last". Essential on receipts where
                     'Subtotal'/'Total' appear as a column header AND as a total row.
    """
    anchor_tokens = [_norm(t) for t in field_cfg["anchor"].split()]
    occurrence = field_cfg.get("occurrence", 1)

    # --- numeric picks from a row of numbers (e.g. the Grand Total row) ---
    if "nth" in field_cfg or "sum_nth" in field_cfg:
        nums = _numbers_right_of_anchor(lines, anchor_tokens, occurrence)
        if "sum_nth" in field_cfg:
            positions = field_cfg["sum_nth"]
            picked = [nums[i - 1] for i in positions if 0 < i <= len(nums)]
            return round(sum(picked), 2) if picked else None
        i = field_cfg["nth"]
        return nums[i - 1] if 0 < i <= len(nums) else None

    # --- value sits BELOW the label (two-row tables, common on receipts) ---
    if field_cfg.get("below"):
        n_below = int(field_cfg["below"]) if str(field_cfg["below"]).isdigit() else 1
        tol = float(field_cfg.get("x_tol", 22.0))
        for li, line in enumerate(lines):
            after = _find_anchor_in_line(line, anchor_tokens)
            if after is None:
                continue
            anchor_x = line[after - len(anchor_tokens)]["x0"]
            target = li + n_below
            if target >= len(lines):
                return None
            picked = [w for w in lines[target] if w["x0"] >= anchor_x - tol]
            if not picked:
                return None
            picked.sort(key=lambda w: w["x0"])
            gap = float(field_cfg.get("gap", 30.0))
            out = [picked[0]["text"]]
            for prev, w in zip(picked, picked[1:]):
                if w["x0"] - prev["x1"] > gap:
                    break
                out.append(w["text"])
            mw = field_cfg.get("max_words")
            if mw:
                out = out[:int(mw)]
            return _convert(" ".join(out), field_cfg.get("type", "text"))
        return None

    # --- value sits immediately LEFT of the label ---
    if field_cfg.get("before"):
        n = int(field_cfg["before"])
        for line in lines:
            after = _find_anchor_in_line(line, anchor_tokens)
            if after is not None:
                start = after - len(anchor_tokens)
                words = [w["text"] for w in line[max(0, start - n):start]]
                if words:
                    return _convert(" ".join(words), field_cfg.get("type", "text"))
        return None

    # --- ordinary label -> value-to-the-right ---
    gap = float(field_cfg.get("gap", 55.0))
    max_words = field_cfg.get("max_words")
    hits = []
    for line in lines:
        after = _find_anchor_in_line(line, anchor_tokens)
        if after is not None and after < len(line):
            hits.append((line, after))
    if not hits:
        return None
    if occurrence == "last":
        line, after = hits[-1]
    else:
        idx = int(occurrence) - 1
        if idx >= len(hits):
            return None
        line, after = hits[idx]
    raw = _value_to_right(line, after, gap, max_words)
    return _convert(raw, field_cfg.get("type", "text"))


# ---- line-item table extraction -------------------------------------------

def _column_positions(header_line, columns):
    """Find the x-position (left edge) of each column header on the header line."""
    positions = []
    for col in columns:
        header_word = col["header"].split()[0]  # first word of the header label
        target = _norm(header_word)
        x0 = None
        for w in header_line:
            if _norm(w["text"]) == target:
                x0 = w["x0"]
                break
        positions.append({"name": col["name"], "type": col.get("type", "text"), "x0": x0})
    # keep only columns we actually located, sorted left to right
    positions = [p for p in positions if p["x0"] is not None]
    positions.sort(key=lambda p: p["x0"])
    return positions


def _boundaries(positions):
    """Midpoints between adjacent columns become the boundaries that decide which
    column a word belongs to."""
    xs = [p["x0"] for p in positions]
    bounds = []
    for i in range(len(xs)):
        left = -1e9 if i == 0 else (xs[i - 1] + xs[i]) / 2
        right = 1e9 if i == len(xs) - 1 else (xs[i] + xs[i + 1]) / 2
        bounds.append((left, right))
    return bounds


def _extract_line_items(lines, li_cfg):
    """Read the line-item rows between the header row and the stop anchor (header-word
    column detection). Used by simple invoices like the ACME/GLOBEX samples."""
    header_anchor = [_norm(t) for t in li_cfg["header_anchor"].split()]
    end_anchor = [_norm(t) for t in li_cfg["end_anchor"].split()]
    columns = li_cfg["columns"]

    # locate header row and stop row by their 'top' position
    header_top = None
    header_line = None
    end_top = None
    for line in lines:
        if header_top is None and _find_anchor_in_line(line, header_anchor) is not None:
            header_top = line[0]["top"]
            header_line = line
        elif header_top is not None and end_top is None and \
                _find_anchor_in_line(line, end_anchor) is not None:
            end_top = line[0]["top"]
            break

    if header_line is None:
        return []
    if end_top is None:
        end_top = 1e9  # no explicit end; read to bottom

    positions = _column_positions(header_line, columns)
    if not positions:
        return []
    bounds = _boundaries(positions)

    items = []
    for line in lines:
        top = line[0]["top"]
        if top <= header_top + 1 or top >= end_top:  # skip header itself and rows past the stop
            continue
        cells = {p["name"]: [] for p in positions}
        for w in line:
            cx = (w["x0"] + w["x1"]) / 2
            for p, (lo, hi) in zip(positions, bounds):
                if lo <= cx < hi:
                    cells[p["name"]].append(w["text"])
                    break
        # build the row in column order
        row = {}
        for p in positions:
            joined = " ".join(cells[p["name"]]).strip()
            row[p["name"]] = _convert(joined, p["type"]) if p["type"] != "text" else joined
        # ignore empty rows
        if any(v not in (None, "", 0) for v in row.values()):
            items.append(LineItem(cols=row))
    return items


# ---- coordinate-band line-item extraction (for dense tables like GST invoices) ----



def _anchor_top(lines, anchor_text, occurrence=1, after_top=None):
    """Return the 'top' of the line containing the anchor text.
    `occurrence` picks the Nth match (or "last"); `after_top` ignores matches at or
    above that position - useful when a totals word also appears in the table header."""
    tokens = [_norm(t) for t in anchor_text.split()]
    hits = []
    for line in lines:
        if after_top is not None and line[0]["top"] <= after_top:
            continue
        if _find_anchor_in_line(line, tokens) is not None:
            hits.append(line[0]["top"])
    if not hits:
        return None
    if occurrence == "last":
        return hits[-1]
    i = int(occurrence) - 1
    return hits[i] if 0 <= i < len(hits) else None


def _extract_line_items_xband(all_words, lines, li_cfg):
    """Read line items using fixed column x-bands. This handles invoices whose table
    has a multi-row header and cells whose text wraps onto several lines - by grouping
    words into rows itself and merging description-only 'continuation' lines upward."""
    columns = li_cfg["columns"]  # each: name, x_min, x_max, type
    row_tol = float(li_cfg.get("row_tol", 6.0))
    start_offset = float(li_cfg.get("start_offset", 10.0))
    end_offset = float(li_cfg.get("end_offset", 8.0))

    header_top = _anchor_top(lines, li_cfg["header_anchor"],
                             li_cfg.get("header_occurrence", 1))
    # the end word may also appear in the header row, so only look below the header
    end_top = _anchor_top(lines, li_cfg["end_anchor"],
                          li_cfg.get("end_occurrence", 1),
                          after_top=header_top) if li_cfg.get("end_anchor") else None
    if header_top is None:
        return []
    top_cut = header_top + start_offset
    bot_cut = (end_top - end_offset) if end_top is not None else 1e9

    # candidate words that sit inside the table body
    cand = [w for w in all_words if top_cut < w["top"] < bot_cut]
    if not cand:
        return []

    # group candidate words into rows using row_tol
    rows = []
    for w in sorted(cand, key=lambda w: (w["top"], w["x0"])):
        if rows and abs(rows[-1]["top"] - w["top"]) <= row_tol:
            rows[-1]["words"].append(w)
        else:
            rows.append({"top": w["top"], "words": [w]})

    def cell_for(word):
        # use the word's CENTRE, not its left edge: amounts are usually right-aligned,
        # so a wide number starts further left and would otherwise fall in the
        # neighbouring column.
        mid = (word["x0"] + word["x1"]) / 2.0
        for col in columns:
            if col["x_min"] <= mid < col["x_max"]:
                return col["name"]
        # fall back to the left edge for wide text cells
        for col in columns:
            if col["x_min"] <= word["x0"] < col["x_max"]:
                return col["name"]
        return None

    # first pass: turn each row into values, and note which rows carry amounts
    parsed = []
    for row in rows:
        buckets = {col["name"]: [] for col in columns}
        for w in row["words"]:
            name = cell_for(w)
            if name is not None:
                buckets[name].append(w["text"])
        values = {}
        for col in columns:
            joined = " ".join(buckets[col["name"]]).strip()
            values[col["name"]] = _convert(joined, col["type"]) if col["type"] != "text" else joined
        desc = str(values.get("description", "") or "").strip()
        has_money = any(values.get(c["name"]) not in (None, "")
                        for c in columns if c["type"] in ("money", "number"))
        parsed.append({"top": row["top"], "values": values, "desc": desc,
                       "has_money": has_money})

    money_rows = [i for i, r in enumerate(parsed) if r["has_money"]]
    if not money_rows:
        return []

    # second pass: every non-amount line joins its NEAREST amount row - a wrapped
    # description can sit above as well as below the amounts, so attaching upward only
    # would split an item across two rows. Other text columns wrap too (a narrow
    # column can split "Exempt" into "Exem"/"pt"), so those fragments are carried over
    # as well: descriptions re-join with a space, narrow cells without one.
    text_cols = [c["name"] for c in columns if c["type"] == "text"]
    frag_desc = {i: [] for i in money_rows}
    frag_text = {i: {c: [] for c in text_cols if c != "description"} for i in money_rows}

    for i, r in enumerate(parsed):
        if r["has_money"]:
            continue
        vals = r["values"]
        if not any(str(vals.get(c) or "").strip() for c in text_cols):
            continue
        nearest = min(money_rows, key=lambda m: abs(parsed[m]["top"] - r["top"]))
        if r["desc"]:
            frag_desc[nearest].append((r["top"], r["desc"]))
        for c in text_cols:
            if c == "description":
                continue
            v = str(vals.get(c) or "").strip()
            if v:
                frag_text[nearest][c].append((r["top"], v))

    items = []
    for i in money_rows:
        vals = dict(parsed[i]["values"])
        parts = frag_desc[i] + [(parsed[i]["top"], parsed[i]["desc"])]
        parts = [p for p in parts if p[1]]
        parts.sort(key=lambda p: p[0])
        joined = " ".join(p[1] for p in parts).strip()
        if joined or not vals.get("description"):
            vals["description"] = joined
        for c, frags in frag_text[i].items():
            if frags:
                own = str(vals.get(c) or "").strip()
                pieces = sorted(frags + ([(parsed[i]["top"], own)] if own else []),
                                key=lambda p: p[0])
                vals[c] = "".join(p[1] for p in pieces)
        # a real line item always ends up with a description; rows that are only
        # amounts are part of the summary block (Taxable Value / CGST / Round Off)
        if str(vals.get("description") or "").strip():
            items.append(LineItem(cols=vals))

    return items


def _li_value(li: LineItem, col: str):
    return li.cols.get(col)


def _derive_totals(inv, items, cfg):
    """Compute invoice-level fields by adding up line-item columns. Standard fields
    (subtotal/tax/total) become main columns; any other name (cgst, sgst, igst, ...)
    becomes an extra column. cfg example:
        {subtotal: {sum: taxable_value}, cgst: {sum: cgst}, sgst: {sum: sgst},
         total: {sum: total}, tax: {diff: [total, subtotal]}}"""
    core = set(inv.model_fields) - {"extra", "line_items"}

    def _set(name, value):
        if name in core:
            setattr(inv, name, value)
        else:
            inv.extra[name] = value

    def _get(name):
        return getattr(inv, name, None) if name in core else inv.extra.get(name)

    # first pass: sum-based
    for field, rule in cfg.items():
        if "sum" in rule:
            col = rule["sum"]
            total = sum(v for li in items if (v := _li_value(li, col)) is not None)
            _set(field, round(total, 2))
    # second pass: difference-based (can reference the sums just computed)
    for field, rule in cfg.items():
        if "diff" in rule:
            a, b = rule["diff"]
            _set(field, round((_get(a) or 0.0) - (_get(b) or 0.0), 2))


# ---- public entry point ----------------------------------------------------

def _select_variant(template: dict, page_text: str) -> dict:
    """If a template holds several layouts under 'variants', return the one whose
    identify.keyword appears in the invoice text (merged over the top-level keys).
    Templates without variants are returned unchanged."""
    variants = template.get("variants")
    if not variants:
        return template
    tl = page_text.lower()
    chosen = None
    for v in variants:
        kw = (v.get("identify") or {}).get("keyword", "")
        if kw and kw.lower() in tl:
            chosen = v
            break
    chosen = chosen or variants[0]  # fall back to the first layout
    merged = {k: val for k, val in template.items() if k != "variants"}
    merged.update(chosen)
    # keep the family name if the variant doesn't set a specific vendor label
    if "vendor" not in chosen and template.get("vendor"):
        merged["vendor"] = chosen.get("vendor", template["vendor"])
    return merged


def extract_invoice(pdf_path: str, template: dict) -> Invoice:
    """Extract a single invoice PDF using the given vendor template."""
    with pdfplumber.open(pdf_path) as pdf:
        # combine words from all pages (most invoices are 1 page, but be safe)
        all_words = []
        page_offset = 0
        for page in pdf.pages:
            for w in page.extract_words():
                w = dict(w)
                w["text"] = clean_text(w["text"])
                w["top"] = w["top"] + page_offset
                all_words.append(w)
            page_offset += page.height

    lines = _cluster_lines(all_words)

    # A template may bundle several layouts as 'variants'; pick the one whose vendor
    # keyword appears on this invoice, so one template can cover look-alike vendors.
    page_text = " ".join(w["text"] for w in all_words)
    template = _select_variant(template, page_text)

    import os
    inv = Invoice(source_file=os.path.basename(pdf_path), vendor=template.get("vendor", ""))

    core_fields = set(Invoice.model_fields.keys())
    for field_name, cfg in template.get("fields", {}).items():
        value = _extract_field(lines, cfg)
        if field_name in core_fields and field_name not in ("extra", "line_items"):
            setattr(inv, field_name, value)
        else:
            inv.extra[field_name] = value

    if "line_items" in template:
        li_cfg = template["line_items"]
        cols = li_cfg.get("columns", [])
        use_xband = bool(cols) and "x_min" in cols[0]
        if use_xband:
            inv.line_items = _extract_line_items_xband(all_words, lines, li_cfg)
        else:
            inv.line_items = _extract_line_items(lines, li_cfg)
        if "derive_totals" in li_cfg:
            _derive_totals(inv, inv.line_items, li_cfg["derive_totals"])

        # decide which line columns are meaningful to total (money amounts, not
        # per-unit rates or percentages); a template may override with total_columns
        explicit = li_cfg.get("total_columns")
        if explicit is not None:
            inv.line_total_columns = list(explicit)
        else:
            per_unit = {"rate", "unit_price", "price", "unit_rate", "mrp", "unit_cost"}
            summable = []
            for c in li_cfg.get("columns", []):
                n = c.get("name", ""); t = c.get("type", "")
                low = n.lower()
                if t == "money" and low not in per_unit and "pct" not in low and "percent" not in low:
                    summable.append(n)
            inv.line_total_columns = summable

    return inv
