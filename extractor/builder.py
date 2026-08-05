"""
Helpers for the in-app "Add a new vendor" template builder.

These functions are deliberately kept free of Streamlit code so they can be
tested on their own. The page file (pages/1_Add_New_Vendor.py) calls them.
"""
from __future__ import annotations
import os
import re
import io
import yaml
import pdfplumber

from .engine import _norm, extract_invoice
from .validate import validate

TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")

STANDARD_FIELDS = ["invoice_number", "invoice_date", "po_number",
                   "subtotal", "tax", "total"]

FIELD_TYPES = ["text", "date", "number", "money"]


def default_type(name: str) -> str:
    """Guess a sensible type from the field name (used to pre-select the dropdown)."""
    n = (name or "").lower()
    if "date" in n:
        return "date"
    if any(k in n for k in ("subtotal", "tax", "total", "amount", "price",
                            "rate", "value", "charge", "cost")):
        return "money"
    if any(k in n for k in ("qty", "quantity", "count")):
        return "number"
    return "text"


# ---------- reading the sample invoice ----------

def load_page(pdf_path: str, resolution: int = 120):
    """Return words (with coordinates), page size in points, a PIL image of the
    page, and the pixels-per-point scale used to render it."""
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[0]
        from .engine import clean_text
        words = []
        for w in page.extract_words():
            w = dict(w)
            w["text"] = clean_text(w["text"])
            words.append(w)
        width, height = page.width, page.height
        image = page.to_image(resolution=resolution).original  # PIL image
    scale = resolution / 72.0
    return {"words": words, "width": width, "height": height,
            "image": image, "scale": scale}


from .pdf_utils import group_words_into_lines as _lines


def _segment_line(ln):
    """Split one line into separate 'Label : value' segments using the horizontal
    gaps between words. Words inside a field sit close together; there's a much
    bigger gap before the next field's label. Returns a list of segments, each with
    anchor, value, value_box (points), and gap_hint (a gap size that tells the
    extractor where this value ends so it won't spill into the next field)."""
    ln = sorted(ln, key=lambda w: w["x0"])
    if not ln:
        return []
    gaps = [ln[i]["x0"] - ln[i - 1]["x1"] for i in range(1, len(ln))]
    min_gap = min([g for g in gaps if g > 0], default=2.0)
    break_thresh = max(14.0, 3.0 * min_gap)

    # cut the line into chunks wherever a big gap occurs
    chunks, cur = [], [ln[0]]
    chunk_break_after = []  # the gap that ended each chunk (or None for the last)
    for i in range(1, len(ln)):
        if ln[i]["x0"] - ln[i - 1]["x1"] > break_thresh:
            chunks.append(cur); chunk_break_after.append(ln[i]["x0"] - ln[i - 1]["x1"])
            cur = [ln[i]]
        else:
            cur.append(ln[i])
    chunks.append(cur); chunk_break_after.append(None)

    segments = []
    skip_next = False
    for ci, (chunk, brk) in enumerate(zip(chunks, chunk_break_after)):
        if skip_next:
            skip_next = False
            continue
        # find the colon inside this chunk
        colon_idx = None
        for i, w in enumerate(chunk):
            if w["text"] == ":" or w["text"].endswith(":"):
                colon_idx = i
                break
        if colon_idx is None:
            continue
        label_ws = chunk[:colon_idx + 1]
        value_ws = chunk[colon_idx + 1:]
        # right-aligned totals put the value in the next chunk: "Total Due:      89.10"
        if not value_ws and ci + 1 < len(chunks):
            value_ws = chunks[ci + 1]
            skip_next = True
        anchor = " ".join(w["text"] for w in label_ws).rstrip(":").strip()
        if not anchor:
            continue
        value = " ".join(w["text"] for w in value_ws).strip()
        if value_ws:
            vb = (min(w["x0"] for w in value_ws), min(w["top"] for w in value_ws),
                  max(w["x1"] for w in value_ws), max(w["bottom"] for w in value_ws))
            internal = [value_ws[i]["x0"] - value_ws[i - 1]["x1"] for i in range(1, len(value_ws))]
            max_internal = max(internal, default=2.0)
        else:
            last = label_ws[-1]
            vb = (last["x1"] + 2, last["top"], last["x1"] + 60, last["bottom"])
            max_internal = 2.0
        # if another field follows on this line, tell the extractor to stop before it
        gap_hint = round((max_internal + brk) / 2) if brk else None
        segments.append({"anchor": anchor, "value": value, "value_box": vb,
                         "gap_hint": gap_hint})
    return segments


def detect_labels(words):
    """All 'Label : value' pairs on the page (now handles several per line)."""
    out = []
    for ln in _lines(words):
        for seg in _segment_line(ln):
            out.append({"anchor": seg["anchor"], "value": seg["value"]})
    seen, uniq = set(), []
    for d in out:
        if d["anchor"].lower() not in seen:
            seen.add(d["anchor"].lower()); uniq.append(d)
    return uniq


_MONEY_RE = re.compile(r"^[₹$€£]?\d{1,3}(,\d{3})*(\.\d{1,2})?$|^[₹$€£]?\d+\.\d{1,2}$")


def _is_money_token(text):
    """True only for properly-formatted monetary amounts (433.00, 6,496.00, ₹99.50).
    Rejects plain codes (996425), phone/fax fragments (2500.), and IDs with letters."""
    t = text.strip()
    if not (re.search(r"[.,]", t) or re.search(r"[₹$€£]", t)):
        return False
    return bool(_MONEY_RE.match(t))


def _money_candidates(ln):
    """Detect amount fields on a line even when there's no colon, e.g. 'Subtotal 81.00'
    or a totals row 'Grand Total 433.00 0.00 ... 455.00'. Each money value gets its
    position (nth) among the numbers on the line, so extraction is gap-immune."""
    from .engine import _to_number
    ln = sorted(ln, key=lambda w: w["x0"])
    # the label is the leading run of words before the first money amount
    label_ws = []
    for w in ln:
        if _is_money_token(w["text"]):
            break
        label_ws.append(w)
    anchor = " ".join(w["text"] for w in label_ws).rstrip(":").strip()
    if not anchor:
        return []
    out, nth = [], 0
    for w in ln[len(label_ws):]:
        if _to_number(w["text"]) is None:
            continue
        nth += 1
        if _is_money_token(w["text"]):
            out.append({"anchor": anchor, "value": w["text"], "nth": nth,
                        "is_money": True,
                        "value_box": (w["x0"], w["top"], w["x1"], w["bottom"])})
    return out


def _overlaps(a, b):
    return not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])


_DATEISH = re.compile(
    r"^(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2}|"
    r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?)$", re.I)
_IDISH = re.compile(r"^(?=.*\d)[A-Za-z0-9][A-Za-z0-9\-/_.]{3,}$")


def _looks_like_value(words):
    """Is this run of words a plausible field VALUE (not prose)?"""
    if not words or len(words) > 6:
        return False
    txt = " ".join(w["text"] for w in words).strip()
    if not txt:
        return False
    if any(_is_money_token(w["text"]) for w in words):
        return True
    if any(_DATEISH.match(w["text"]) for w in words):
        return True
    if any(_IDISH.match(w["text"]) for w in words):
        return True
    if "@" in txt and "." in txt:          # email
        return True
    return False


def _looks_like_label(words):
    """Short, mostly alphabetic run that could be a field label."""
    if not words or len(words) > 4:
        return False
    txt = " ".join(w["text"] for w in words).strip().rstrip(":")
    if len(txt) < 3:
        return False
    letters = sum(ch.isalpha() for ch in txt)
    return letters >= max(3, int(len(txt) * 0.6))


def _split_cells(ln, gap=18.0):
    """Cut a line into independent cells at wide gaps. Invoices often place a meta
    table (Invoice No / Date) beside the supplier block on the SAME line, so each cell
    has to be interpreted on its own."""
    ln = sorted(ln, key=lambda w: w["x0"])
    cells, cur = [], [ln[0]]
    for prev, w in zip(ln, ln[1:]):
        if w["x0"] - prev["x1"] > gap:
            cells.append(cur); cur = []
        cur.append(w)
    cells.append(cur)
    return cells


def _gapless_segments(ln):
    """Handle invoices that separate a label from its value with WHITESPACE instead of
    a colon, e.g. 'Invoice number      KJOT4RJQ-0008'. Works cell by cell, splitting
    each at its widest internal gap."""
    out = []
    for cell in _split_cells(ln):
        if len(cell) < 2:
            continue
        gaps = [(cell[i]["x0"] - cell[i - 1]["x1"], i) for i in range(1, len(cell))]
        gap, idx = max(gaps, key=lambda g: g[0])
        if gap < 4.0:
            continue
        label_ws, value_ws = cell[:idx], cell[idx:]
        if not (_looks_like_label(label_ws) and _looks_like_value(value_ws)):
            continue
        anchor = " ".join(w["text"] for w in label_ws).rstrip(":").strip()
        vb = (min(w["x0"] for w in value_ws), min(w["top"] for w in value_ws),
              max(w["x1"] for w in value_ws), max(w["bottom"] for w in value_ws))
        internal = [value_ws[i]["x0"] - value_ws[i - 1]["x1"]
                    for i in range(1, len(value_ws))]
        out.append({"anchor": anchor,
                    "value": " ".join(w["text"] for w in value_ws).strip(),
                    "value_box": vb,
                    "gap_hint": round(max(internal, default=2.0) + 3)})
    return out


def _value_groups(ln):
    """Every value-looking run on a line, so amounts/dates/IDs are clickable even when
    the line has no label at all (the label may sit on the line above)."""
    ln = sorted(ln, key=lambda w: w["x0"])
    groups, cur = [], []
    for i, w in enumerate(ln):
        near = cur and (w["x0"] - cur[-1]["x1"]) < 12
        if cur and not near:
            groups.append(cur); cur = []
        cur.append(w)
    if cur:
        groups.append(cur)
    return [g for g in groups if _looks_like_value(g)]


def _label_above(lines, li, box):
    """Find a label sitting directly above a value (two-row layouts)."""
    if li == 0:
        return None
    x0 = box[0]
    for prev in reversed(lines[:li][-2:]):
        cands = [w for w in prev if abs(w["x0"] - x0) < 40]
        if cands:
            txt = " ".join(w["text"] for w in sorted(cands, key=lambda w: w["x0"]))
            txt = txt.rstrip(":").strip()
            if txt and _looks_like_label(cands):
                return txt
    return None


def _label_left(ln, box):
    """Words to the left of a value on the same line become its label."""
    left = [w for w in ln if w["x1"] <= box[0] + 1]
    if not left:
        return None
    left = sorted(left, key=lambda w: w["x0"])[-4:]
    txt = " ".join(w["text"] for w in left).rstrip(":").strip()
    return txt if _looks_like_label(left) else None


def field_candidates(words):
    """Every clickable value with its box. Detects three patterns so the highlighting
    is comprehensive: 'Label: value' pairs, gap-separated 'Label   value' pairs, and
    standalone values whose label sits to the left or on the line above."""
    lines = _lines(words)
    cands = []
    for li, ln in enumerate(lines):
        covered = []
        segs = _segment_line(ln)            # Label: value
        for s in segs:
            cands.append(s); covered.append(s["value_box"])
        for s in _gapless_segments(ln):      # Label   value (per cell)
            if not any(_overlaps(s["value_box"], vb) for vb in covered):
                cands.append(s); covered.append(s["value_box"])
        for mc in _money_candidates(ln):      # amounts on a totals row
            if not any(_overlaps(mc["value_box"], vb) for vb in covered):
                cands.append(mc); covered.append(mc["value_box"])
        for g in _value_groups(ln):           # anything else value-shaped
            box = (min(w["x0"] for w in g), min(w["top"] for w in g),
                   max(w["x1"] for w in g), max(w["bottom"] for w in g))
            if any(_overlaps(box, vb) for vb in covered):
                continue
            anchor = _label_left(ln, box)
            below = None
            if not anchor:
                anchor = _label_above(lines, li, box)
                below = 1 if anchor else None
            if not anchor:
                continue
            cands.append({"anchor": anchor,
                          "value": " ".join(w["text"] for w in g).strip(),
                          "value_box": box, "gap_hint": None, "below": below,
                          "is_money": any(_is_money_token(w["text"]) for w in g)})
            covered.append(box)

    seen, uniq = [], []
    for c in cands:
        key = tuple(round(v) for v in c["value_box"])
        if key not in seen:
            seen.append(key); uniq.append(c)
    return uniq


def render_preview(image, scale, candidates, selected_idx=None):
    """Draw numbered highlight boxes over each detected value. Money fields are green,
    text fields blue, and the selected one orange, so amounts are easy to spot."""
    from PIL import ImageDraw
    im = image.convert("RGB").copy()
    draw = ImageDraw.Draw(im)
    for i, c in enumerate(candidates):
        x0, t, x1, b = [v * scale for v in c["value_box"]]
        if i == selected_idx:
            color = (211, 84, 0)
        elif c.get("is_money"):
            color = (22, 128, 60)
        else:
            color = (46, 91, 143)
        draw.rectangle([x0 - 2, t - 2, x1 + 2, b + 2], outline=color,
                       width=4 if i == selected_idx else 2)
        draw.text((x0 - 1, max(0, t - 13)), str(i + 1), fill=color)
    return im


def nearest_candidate(candidates, x_pt, y_pt, max_dist=70.0):
    """Return the index of the value box nearest the click (or None if the click is
    far from every box). Makes clicking forgiving - land anywhere near a highlight."""
    best, best_d = None, 1e18
    for i, c in enumerate(candidates):
        x0, t, x1, b = c["value_box"]
        inside = (x0 - 6 <= x_pt <= x1 + 6 and t - 6 <= y_pt <= b + 6)
        cx, cy = (x0 + x1) / 2, (t + b) / 2
        d = 0.0 if inside else ((cx - x_pt) ** 2 + (cy - y_pt) ** 2) ** 0.5
        if d < best_d:
            best, best_d = i, d
    if best is not None and best_d <= max_dist:
        return best
    return None


# ---------- click-on-preview mapping ----------

def point_to_word(words, x_pt, y_pt):
    """Given a click position in PDF points, return the nearest word."""
    best, best_d = None, 1e18
    for w in words:
        cx = (w["x0"] + w["x1"]) / 2
        cy = (w["top"] + w["bottom"]) / 2
        inside = (w["x0"] - 2 <= x_pt <= w["x1"] + 2 and
                  w["top"] - 2 <= y_pt <= w["bottom"] + 2)
        d = 0 if inside else (cx - x_pt) ** 2 + (cy - y_pt) ** 2
        if d < best_d:
            best, best_d = w, d
    return best


def anchor_from_value(words, value_word):
    """Given the value the user clicked, find the label sitting to its left on the
    same line (so we can store an anchor). Returns the anchor text, or ''. """
    same_line = [w for w in words
                 if abs(w["top"] - value_word["top"]) <= 3 and w["x1"] <= value_word["x0"] + 1]
    same_line.sort(key=lambda w: w["x0"])
    label = " ".join(w["text"] for w in same_line).strip()
    return re.sub(r"[:\-\s]+$", "", label).strip()


# ---------- assembling and saving the template ----------

def line_item_columns_from_clicks(clicked, desc_type="text"):
    """Turn clicked value-columns into x-band columns. `clicked` is a list of
    {name, type, x0}. A 'description' column is added automatically covering
    everything to the left of the first clicked column."""
    cs = sorted(clicked, key=lambda c: c["x0"])
    if not cs:
        return []
    first = cs[0]["x0"]
    cols = [{"name": "description", "x_min": 30.0, "x_max": round(first - 6, 1), "type": desc_type}]
    for i, c in enumerate(cs):
        x_min = round(first - 6, 1) if i == 0 else round((cs[i - 1]["x0"] + c["x0"]) / 2, 1)
        x_max = round(c["x0"] + 70, 1) if i == len(cs) - 1 else round((c["x0"] + cs[i + 1]["x0"]) / 2, 1)
        cols.append({"name": c["name"], "x_min": x_min, "x_max": x_max, "type": c["type"]})
    return cols


def render_column_markers(image, scale, x_positions, selected_x=None):
    """Draw vertical guide lines at each captured column x (points)."""
    from PIL import ImageDraw
    im = image.convert("RGB").copy()
    draw = ImageDraw.Draw(im)
    h = im.height
    for x in x_positions:
        px = x * scale
        color = (211, 84, 0) if x == selected_x else (22, 128, 60)
        draw.line([(px, 0), (px, h)], fill=color, width=2)
    return im


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return slug or "vendor"


def build_template_dict(vendor, identify_keyword, fields, line_items=None):
    """fields: list of {name, anchor, type, max_words?}. line_items: optional dict."""
    d = {"vendor": vendor}
    if identify_keyword:
        d["identify"] = {"keyword": identify_keyword}
    d["fields"] = {}
    for f in fields:
        cfg = {"anchor": f["anchor"], "type": f.get("type", "text")}
        if f.get("below"):
            cfg["below"] = int(f["below"])
        if f.get("nth"):
            cfg["nth"] = int(f["nth"])
        if f.get("max_words"):
            cfg["max_words"] = int(f["max_words"])
        if f.get("gap"):
            cfg["gap"] = f["gap"]
        d["fields"][f["name"]] = cfg
    if line_items:
        d["line_items"] = line_items
    return d


def to_yaml(template_dict) -> str:
    return yaml.safe_dump(template_dict, sort_keys=False, allow_unicode=True,
                          default_flow_style=False)


def save_template(vendor_id: str, yaml_text: str) -> str:
    os.makedirs(TEMPLATES_DIR, exist_ok=True)
    path = os.path.join(TEMPLATES_DIR, f"{vendor_id}.yaml")
    with open(path, "w", encoding="utf-8") as f:
        f.write(yaml_text)
    return path


def delete_template(vendor_id: str) -> bool:
    """Delete a vendor template file. Returns True if a file was removed."""
    for ext in (".yaml", ".yml"):
        path = os.path.join(TEMPLATES_DIR, vendor_id + ext)
        if os.path.exists(path):
            os.remove(path)
            return True
    return False


OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "output")


def list_output_files():
    """List generated spreadsheet/CSV files in the output folder (name, size KB)."""
    if not os.path.isdir(OUTPUT_DIR):
        return []
    files = []
    for name in sorted(os.listdir(OUTPUT_DIR)):
        p = os.path.join(OUTPUT_DIR, name)
        if os.path.isfile(p) and name.lower().endswith((".xlsx", ".csv")):
            files.append({"name": name, "kb": round(os.path.getsize(p) / 1024, 1)})
    return files


def delete_output_file(name: str) -> bool:
    """Delete one generated output file (guards against path escapes)."""
    safe = os.path.basename(name)
    path = os.path.join(OUTPUT_DIR, safe)
    if os.path.isfile(path):
        os.remove(path)
        return True
    return False


def preview_extract(pdf_path: str, template_dict):
    """Run the just-built template against the sample and return the Invoice,
    so the user can confirm it works before saving."""
    return validate(extract_invoice(pdf_path, template_dict))


# ---------- LLM-assisted generation ----------

SCHEMA_DOC = """
You write YAML templates for an invoice-extraction tool. A template describes WHERE
each value sits on ONE vendor's invoice so all their invoices can be read the same way.

TOP LEVEL:
  vendor: "<human readable vendor name>"
  identify: {keyword: "<a distinctive phrase that appears on this vendor's invoices>"}
  fields: { ... }            # header values
  line_items: { ... }        # optional table of services/products

FIELDS (each key becomes a spreadsheet column; use these standard names where they
apply: invoice_number, invoice_date, po_number, subtotal, tax, total. Any other name
you invent becomes an extra column, e.g. passenger_name, pnr):
  invoice_number:
    anchor: "<the label printed on the page, e.g. 'Invoice Number' or 'Number'>"
    type: text            # one of: text, date, number, money
    max_words: 2          # optional: cap the value length on crowded lines
    nth: 8                # optional: take the Nth number to the right of the anchor
    sum_nth: [4,5,6,7]    # optional: add those Nth numbers together (e.g. total of taxes)

LINE ITEMS - choose ONE of two styles:
  (A) simple tables with clear single-word column headers:
      line_items:
        header_anchor: "Description"
        end_anchor: "Subtotal"
        columns:
          - {name: description, header: "Description", type: text}
          - {name: quantity,    header: "Quantity",   type: money}
          - {name: unit_price,  header: "Unit Price", type: money}
          - {name: amount,      header: "Amount",     type: money}
  (B) dense tables (multi-row headers, wrapping numbers, e.g. GST tax invoices) -
      define columns by their x position (points from the left edge) and derive the
      invoice totals by summing the lines:
      line_items:
        header_anchor: "Description"
        end_anchor: "Grand Total"
        row_tol: 6
        columns:
          - {name: description, x_min: 40,  x_max: 120, type: text}
          - {name: line_total,  x_min: 215, x_max: 265, type: money}
          - {name: amount,      x_min: 505, x_max: 545, type: money}
        derive_totals:
          subtotal: {sum: line_total}
          cgst:     {sum: cgst}      # any name (cgst/sgst/igst) -> its own column
          sgst:     {sum: sgst}
          total:    {sum: amount}
          tax:      {diff: [total, subtotal]}
        # optional: which columns get a total in the line-items totals row
        # (defaults to money columns, excluding per-unit rates and percentages)
        total_columns: [taxable_value, cgst, sgst, total]

RULES:
- Output ONLY the YAML. No prose, no markdown fences.
- Prefer style (A) for simple tables, style (B) for dense/wrapping tax tables.
- Use the x positions from the WORD COORDINATES provided to choose x_min/x_max bands.
"""


def _words_dump(words, limit=400):
    rows = []
    for w in sorted(words, key=lambda w: (round(w["top"]), w["x0"]))[:limit]:
        rows.append(f"x={w['x0']:.0f} y={w['top']:.0f} {w['text']!r}")
    return "\n".join(rows)


# Presets so a non-technical user can pick a provider without knowing URLs.
# 'provider' is either 'anthropic' or 'openai' (the OpenAI-compatible path, which
# most providers and local runners speak). Model names are editable in the UI.
LLM_PRESETS = {
    "Anthropic (Claude)": {
        "provider": "anthropic", "base_url": None,
        "model": "claude-sonnet-5", "key_env": "ANTHROPIC_API_KEY"},
    "OpenAI": {
        "provider": "openai", "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o", "key_env": "OPENAI_API_KEY"},
    "Google Gemini": {
        "provider": "openai",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "model": "gemini-2.5-flash", "key_env": "GEMINI_API_KEY"},
    "Groq": {
        "provider": "openai", "base_url": "https://api.groq.com/openai/v1",
        "model": "llama-3.3-70b-versatile", "key_env": "GROQ_API_KEY"},
    "OpenRouter": {
        "provider": "openai", "base_url": "https://openrouter.ai/api/v1",
        "model": "anthropic/claude-3.5-sonnet", "key_env": "OPENROUTER_API_KEY"},
    "Mistral": {
        "provider": "openai", "base_url": "https://api.mistral.ai/v1",
        "model": "mistral-large-latest", "key_env": "MISTRAL_API_KEY"},
    "Local (Ollama)": {
        "provider": "openai", "base_url": "http://localhost:11434/v1",
        "model": "llama3.1", "key_env": None},
    "Local (vLLM)": {
        "provider": "openai", "base_url": "http://localhost:8000/v1",
        "model": "Qwen/Qwen2.5-7B-Instruct", "key_env": None},
    "Custom (OpenAI-compatible)": {
        "provider": "openai", "base_url": "", "model": "", "key_env": None},
}


def _call_anthropic(prompt, api_key, model, max_tokens=1500):
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(model=model, max_tokens=max_tokens,
                                 messages=[{"role": "user", "content": prompt}])
    return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")


def _call_openai(prompt, api_key, model, base_url, max_tokens=4096):
    """Works with OpenAI and any OpenAI-compatible endpoint (Gemini, Groq, OpenRouter,
    Mistral, Together, local Ollama/LM Studio, ...)."""
    from openai import OpenAI, APITimeoutError
    timeout_s = float(os.environ.get("AI_TIMEOUT", "600"))
    _timed_out = RuntimeError(
        f"The connection to the AI server timed out (took longer than {timeout_s:.0f} "
        "seconds). If you're using a local model on CPU, raise it by setting the "
        "AI_TIMEOUT environment variable (e.g. AI_TIMEOUT=600), or use a faster/smaller "
        "model. Otherwise the server may be overloaded or out of GPU memory.")
    client = OpenAI(api_key=api_key or "not-needed", base_url=(base_url or None), timeout=timeout_s)
    kwargs = dict(model=model, messages=[{"role": "user", "content": prompt}])

    last_exc = None
    _NATIVE_JSON_HOSTS = ("api.openai.com", "api.anthropic.com")
    _is_native = any(h in (base_url or "") for h in _NATIVE_JSON_HOSTS)
    _formats = [{"type": "json_object"}, None] if _is_native else [None]
    _extra_bodies = [{"chat_template_kwargs": {"enable_thinking": False}}, None] if not _is_native else [None]

    for eb in _extra_bodies:
        for fmt in _formats:
            for token_kw in [{"max_tokens": max_tokens}, {"max_completion_tokens": max_tokens}, {}]:
                try:
                    call_kwargs = dict(**kwargs, **token_kw)
                    if fmt:
                        call_kwargs["response_format"] = fmt
                    if eb:
                        call_kwargs["extra_body"] = eb
                    resp = client.chat.completions.create(**call_kwargs)
                    content = resp.choices[0].message.content or ""
                    if content.strip():
                        return content
                except APITimeoutError as e:
                    raise _timed_out from e
                except Exception as e:
                    last_exc = e
                    continue
    if last_exc is not None:
        raise RuntimeError(
            f"All API call attempts failed. Last error: {last_exc}"
        ) from last_exc
    return ""


def llm_generate_template(vendor_name, words, api_key, model,
                          provider="anthropic", base_url=None):
    """Ask an LLM to write a YAML template from the sample invoice. Works with any
    provider: provider='anthropic' uses Claude natively; provider='openai' uses the
    OpenAI-compatible API (set base_url for OpenAI, Gemini, Groq, Ollama, etc.).
    Returns YAML text. Raises on failure so the caller can show the error."""
    prompt = (
        f"{SCHEMA_DOC}\n\n"
        f"VENDOR NAME: {vendor_name}\n\n"
        f"WORD COORDINATES (x = points from left, y = points from top):\n"
        f"{_words_dump(words)}\n\n"
        f"Write the YAML template now. Output ONLY the YAML."
    )
    if provider == "anthropic":
        text = _call_anthropic(prompt, api_key, model)
    else:
        text = _call_openai(prompt, api_key, model, base_url)

    text = re.sub(r"^```[a-zA-Z]*\n|```$", "", text.strip()).strip()
    data = yaml.safe_load(text)
    if not isinstance(data, dict) or "fields" not in data:
        raise ValueError("The model did not return a valid template. Raw output:\n" + text[:400])
    return text
