"""
Template-free extraction: read ANY invoice PDF and use an LLM to pull out the vendor,
invoice/bill/receipt number, date, every line item (with multi-line descriptions joined),
quantities, all applicable taxes, subtotal and total. Works with any provider supported
in builder.LLM_PRESETS (Anthropic, OpenAI, Gemini, Groq, Mistral, OpenRouter, local
Ollama, or a custom OpenAI-compatible endpoint).
"""
import importlib.metadata
import json
import os
import re

import pdfplumber

from .models import Invoice, LineItem
from .builder import _call_anthropic, _call_openai
from .security import guard_ai_call, wrap_untrusted, log_event, mask_key, load_settings
from .pdf_utils import _pdf_text, _TABLE_SETTINGS, extract_table_with_columns, extract_financial_summary  # FIX 7 & 10
from .ocr import extract_text_with_ocr_fallback
from .utils import _num, _normalize_date  # FIX 14 & FIX 3: shared utilities
from .validators import validate_invoice_number, validate_po_number, validate_line_items  # FIX 11, 15, 16, 17: field validation

# Column order used for line items when present
_LI_ORDER = ["description", "hsn_sac", "quantity", "unit_price", "tax_rate",
             "tax_amount", "amount"]

_TOTAL_ROW_PATTERNS = re.compile(
    r'^\s*('
    r'total|grand\s*total|sub\s*total|subtotal|taxable\s*value|'
    r'tax\s*total|tax\s*amount|round\s*off|rounding|'
    r'cgst|sgst|igst|gst|vat|cess|surcharge|'
    r'freight|shipping|handling|delivery\s*charges?|'
    r'discount|less\s*discount|trade\s*discount|'
    r'advance|amount\s*paid|balance\s*due|amount\s*payable|'
    r'net\s*(?:total|amount|payable)|'
    r'invoice\s*(?:total|value|amount)|'
    r'amount\s*in\s*words|rupees|rs\.?'
    r')\b',
    re.IGNORECASE
)

# FIX 7: _TABLE_SETTINGS was a duplicate of pdf_utils._TABLE_SETTINGS — deleted; imported above

INSTRUCTIONS = """You are an expert accounts-payable data-entry assistant. Read the
invoice document below (it includes both structured tables and layout text) and
return the data as STRICT JSON only - no prose, no markdown, no code fences.

IMPORTANT: Some text extracted from scanned invoices may be marked with uncertainty markers:
- [?text?] means OCR read this with low confidence — verify against context
- [??text??] means OCR read this with very low confidence — use context clues or return null for this field if unsure
Do not include these markers in your extracted values.

Extract exactly this shape:
{
  "vendor": "Supplier/seller company name. Look for the company name at the TOP of the invoice, often in a header or letterhead. Also check: Vendor, Supplier, From, Sold By, Billed By, Issued By.",
  "invoice_number": "Invoice number/ID. Look for: Invoice No, Invoice #, Invoice Number, Bill No, Bill Number, Tax Invoice No, Inv No, Inv #, Document No, Doc No, Voucher No.",
  "po_number": "Purchase order number. Look for ANY of these labels: PO Number, PO No, PO#, P.O. Number, Purchase Order, Purchase Order No, Order Ref, Order Reference, Order No, Buyer Order No, Buyer Order, Reference No, Ref No, Your Order No, Customer PO, Client PO. Extract the VALUE next to any of these labels.",
  "invoice_date": "Invoice date. Look for: Invoice Date, Bill Date, Date, Tax Invoice Date, Document Date, Issue Date, Dated. Extract the date EXACTLY as printed on the invoice. Do not reformat or interpret the date. Examples: '20-Jul-26', '20/07/2026', '20-07-2026'. Return the raw string as-is.",
  "currency": "INR / USD / ... if shown, else null",
  "cgst": "CGST amount if present, else null",
  "sgst": "SGST amount if present, else null",
  "igst": "IGST amount if present, else null",
  "taxable_value": "pre-tax subtotal / taxable value if shown, else null",
  "tax": "TOTAL tax = CGST + SGST + IGST combined. If only one tax line exists use that. NEVER use only CGST or only SGST alone as the total tax.",
  "line_items": [
    {
      "description": "Product or service name ONLY. EXCLUDE any row that is a summary, subtotal, tax, total, grand total, CGST, SGST, IGST, VAT, freight, discount, round-off, or 'amount in words' row. Only include actual products or services being invoiced.",
      "quantity": number or null,
      "unit_price": number or null,        // price per unit / rate
      "tax_rate": number or null,          // % for this line if shown
      "tax_amount": number or null,        // tax value for this line if shown
      "amount": number or null             // line total (taxable or gross as printed)
    }
  ],
  "taxes": [                                // ALL applicable taxes at invoice level
    {"name": "CGST", "rate": number or null, "amount": number}
    // e.g. CGST, SGST, IGST, VAT, GST, Service Tax, Sales Tax, Cess, etc.
  ],
  "subtotal": number or null,              // pre-tax total / taxable value
  "total": number or null                  // final payable amount
}

RULES:
- CRITICAL: Extract EVERY SINGLE LINE ITEM row from the table. If there are 10 line items, output ALL 10 entries in "line_items". Do NOT stop after 1 row.
- CRITICAL: Read full numerical values carefully without dropping digits or commas (e.g. "247,800.00" -> 247800.0, NOT 24).
- If an item's description spans multiple lines, JOIN it into one string (single spaces).
- Numbers must be plain: no currency symbols, no thousands separators (1064000, not "10,64,000.00"). Use a dot for decimals.
- Put every distinct tax component in "taxes" (e.g. CGST and SGST as two entries).
- Look for PO Number, Purchase Order Number, P.O. No., Order Ref, Order Reference, or similar labels anywhere on the invoice, including near the header or line items.
- Each tax type (e.g. IGST, CGST, SGST) must appear as exactly ONE entry in the taxes array. Do not split a single tax type into multiple entries based on different calculation steps or sub-values shown on the invoice.
- If the invoice shows a final TOTAL row with tax breakdown, prioritize matching those final tax values over intermediate calculation values shown elsewhere on the invoice.
- Line items may show different tax rates (e.g. some rows at 18%, others at 28%) — this is normal. Regardless of how many different rates appear across line items, the invoice-level tax section (usually near the subtotal/total) will show ONE final total for each tax type (e.g. one IGST total). ALWAYS use that final summary total directly — do NOT attempt to compute, split, or re-derive the tax total from individual line item rates or amounts.
- INVOICE NUMBER RULES: ONLY extract the value immediately next to exact labels ('Invoice No', 'Invoice No.', 'Invoice Number', 'Invoice #', 'Bill No', 'Tax Invoice No', 'Inv No', 'Invoice Ref'). Must be on same line or next line directly below. NEVER extract values next to 'Date', 'Dated', 'PO No', 'Order No', 'Ref No', 'Receipt No', 'Cheque No', 'Challan No', 'Tel', 'Phone', 'GSTIN', 'PAN'. NEVER extract a date or phone number. If uncertain, return null.
- PO NUMBER RULES: ONLY extract the value immediately next to exact labels ('PO No', 'PO No.', 'PO Number', 'Purchase Order', 'Purchase Order No', 'Buyer Order No', 'Order Ref', 'Order No'). Must be on same line or next line directly below. If field is blank or contains only dashes ('---', 'N/A', 'NIL'), return null. NEVER use adjacent label text as PO value (e.g. 'Dated', 'Tel No', 'Phone', 'Reference', 'GSTIN', 'Challan', 'Receiver'). If uncertain, return null.
- EXEMPT / NIL GST RULES: If a line item contains 'Exempt', 'NIL', 'Nil Rated', or '0%' in any tax column, set cgst_rate=0, sgst_rate=0, igst_rate=0 for that row. Do NOT inherit tax rates from other rows for exempt rows. Explicitly set to 0.
- Verify before output: subtotal + sum of all tax amounts should equal total. If they don't match, re-check which tax values you extracted.
- If a value is not present on the invoice, use null. Never invent values.
- Output ONLY the JSON object."""

INSTRUCTIONS_COMPACT = """Extract invoice data as strict JSON only. 
No prose, no markdown, no explanation.

{
  "vendor": "supplier name",
  "invoice_number": "invoice number",
  "invoice_date": "YYYY-MM-DD",
  "po_number": "PO number or null",
  "currency": "INR/USD/etc or null",
  "line_items": [
    {
      "description": "item description",
      "quantity": number or null,
      "unit_price": number or null,
      "tax_rate": number or null,
      "tax_amount": number or null,
      "amount": number or null
    }
  ],
  "taxes": [{"name": "CGST/SGST/etc", "rate": number, "amount": number}],
  "subtotal": number or null,
  "total": number or null
}

RULES:
- Extract ALL line items without exception. Never stop early.
- Each table row = one line item. Never merge rows.
- Numbers: plain digits only, no symbols, no commas (247800 not 2,47,800).
- Missing values: null.
- Each tax type (e.g. IGST, CGST, SGST) must appear as exactly ONE entry in taxes. Never split one tax into multiple entries.
- Prioritize the invoice-level summary tax totals (near subtotal/total) over line-item-level tax amounts. If rows show different rates (e.g. 18% and 28%), still use the ONE final summary total for each tax type.
- Verify: subtotal + sum(tax amounts) should equal total. If not, re-check tax values.
- Look for PO Number, Purchase Order Number, P.O. No., Order Ref, Order Reference, or similar labels.
- Output ONLY the JSON object, nothing else."""





# FIX 14: _num() moved to extractor/utils.py — imported above


def _parse_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()
    text = re.sub(r'^(Thinking Process|Analysis|Reasoning)[:\s].*?(?=\{)', '', text, flags=re.DOTALL | re.IGNORECASE).strip()
    text = re.sub(r"^```[a-zA-Z]*\n?|```$", "", text).strip()
    start = text.find("{")
    if start != -1:
        text = text[start:]

    # Direct parse try
    try:
        return json.loads(text)
    except Exception:
        pass

    # Try parsing up to the last closing brace
    end = text.rfind("}")
    if end != -1:
        try:
            return json.loads(text[:end + 1])
        except Exception:
            pass

    # Stack-based repair for truncated JSON structures
    def _stack_repair(s: str):
        stack = []
        in_string = False
        escape = False
        for ch in s:
            if escape:
                escape = False
                continue
            if ch == '\\' and in_string:
                escape = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if not in_string:
                if ch in ('{', '['):
                    stack.append(ch)
                elif ch == '}' and stack and stack[-1] == '{':
                    stack.pop()
                elif ch == ']' and stack and stack[-1] == '[':
                    stack.pop()

        repaired = s
        if in_string:
            repaired += '"'
        repaired = re.sub(r'[\s,:]+$', '', repaired)
        matching = {'{': '}', '[': ']'}
        for open_ch in reversed(stack):
            repaired += matching[open_ch]
        return json.loads(repaired)

    try:
        return _stack_repair(text)
    except Exception:
        pass

    # Truncate back to last complete entry boundary and repair
    last_boundary = max(text.rfind("}"), text.rfind("]"), text.rfind(","))
    if last_boundary != -1:
        try:
            return _stack_repair(text[:last_boundary])
        except Exception:
            pass

    return json.loads(text)


def _is_summary_row(item) -> bool:
    """Return True if this line item looks like a summary/total row."""
    desc = str(item.description).strip().lower()
    if _TOTAL_ROW_PATTERNS.match(desc):
        return True
    if not desc or desc in ('', '-', 'n/a', 'none'):
        return True
    return False


def _strip_ocr_markers(val):
    """Strip OCR uncertainty markers ([?text?], [??text??]) from extracted string values."""
    if isinstance(val, str):
        return re.sub(r'\[?\?+([^?\]]*)\?+\]?', r'\1', val).strip()
    return val


def _has_math_failure(inv) -> bool:
    """Return True if validation failed due to math mismatch."""
    math_keywords = ['sum', 'math', 'mismatch', 'subtotal', 'total', 'tax', '!=']
    return any(
        any(k in note.lower() for k in math_keywords)
        for note in inv.validation_notes
    )


def _build_retry_hint(inv) -> str:
    """Build a targeted retry instruction from validation failures."""
    lines = ["CORRECTION NEEDED — the previous extraction had math errors:"]
    for note in inv.validation_notes:
        lines.append(f"  - {note}")
    lines.append("")
    lines.append("Re-examine the invoice carefully and return corrected values.")
    lines.append(f"Previous values: subtotal={inv.subtotal}, tax={inv.tax}, total={inv.total}")
    lines.append("Check: subtotal + tax must equal total. Line items must sum to subtotal.")
    return "\n".join(lines)


def _score(inv) -> int:
    """Simple quality score — higher is better."""
    score = 0
    if inv.validation_ok:
        score += 10
    score -= len(inv.validation_notes)
    if inv.total is not None:
        score += 2
    if inv.subtotal is not None:
        score += 1
    if inv.line_items:
        score += len(inv.line_items)
    return score


def _format_structured_rows(rows: list[dict]) -> str:
    """Format structured row dicts as a readable table hint for the LLM."""
    if not rows:
        return ""
    headers = list(rows[0].keys())
    lines = ["STRUCTURED TABLE (column-mapped, use this preferentially):"]
    lines.append(" | ".join(headers))
    lines.append("-" * 60)
    for row in rows:
        lines.append(" | ".join(str(row.get(h, '')) for h in headers))
    return "\n".join(lines)


def _format_financial_summary(summary: dict) -> str:
    """Format extracted financial summary as a prompt hint."""
    if not summary:
        return ""
    lines = ["FINANCIAL SUMMARY (extracted directly — use these values):"]
    label_map = {
        'subtotal':    'Subtotal / Taxable Value',
        'cgst':        'CGST',
        'sgst':        'SGST',
        'igst':        'IGST',
        'total_tax':   'Total Tax',
        'round_off':   'Round Off',
        'grand_total': 'Grand Total',
        'discount':    'Discount',
    }
    for field, label in label_map.items():
        if field in summary:
            lines.append(f"  {label}: {summary[field]}")
    return "\n".join(lines)


def invoice_from_data(data: dict, source_file: str) -> Invoice:
    """Map the LLM's JSON into an Invoice (taxes -> their own columns, line items ->
    ordered cols)."""
    inv = Invoice(source_file=source_file, vendor=_strip_ocr_markers(str(data.get("vendor") or "").strip()))
    inv.invoice_number = (_strip_ocr_markers(str(data["invoice_number"]).strip())
                          if data.get("invoice_number") else None)
    if inv.invoice_number:
        cleaned_inv, inv_conf = validate_invoice_number(inv.invoice_number)
        if inv_conf < 0.4:
            inv.invoice_number = None
            setattr(inv, '_invoice_number_low_confidence', True)
        else:
            inv.invoice_number = cleaned_inv
            if inv_conf < 0.7:
                setattr(inv, '_invoice_number_low_confidence', True)

    inv.invoice_date = (_strip_ocr_markers(str(data["invoice_date"]).strip())
                        if data.get("invoice_date") else None)

    inv.po_number = (_strip_ocr_markers(str(data["po_number"]).strip())
                     if data.get("po_number") else None)
    if inv.po_number:
        cleaned_po, po_conf = validate_po_number(inv.po_number)
        if po_conf < 0.4:
            inv.po_number = None
        else:
            inv.po_number = cleaned_po
    inv.cgst = _num(data.get("cgst"))
    inv.sgst = _num(data.get("sgst"))
    inv.igst = _num(data.get("igst"))
    inv.taxable_value = _num(data.get("taxable_value"))
    inv.subtotal = _num(data.get("subtotal"))
    inv.total = _num(data.get("total"))
    if data.get("currency"):
        inv.extra["currency"] = str(data["currency"]).strip()

    # taxes -> each becomes its own invoice column, and sum -> inv.tax
    tax_total = 0.0
    have_tax = False
    for t in (data.get("taxes") or []):
        name = (t.get("name") or "tax").strip()
        amt = _num(t.get("amount"))
        if amt is None:
            continue
        have_tax = True
        tax_total += amt
        key = name if name not in inv.extra else f"{name}_amount"
        inv.extra[key] = round(amt, 2)
    if have_tax:
        inv.tax = round(tax_total, 2)
    elif inv.subtotal is not None and inv.total is not None:
        inv.tax = round(inv.total - inv.subtotal, 2)

    # FIX 1: GST post-processing — sum CGST+SGST+IGST into tax field
    gst_components = [inv.cgst, inv.sgst, inv.igst]
    gst_sum = sum(x for x in gst_components if x is not None)
    if gst_sum > 0:
        inv.tax = round(gst_sum, 2)

    # line items
    items = []
    for row in (data.get("line_items") or []):
        desc = _strip_ocr_markers(str(row.get("description") or "").strip())
        if desc and _TOTAL_ROW_PATTERNS.match(desc):
            continue
        cols = {}
        for k in _LI_ORDER:
            v = row.get(k)
            if k in ("description", "hsn_sac"):
                if v:
                    cols[k] = _strip_ocr_markers(str(v).strip())
            elif v is not None:
                cols[k] = _num(v)
        if cols.get("description") or any(k in cols for k in ("amount", "quantity")):
            items.append(LineItem(cols=cols))
    # FIX 4: post-processing filter — remove summary rows that LLM included
    inv.line_items = [item for item in items if not _is_summary_row(item)]

    # which line columns are meaningful to total
    present = {k for li in inv.line_items for k in li.cols}
    inv.line_total_columns = [c for c in ("amount", "tax_amount") if c in present]
    return inv


_NUM_LABELS = [
    r"order\s*(?:number|no\.?|#)\s*[:\-]?\s*([A-Za-z0-9][\w\-/]{2,})",
    r"invoice\s*(?:number|no\.?|#)\s*[:\-]?\s*([A-Za-z0-9][\w\-/]{2,})",
    r"bill\s*(?:number|no\.?|#)\s*[:\-]?\s*([A-Za-z0-9][\w\-/]{2,})",
    r"receipt\s*(?:number|no\.?|#)\s*[:\-]?\s*([A-Za-z0-9][\w\-/]{2,})",
]

_DATE_PATTERNS = [
    r"\b(\d{4}-\d{2}-\d{2})\b",
    r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b",
    r"\b(\d{1,2}[-\s][A-Za-z]{3,9}[-,\s]\s*\d{4})\b",
    r"\b([A-Za-z]{3,9}\s+\d{1,2},\s*\d{4})\b",
]


def _fallback_fields(inv, text):
    """Fill anything the model left out using deterministic patterns, so a single
    missed field never costs the whole invoice."""
    if not inv.invoice_number:
        for pat in _NUM_LABELS:
            m = re.search(pat, text, re.I)
            if m:
                inv.invoice_number = m.group(1).strip()
                break

    # FIX 2: PO number regex fallback if LLM missed it
    if inv.po_number is None and text:
        po_patterns = [
            r'(?:PO|P\.O\.)\s*(?:Number|No\.?|#)\s*[:\-]?\s*([A-Z0-9\-/]+)',
            r'Purchase\s*Order\s*(?:No\.?|Number|#)?\s*[:\-]?\s*([A-Z0-9\-/]+)',
            r'Order\s*(?:Ref|Reference|No\.?)\s*[:\-]?\s*([A-Z0-9\-/]+)',
            r'Buyer\s*Order\s*(?:No\.?|#)?\s*[:\-]?\s*([A-Z0-9\-/]+)',
            r'(?:Reference|Ref)\s*(?:No\.?|Number|#)\s*[:\-]?\s*([A-Z0-9\-/]+)',
            r'Customer\s*PO\s*[:\-]?\s*([A-Z0-9\-/]+)',
            r'Your\s*Order\s*(?:No\.?|#)?\s*[:\-]?\s*([A-Za-z0-9\-/]+)',
        ]
        for pattern in po_patterns:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                inv.po_number = m.group(1).strip()
                break

    if not inv.invoice_date:
        for pat in _DATE_PATTERNS:
            m = re.search(pat, text)
            if m:
                from .engine import _convert
                inv.invoice_date = _convert(m.group(1), "date") or m.group(1)
                break

    # FIX 3: normalize date fields to prevent corruption
    if inv.invoice_date:
        inv.invoice_date = _normalize_date(inv.invoice_date)

    if inv.total is None or inv.subtotal is None:
        # reuse the printed-total reader used for reconciliation
        try:
            from .reconcile import _printed_total, _printed_subtotal
            lines = [l for l in text.splitlines() if l.strip()]
            if inv.total is None:
                inv.total = _printed_total(lines)
            if inv.subtotal is None:
                inv.subtotal = _printed_subtotal(lines)
        except Exception:
            pass
    if inv.tax is None and inv.total is not None and inv.subtotal is not None:
        inv.tax = round(inv.total - inv.subtotal, 2)
    if not inv.vendor:
        try:
            from .classify import guess_vendor_name
            inv.vendor = guess_vendor_name(text)
        except Exception:
            pass
    return inv


def _count_table_rows(pdf_path: str, pdf_doc=None) -> int:
    count = 0
    if pdf_doc is not None:
        for page in pdf_doc.pages:
            try:
                tables = page.extract_tables()
                for t in (tables or []):
                    count += max(0, len(t) - 1)
            except Exception:
                pass
        return count
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            try:
                tables = page.extract_tables()
                for t in (tables or []):
                    count += max(0, len(t) - 1)
            except Exception:
                pass
    return count


def extract_generic(pdf_path: str, api_key: str, model: str,
                    provider: str = "anthropic", base_url: str = None,
                    _is_retry: bool = False, pdf_doc=None) -> Invoice:
    """Extract any invoice with no template, using an LLM. Raises on hard failure."""
    sec = load_settings()
    ocr_enabled = sec.get("ocr_enabled", True)
    dpi = int(sec.get("ocr_dpi", 300))
    min_chars = int(sec.get("ocr_min_chars", 50))
    min_conf = float(sec.get("ocr_min_confidence", 0.5))

    def _run_extraction(doc):
        if ocr_enabled:
            text, ocr_used, ocr_conf = extract_text_with_ocr_fallback(
                pdf_path, dpi=dpi, min_chars=min_chars, min_confidence=min_conf, pdf_doc=doc
            )
        else:
            text = _pdf_text(pdf_path, pdf_doc=doc)
            ocr_used, ocr_conf = False, 1.0

        text_clean = re.sub(r'---\s*PAGE\s*\d+\s*---', '', text, flags=re.IGNORECASE)
        text_clean = re.sub(r'===\s*(?:OCR TEXT|NATIVE PAGE TEXT|RAW PAGE TEXT|STRUCTURED TABLES)\s*===', '', text_clean, flags=re.IGNORECASE)
        text_clean = re.sub(r'\n{3,}', '\n\n', text_clean).strip()

        if not text_clean.strip():
            raise ValueError("No text could be extracted from PDF (native or OCR).")

        # ---- security guardrails before anything leaves the machine ----
        allowed, prepared, note = guard_ai_call(text_clean, provider, base_url)
        if not allowed:
            log_event("ai_blocked", note, outcome="blocked")
            raise PermissionError(note)

        # layout-aware table column extraction
        structured_rows = extract_table_with_columns(pdf_path, pdf_doc=doc)
        if structured_rows:
            structured_rows = validate_line_items(structured_rows)
            mismatches = [r for r in structured_rows if r.get('_math_mismatch')]
            if mismatches:
                log_event("math_mismatch", f"{len(mismatches)} rows failed Qty*Rate check")
                mismatch_hint = (
                    "WARNING: The following rows have Qty * Rate != Taxable Value. "
                    "Re-examine the table carefully for these rows:\n"
                )
                for r in mismatches:
                    mismatch_hint += (
                        f"  Description: {r.get('description','?')} | "
                        f"Qty: {r.get('quantity','?')} | "
                        f"Rate: {r.get('rate','?')} | "
                        f"Taxable: {r.get('taxable_value','?')}\n"
                    )
                prepared = mismatch_hint + "\n\n" + prepared

            table_hint = _format_structured_rows(structured_rows)
            if table_hint:
                prepared = table_hint + "\n\n" + prepared

        # financial summary extraction
        financial_summary = extract_financial_summary(pdf_path, pdf_doc=doc)
        if financial_summary:
            financial_hint = _format_financial_summary(financial_summary)
            if financial_hint:
                prepared = financial_hint + "\n\n" + prepared

        row_hint = _count_table_rows(pdf_path, pdf_doc=doc)
        return text_clean, prepared, note, ocr_used, ocr_conf, row_hint

    if pdf_doc is not None:
        text, prepared, note, ocr_used, ocr_conf, row_hint = _run_extraction(pdf_doc)
    else:
        with pdfplumber.open(pdf_path) as doc:
            text, prepared, note, ocr_used, ocr_conf, row_hint = _run_extraction(doc)
    row_hint_str = (
        f"\n\nNOTE: This invoice contains approximately {row_hint} data rows "
        f"across all tables. Your line_items array MUST contain all {row_hint} "
        f"entries (excluding header/total rows)."
        if row_hint > 0 else ""
    )
    # Estimate input token usage (1 token ≈ 4 chars).
    # For small context windows (vLLM with max_model_len 8192),
    # switch to compact prompt to free up more tokens for output.
    _estimated_input_tokens = len(prepared) // 4
    _context_tight = (
        "api.openai.com" not in (base_url or "")
        and "generativelanguage.googleapis.com" not in (base_url or "")
        and _estimated_input_tokens > 2500
    )
    _instructions = INSTRUCTIONS_COMPACT if _context_tight else INSTRUCTIONS
    prompt = (f"{_instructions}\n\n{wrap_untrusted(prepared)}"
              f"{row_hint_str}\n\nReturn the JSON now.")
    log_event("ai_call",
              f"file={os.path.basename(pdf_path)} provider={provider} model={model} "
              f"chars={len(prepared)} key={mask_key(api_key)}"
              + (f" [{note}]" if note else ""))

    def _ask(extra=""):
        p = prompt + extra
        # Dynamic token budget: (rows × 200 tokens/row) + 1500 header overhead
        # + 20% safety buffer. Capped at provider maximums.
        _row_count = row_hint   # FIX 2: reuse result from outer scope — avoids double PDF parse
        _needed = int((_row_count * 200 + 1500) * 1.2)
        _is_gemini = "generativelanguage.googleapis.com" in (base_url or "")
        _provider_cap = 65536 if _is_gemini else 16384
        _tokens = max(4096, min(_needed, _provider_cap))

        if provider == "anthropic":
            return _call_anthropic(p, api_key, model, max_tokens=min(_tokens, 8192))
        return _call_openai(p, api_key, model, base_url, max_tokens=_tokens)

    try:
        raw = _ask()
    except RuntimeError as e:
        log_event("ai_call", f"file={os.path.basename(pdf_path)} api_error",
                  outcome="error")
        raise ValueError(
            f"API call failed — check your API key, model name, and base URL.\n"
            f"Detail: {e}"
        )

    if not raw or not raw.strip():
        log_event("ai_call", f"file={os.path.basename(pdf_path)} empty_response",
                  outcome="error")
        raise ValueError(
            "The AI returned an empty response. Possible causes:\n"
            "  • Invalid API key or expired quota\n"
            "  • Wrong model name (check spelling)\n"
            "  • Wrong base URL for this provider\n"
            "  • Provider rejected the request format\n"
            f"Provider: {provider} | Model: {model} | Base URL: {base_url}"
        )

    try:
        data = _parse_json(raw)
    except Exception:
        # one retry with a firmer instruction before giving up
        raw2 = _ask("\n\nIMPORTANT: reply with the JSON object ONLY - no explanation, "
                    "no markdown fences.")
        try:
            data = _parse_json(raw2)
        except Exception as e:
            log_event("ai_call", f"file={os.path.basename(pdf_path)} invalid JSON",
                      outcome="error")
            raise ValueError(f"The model did not return valid JSON ({e}). "
                             f"First 300 chars:\n{raw2[:300]}")

    inv = invoice_from_data(data, os.path.basename(pdf_path))
    inv = _fallback_fields(inv, text)

    try:
        ver = importlib.metadata.version("rapidocr-onnxruntime")
        ocr_ver_str = f"rapidocr-onnxruntime-{ver}"
    except Exception:
        ocr_ver_str = "rapidocr-onnxruntime"

    inv.ocr_used = ocr_used
    inv.ocr_confidence = ocr_conf
    inv.ocr_engine_version = ocr_ver_str if ocr_used else ""

    from .validate import validate
    inv = validate(inv)

    # FIX 6: auto-retry on math validation failure (once only)
    if not _is_retry and not inv.validation_ok and _has_math_failure(inv):
        retry_hint = _build_retry_hint(inv)
        try:
            raw_retry = _ask("\n\n" + retry_hint)
            data_retry = _parse_json(raw_retry)
            inv2 = invoice_from_data(data_retry, os.path.basename(pdf_path))
            inv2 = _fallback_fields(inv2, text)
            inv2.ocr_used = ocr_used
            inv2.ocr_confidence = ocr_conf
            inv2.ocr_engine_version = ocr_ver_str if ocr_used else ""
            inv2 = validate(inv2)
            if _score(inv2) > _score(inv):
                inv = inv2
        except Exception:
            pass

    log_event("ai_extracted",
              f"file={os.path.basename(pdf_path)} items={len(inv.line_items)} "
              f"total={inv.total} ocr_used={ocr_used} ocr_conf={ocr_conf:.2f}")
    return inv

