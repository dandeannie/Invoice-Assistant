"""
Auto-build a vendor template from ONE sample invoice - deterministically, with no AI.

How it works (pure geometry + a synonym dictionary):
  1. Read every word with its coordinates.
  2. Header fields: find "Label: value" and "Label   value" pairs (and values sitting
     under a label), then map the label to a standard field name via synonyms.
  3. Line-item table: find the header row by scoring lines against known column words,
     work out each column's x-band from the header AND from how the data below lines up,
     then name and type each column.
  4. Totals: derive subtotal / tax / total from the columns where possible, otherwise
     read them from the printed totals block.
  5. Self-check: run the template against the sample and, if the numbers don't
     reconcile, retry with adjusted settings and keep the best result.
"""
import re
from statistics import median

import pdfplumber

from .engine import clean_text, _to_number

# ---------------------------------------------------------------- synonyms
FIELD_SYNONYMS = {
    "invoice_number": ["invoice number", "invoice no", "invoice #", "invoice num",
                       "bill number", "bill no", "tax invoice no", "document no",
                       "order number", "order no", "receipt number", "receipt no",
                       "voucher no", "inv no", "invoice"],
    "invoice_date": ["invoice date", "date of issue", "bill date", "dated", "date",
                     "issue date", "document date"],
    "due_date": ["due date", "date due", "payment due", "pay by"],
    "po_number": ["po number", "po no", "purchase order", "order ref", "p.o. no",
                  "your order", "order reference"],
    "supplier_gstin": ["gstin", "gst no", "gst number", "vat registration", "vat no",
                       "tax registration", "abn", "supplier gstin"],
    "customer_gstin": ["customer gstin", "buyer gstin", "in gst", "recipient gstin"],
    "bill_to": ["bill to", "billed to", "invoice to", "customer", "buyer", "sold to"],
    "ship_to": ["ship to", "shipped to", "delivery address", "consignee"],
    "place_of_supply": ["place of supply", "state of supply"],
    "subtotal": ["subtotal", "sub total", "taxable value", "net amount", "total before tax",
                 "amount before tax", "sub-total", "taxable amount"],
    "tax": ["total tax", "tax amount", "gst amount", "vat amount"],
    "total": ["grand total", "invoice total", "total amount", "amount payable",
              "total payable", "net payable", "amount due", "balance due", "total"],
}

COLUMN_SYNONYMS = [
    ("description", ["description", "particulars", "item", "items", "goods", "service",
                     "services", "product", "details", "nature of service"]),
    ("hsn_sac", ["hsn", "sac", "hsn/sac", "hsn code", "sac code", "hsn sac"]),
    ("quantity", ["qty", "quantity", "qty.", "nos", "units", "unit"]),
    ("unit_price", ["rate", "unit price", "price", "unit rate", "mrp", "unit cost"]),
    ("taxable_value", ["taxable value", "taxable", "amount", "value", "net", "net amount"]),
    ("gst_pct", ["gst %", "gst%", "tax %", "rate %", "gst rate", "igst %", "tax rate", "%"]),
    ("cgst", ["cgst", "cgst amt", "cgst amount"]),
    ("sgst", ["sgst", "sgst amt", "sgst amount", "utgst"]),
    ("igst", ["igst", "igst amt", "igst amount"]),
    ("total", ["total", "line total", "amount", "net amount", "total amount", "subtotal"]),
]

END_WORDS = ["subtotal", "sub total", "grand total", "invoice total", "total",
             "amount due", "net payable", "amount payable", "taxable value"]

MONEY_COLS = {"unit_price", "taxable_value", "cgst", "sgst", "igst", "total", "amount"}
TEXT_COLS = {"description", "hsn_sac"}


_AMOUNT = re.compile(r"^[₹$€£]?\d{1,3}(,\d{3})*(\.\d{1,2})?$|^[₹$€£]?\d+\.\d{1,2}$")


def _is_amount(t):
    return bool(_AMOUNT.match(str(t).strip()))


def _norm(s):
    return re.sub(r"[^a-z0-9%/ ]", " ", str(s).lower()).replace("  ", " ").strip()


# ---------------------------------------------------------------- page reading
def read_page(pdf_path):
    with pdfplumber.open(pdf_path) as pdf:
        words, offset = [], 0.0
        for page in pdf.pages:
            for w in page.extract_words():
                w = dict(w)
                w["text"] = clean_text(w["text"])
                w["top"] = w["top"] + offset
                words.append(w)
            offset += page.height
        width = pdf.pages[0].width
    return words, width


from .pdf_utils import group_words_into_lines as _lines


def _cells(ln, gap=10.0):
    """Split a line into cells wherever there's a horizontal gap."""
    cells, cur = [], [ln[0]]
    for prev, w in zip(ln, ln[1:]):
        if w["x0"] - prev["x1"] > gap:
            cells.append(cur); cur = []
        cur.append(w)
    cells.append(cur)
    return cells


# ---------------------------------------------------------------- line items
def _score_header(ln):
    """How much does this line look like a table header row?"""
    text = _norm(" ".join(w["text"] for w in ln))
    hits = set()
    for canon, syns in COLUMN_SYNONYMS:
        for s in syns:
            if re.search(rf"(?<![a-z]){re.escape(s)}(?![a-z])", text):
                hits.add(canon)
                break
    return len(hits), hits


def _name_column(header_text, used):
    t = _norm(header_text)
    best, best_len = None, 0
    for canon, syns in COLUMN_SYNONYMS:
        for s in syns:
            if re.search(rf"(?<![a-z]){re.escape(s)}(?![a-z])", t) and len(s) > best_len:
                if canon in used and canon != "description":
                    continue
                best, best_len = canon, len(s)
    return best


def _stacked_cells(header_words):
    """Group header words into column cells, merging words that sit vertically above
    or below each other ("Taxable" over "Value", "CGST" over "Amt")."""
    cells = []
    for w in sorted(header_words, key=lambda w: w["x0"]):
        placed = False
        for c in cells:
            # overlap horizontally, or start within a few points of the cell
            if not (w["x1"] < c["x0"] - 4 or w["x0"] > c["x1"] + 4):
                c["words"].append(w)
                c["x0"] = min(c["x0"], w["x0"]); c["x1"] = max(c["x1"], w["x1"])
                placed = True
                break
        if not placed:
            cells.append({"x0": w["x0"], "x1": w["x1"], "words": [w]})
    cells.sort(key=lambda c: c["x0"])
    return [sorted(c["words"], key=lambda w: (w["top"], w["x0"])) for c in cells]


def _find_table(words):
    """Locate the line-item table and build its columns."""
    lines = _lines(words)
    # --- header row: best-scoring line with at least 2 known column words ---
    best_i, best_hits, best_score = None, set(), 0
    for i, ln in enumerate(lines):
        score, hits = _score_header(ln)
        if score > best_score:
            best_i, best_hits, best_score = i, hits, score
    if best_i is None or best_score < 2:
        return None

    header_line = lines[best_i]
    header_top = header_line[0]["top"]

    # A header often spans 2-3 stacked rows ("Taxable"/"Value", "CGST"/"Amt") that
    # cluster slightly ABOVE and BELOW the main row. Absorb any amount-free line
    # within a few points either way.
    lo = hi = best_i
    while lo - 1 >= 0 and abs(lines[lo - 1][0]["top"] - header_top) <= 10 \
            and not any(_is_amount(w["text"]) for w in lines[lo - 1]):
        lo -= 1
        header_line = sorted(header_line + lines[lo], key=lambda w: w["x0"])
    while hi + 1 < len(lines) and lines[hi + 1][0]["top"] - header_top <= 12 \
            and not any(_is_amount(w["text"]) for w in lines[hi + 1]):
        hi += 1
        header_line = sorted(header_line + lines[hi], key=lambda w: w["x0"])
    j = hi + 1
    header_bottom = max(w["bottom"] for w in header_line)

    # --- where does the table end? ---
    end_anchor, end_top = None, None
    for ln in lines[j:]:
        txt = _norm(" ".join(w["text"] for w in ln))
        for e in END_WORDS:
            if txt.startswith(e) or f" {e} " in f" {txt} ":
                # must have a number on the line, or be a clear totals label
                if any(_to_number(w["text"]) is not None for w in ln) or txt == e:
                    end_anchor, end_top = e, ln[0]["top"]
                    break
        if end_anchor:
            break
    if end_top is None:
        end_top = max(w["top"] for w in words) + 1

    # --- header cells -> seed columns ---
    seeds = []
    used = set()
    for cell in _stacked_cells(header_line):
        text = " ".join(w["text"] for w in cell)
        name = _name_column(text, used)
        if not name:
            continue
        used.add(name)
        seeds.append({"name": name, "header": text,
                      "x0": min(w["x0"] for w in cell),
                      "x1": max(w["x1"] for w in cell),
                      "center": (min(w["x0"] for w in cell) + max(w["x1"] for w in cell)) / 2})
    if len(seeds) < 2:
        return None
    seeds.sort(key=lambda c: c["center"])

    # --- refine each column from the DATA underneath (handles right-alignment) ---
    body = [w for w in words if header_bottom + 1 < w["top"] < end_top - 4]
    for s in seeds:
        s["lo"], s["hi"] = [], []
    desc_seed = next((s for s in seeds if s["name"] == "description"), seeds[0])
    for w in body:
        mid = (w["x0"] + w["x1"]) / 2
        nearest = min(seeds, key=lambda s: abs(mid - s["center"]))
        # A wrapped description runs far to the right and would otherwise pollute the
        # amount columns. Non-numeric words that don't sit under any header cell
        # belong to the description.
        if _to_number(w["text"]) is None and nearest is not desc_seed:
            under_header = any(s["x0"] - 4 <= mid <= s["x1"] + 4 for s in seeds)
            if not under_header:
                nearest = desc_seed
        nearest["lo"].append(w["x0"]); nearest["hi"].append(w["x1"])
    for s in seeds:
        if s["lo"]:
            s["dx0"] = min(min(s["lo"]), s["x0"])
            s["dx1"] = max(max(s["hi"]), s["x1"])
        else:
            s["dx0"], s["dx1"] = s["x0"], s["x1"]

    # --- turn extents into non-overlapping bands ---
    cols = []
    for i, s in enumerate(seeds):
        left = 20.0 if i == 0 else (seeds[i - 1]["dx1"] + s["dx0"]) / 2
        right = (s["dx1"] + seeds[i + 1]["dx0"]) / 2 if i + 1 < len(seeds) else s["dx1"] + 40
        name = s["name"]
        if name in TEXT_COLS:
            ctype = "text"
        elif name == "quantity":
            ctype = "number"
        elif name == "gst_pct":
            ctype = "text"      # keeps values like "Exempt" readable
        else:
            ctype = "money"
        cols.append({"name": name, "x_min": round(left, 1), "x_max": round(right, 1),
                     "type": ctype})

    cols = _fix_bands(cols, seeds)
    cols = _resolve_column_names(cols)

    # the leftmost column must be the description for wrapped rows to merge correctly
    if cols and cols[0]["name"] != "description":
        if not any(c["name"] == "description" for c in cols):
            cols.insert(0, {"name": "description", "x_min": 20.0,
                            "x_max": cols[0]["x_min"], "type": "text"})

    header_anchor = None
    for cell in _cells(header_line, gap=8.0):
        t = " ".join(w["text"] for w in cell)
        if _name_column(t, set()) in ("description", "hsn_sac", "quantity"):
            header_anchor = t.split()[0]
            break
    header_anchor = header_anchor or header_line[0]["text"]

    cfg = {"header_anchor": header_anchor, "row_tol": 6, "columns": cols}
    if end_anchor:
        cfg["end_anchor"] = " ".join(w.capitalize() for w in end_anchor.split())
    return cfg


def _fix_bands(cols, seeds):
    """Guarantee the bands are ordered, non-overlapping and non-empty. If refinement
    produced something impossible, fall back to the header cell positions."""
    bad = any(c["x_max"] <= c["x_min"] for c in cols)
    if not bad:
        for a, b in zip(cols, cols[1:]):
            if b["x_min"] < a["x_min"]:
                bad = True
                break
    if bad:
        for i, (c, s) in enumerate(zip(cols, seeds)):
            left = 20.0 if i == 0 else (seeds[i - 1]["x1"] + s["x0"]) / 2
            right = (s["x1"] + seeds[i + 1]["x0"]) / 2 if i + 1 < len(seeds) else s["x1"] + 60
            c["x_min"], c["x_max"] = round(left, 1), round(right, 1)
    # final guard: strictly increasing, positive width
    for i, c in enumerate(cols):
        if c["x_max"] <= c["x_min"]:
            c["x_max"] = c["x_min"] + 30
        if i and c["x_min"] < cols[i - 1]["x_min"]:
            c["x_min"] = cols[i - 1]["x_max"]
            c["x_max"] = max(c["x_max"], c["x_min"] + 30)
    return cols


def _resolve_column_names(cols):
    """Invoices reuse words like 'Amount' and 'Total' for different columns. Decide by
    position: when two money columns claim the same meaning, the RIGHTMOST is the line
    total and the earlier one is the taxable/net value."""
    totalish = [i for i, c in enumerate(cols) if c["name"] in ("total", "amount")]
    if len(totalish) > 1:
        for i in totalish[:-1]:
            if not any(c["name"] == "taxable_value" for c in cols):
                cols[i]["name"] = "taxable_value"
            else:
                cols[i]["name"] = f"amount_{i}"
        cols[totalish[-1]]["name"] = "total"
    elif len(totalish) == 1:
        cols[totalish[0]]["name"] = "total"
    # a lone 'taxable_value' with no total column IS the line amount
    if not any(c["name"] == "total" for c in cols):
        tv = [i for i, c in enumerate(cols) if c["name"] == "taxable_value"]
        if tv:
            cols[tv[-1]]["name"] = "amount"
    return cols


def _derive_totals_for(cols):
    names = {c["name"] for c in cols}
    d = {}
    if "taxable_value" in names:
        d["subtotal"] = {"sum": "taxable_value"}
    for t in ("cgst", "sgst", "igst"):
        if t in names:
            d[t] = {"sum": t}
    if "total" in names:
        d["total"] = {"sum": "total"}
        if "subtotal" in d:
            d["tax"] = {"diff": ["total", "subtotal"]}
    elif "amount" in names:
        # only one money column: it is the pre-tax line amount, so it gives the
        # SUBTOTAL. The invoice total must come from the printed totals block.
        d["subtotal"] = {"sum": "amount"}
    return d


# ---------------------------------------------------------------- header fields
def _pairs(words):
    """Label -> value pairs from colon form, gap form, and value-under-label."""
    from .builder import field_candidates
    return field_candidates(words)


def _infer_fields(words, table_cfg):
    cands = _pairs(words)
    fields, taken = {}, set()

    def consider(target, cand, score, syn=None):
        cur = fields.get(target)
        if cur is not None and score <= cur["_score"]:
            return
        entry = {**cand, "_score": score}
        # keep only the words that actually form the label, dropping anything that
        # bled in from a neighbouring block on the same line
        if syn:
            parts = str(cand.get("anchor", "")).split()
            k = len(syn.split())
            if len(parts) > k:
                entry["anchor"] = " ".join(parts[-k:])
        fields[target] = entry

    def value_fits(target, cand):
        """Reject obvious mismatches - an invoice number is never a currency amount,
        and a date field must hold something date-like."""
        val = str(cand.get("value", "")).strip()
        if not val:
            return False
        money = cand.get("is_money") or _is_amount(val)
        if target in ("invoice_number", "po_number", "supplier_gstin",
                      "customer_gstin", "bill_to", "ship_to") and money:
            return False
        if "date" in target:
            return bool(re.search(r"\d", val)) and not money
        if target in ("subtotal", "tax", "total"):
            return money or bool(re.search(r"\d", val))
        return True

    for c in cands:
        label = _norm(c.get("anchor", ""))
        if not label:
            continue
        for target, syns in FIELD_SYNONYMS.items():
            if not value_fits(target, c):
                continue
            for syn in syns:
                if label == syn:
                    consider(target, c, 100 + len(syn), syn)
                elif label.startswith(syn + " ") or label.endswith(" " + syn):
                    consider(target, c, 60 + len(syn), syn)
                elif re.search(rf"(?<![a-z]){re.escape(syn)}(?![a-z])", label):
                    consider(target, c, 30 + len(syn), syn)

    out = {}
    for name, c in fields.items():
        cfg = {"anchor": c["anchor"]}
        if c.get("below"):
            cfg["below"] = int(c["below"])
        if c.get("nth"):
            cfg["nth"] = int(c["nth"])
        val = str(c.get("value", ""))
        if name in ("subtotal", "tax", "total"):
            cfg["type"] = "money"
            cfg["occurrence"] = "last"       # these labels usually repeat
        elif "date" in name:
            cfg["type"] = "date"
            cfg["max_words"] = 3
        else:
            cfg["type"] = "text"
            n_words = len(val.split())
            cfg["max_words"] = max(1, min(n_words if n_words else 1, 5))
        if c.get("gap_hint"):
            cfg["gap"] = c["gap_hint"]
        out[name] = cfg

    # totals that will be computed from the line items don't need a header anchor
    if table_cfg:
        for k in _derive_totals_for(table_cfg["columns"]):
            out.pop(k, None)
    return out


# ---------------------------------------------------------------- main entry
def infer_template(pdf_path, vendor_name=None, keyword=None):
    """Build a complete template from one sample invoice. Returns (template, report)."""
    words, _ = read_page(pdf_path)
    report = []

    table = _find_table(words)
    if table:
        report.append(f"Found a line-item table with {len(table['columns'])} columns: "
                      + ", ".join(c["name"] for c in table["columns"]))
    else:
        report.append("No line-item table detected - only header fields were built.")

    fields = _infer_fields(words, table)
    report.append(f"Detected {len(fields)} header field(s): " + ", ".join(sorted(fields)))

    if not vendor_name:
        from .classify import guess_vendor_name
        vendor_name = guess_vendor_name("\n".join(
            " ".join(w["text"] for w in ln) for ln in _lines(words))) or "New Vendor"

    tpl = {"vendor": vendor_name,
           "identify": {"keyword": keyword or vendor_name},
           "fields": fields}
    if table:
        derived = _derive_totals_for(table["columns"])
        # subtotal from the lines + a printed total => tax is the difference
        if "subtotal" in derived and "total" not in derived and "total" in fields:
            derived["tax"] = {"diff": ["total", "subtotal"]}
        if derived:
            table["derive_totals"] = derived
            report.append("Totals will be computed from the line items: "
                          + ", ".join(derived))
        tpl["line_items"] = table
    return tpl, report


def verify(pdf_path, tpl):
    """Extract with the template and report how well it worked."""
    from .engine import extract_invoice
    from .validate import validate
    from .reconcile import reconcile
    try:
        inv = validate(extract_invoice(pdf_path, tpl))
        rec = reconcile(inv, pdf_path)
        return inv, rec
    except Exception as e:                     # never let a bad guess crash the UI
        return None, {"status": "ERROR", "notes": str(e)}


def build_and_verify(pdf_path, vendor_name=None, keyword=None):
    """Infer a template, check it against the sample, and try a couple of automatic
    repairs if the numbers don't line up. Returns (template, report, invoice, recon)."""
    tpl, report = infer_template(pdf_path, vendor_name, keyword)
    inv, rec = verify(pdf_path, tpl)

    if rec.get("status") != "OK" and tpl.get("line_items"):
        # repair 1: totals row may be inside the table - pull the table end earlier
        alt = {**tpl, "line_items": {**tpl["line_items"], "row_tol": 8}}
        inv2, rec2 = verify(pdf_path, alt)
        if rec2.get("status") == "OK":
            report.append("Adjusted row spacing to make the totals reconcile.")
            return alt, report, inv2, rec2
        # repair 2: read the totals from the printed block instead of the lines
        if "derive_totals" in tpl["line_items"]:
            alt2 = {**tpl, "line_items": {k: v for k, v in tpl["line_items"].items()
                                          if k != "derive_totals"}}
            inv3, rec3 = verify(pdf_path, alt2)
            if rec3.get("status") == "OK":
                report.append("Used the printed totals instead of summing the lines.")
                return alt2, report, inv3, rec3

    return tpl, report, inv, rec
