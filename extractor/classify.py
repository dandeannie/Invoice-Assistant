"""
Auto-detect which vendor template matches an invoice, so the user doesn't have to pick
one. Scores every template's identify keyword(s) against the PDF text and returns the
best match with a confidence score.
"""
import os
import re

import pdfplumber

from .templates import list_vendors, load_template


def pdf_text(pdf_path: str, first_page_only: bool = True) -> str:
    from .ocr import extract_text_with_ocr_fallback
    text, _, _ = extract_text_with_ocr_fallback(pdf_path)
    # FIX 8: strip OCR page markers before vendor scoring — markers make the
    # truthiness check pass even when no real content was extracted, and they
    # pollute keyword matching with structural noise
    if text:
        text = re.sub(r'---\s*PAGE\s*\d+\s*---', '', text, flags=re.IGNORECASE)
        text = re.sub(r'===.*?===', '', text, flags=re.IGNORECASE)
        text = text.strip()
    if text and text.strip():
        if first_page_only:
            p2 = text.find("--- PAGE 2 ---")
            return text[:p2] if p2 != -1 else text
        return text
    with pdfplumber.open(pdf_path) as pdf:
        pages = pdf.pages[:1] if first_page_only else pdf.pages
        return "\n".join((p.extract_text() or "") for p in pages)



def _keywords(tpl: dict):
    """All identify keywords in a template, including inside variants."""
    out = []
    kw = (tpl.get("identify") or {}).get("keyword")
    if kw:
        out.append((kw, None))
    for v in (tpl.get("variants") or []):
        vkw = (v.get("identify") or {}).get("keyword")
        if vkw:
            out.append((vkw, v.get("vendor")))
    return out


def _score(text_low: str, keyword: str) -> float:
    """1.0 for a full keyword hit, 0.85 if every significant word appears (different
    order/spacing), otherwise 0. Partial word overlap is deliberately NOT enough -
    'Software Solutions' appears in many company names."""
    kw = keyword.lower().strip()
    if not kw:
        return 0.0
    if kw in text_low:
        return 1.0
    words = [w for w in re.split(r"\W+", kw) if len(w) > 2]
    if len(words) < 2:
        return 0.0
    return 0.85 if all(w in text_low for w in words) else 0.0


def detect_vendor(pdf_path: str, text: str = None):
    """Return {'id','name','score','variant'} for the best-matching template, or None.
    Score is 0-1; anything below ~0.6 is a weak guess."""
    text = text if text is not None else pdf_text(pdf_path)
    low = text.lower()
    best = None
    for v in list_vendors():
        try:
            tpl = load_template(v["id"])
        except Exception:
            continue
        for kw, variant_vendor in _keywords(tpl):
            s = _score(low, kw)
            if s > 0 and (best is None or s > best["score"]):
                best = {"id": v["id"], "name": v["name"], "score": round(s, 2),
                        "variant": variant_vendor, "keyword": kw}
    return best


_SUFFIXES = ("pvt ltd", "private limited", "limited", " ltd", " llp", " inc", " llc",
             " gmbh", " corp", " corporation", " co.", " company", " enterprises",
             " technologies", " solutions", " systems", " industries", " traders")

_LABELS = re.compile(
    r"\s+(invoice\s*(no|number|date)|bill\s*(no|number|date)|receipt\s*no|date|gstin|"
    r"po\s*number|order\s*ref|tax\s*invoice)\b.*$", re.I)


_HEADERISH = {"customer", "order", "size", "pickup", "time", "qty", "qty.", "item",
              "items", "price", "subtotal", "total", "amount", "description", "date",
              "bill", "ship", "to", "from", "sl", "no", "hsn", "sac", "rate", "tax"}


def guess_vendor_name(text: str) -> str:
    """Best-effort supplier name when no template matches. Prefers a line carrying a
    company suffix (Pvt Ltd, LLC, ...), trimming any label that shares the same line.
    Returns "" rather than guessing wrongly."""
    skip = ("tax invoice", "invoice", "bill", "receipt", "original for",
            "duplicate for", "triplicate", "credit note", "debit note", "proforma")
    lines = [" ".join(l.split()) for l in text.splitlines() if l.strip()]

    def headerish(s):
        toks = [t.strip(":.").lower() for t in s.split()]
        if not toks:
            return True
        hits = sum(1 for t in toks if t in _HEADERISH)
        return hits >= 2 and hits >= len(toks) / 2

    # pass 1: a line that looks like a company name
    for s in lines[:25]:
        low = s.lower()
        if any(low.startswith(k) for k in skip) or headerish(s):
            continue
        if any(suf in low for suf in _SUFFIXES):
            cleaned = _LABELS.sub("", s).strip(" -|,")
            if 3 < len(cleaned) <= 70:
                return cleaned

    # pass 2: first substantial, label-free line
    for s in lines[:15]:
        low = s.lower()
        if len(s) < 4 or len(s) > 70:
            continue
        if any(low.startswith(k) or low == k for k in skip) or headerish(s):
            continue
        if ":" in s or re.search(r"\d{2,}", s):
            continue
        return s
    return ""
