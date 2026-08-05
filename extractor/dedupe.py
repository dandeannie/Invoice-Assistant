"""
Duplicate detection + processing history (audit trail).

Paying the same invoice twice is one of the most expensive AP mistakes, so every
extracted invoice is checked against (a) the others in the same batch and (b) everything
processed previously, which is kept in a small local history file.
"""
import csv
import hashlib
import os
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(__file__))
HISTORY_PATH = os.path.join(BASE, "output", "processing_history.csv")

FIELDS = ["processed_at", "source_file", "vendor", "invoice_number", "invoice_date",
          "total", "file_hash", "status"]


def file_hash(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def _key(vendor, number):
    # values can arrive as numbers (a template may type a numeric invoice number),
    # so coerce before string handling
    v = "" if vendor is None else str(vendor).strip().lower()
    n = "" if number is None else str(number).strip().lower().replace(" ", "")
    return f"{v}|{n}" if n else ""


def load_history():
    if not os.path.exists(HISTORY_PATH):
        return []
    with open(HISTORY_PATH, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def append_history(invoices):
    """Record this run so future runs can spot repeats."""
    os.makedirs(os.path.dirname(HISTORY_PATH), exist_ok=True)
    exists = os.path.exists(HISTORY_PATH)
    with open(HISTORY_PATH, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if not exists:
            w.writeheader()
        for inv in invoices:
            w.writerow({
                "processed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "source_file": inv.source_file,
                "vendor": inv.vendor,
                "invoice_number": inv.invoice_number or "",
                "invoice_date": inv.invoice_date or "",
                "total": inv.total if inv.total is not None else "",
                "file_hash": (inv.extra or {}).get("_file_hash", ""),
                "status": "OK" if inv.validation_ok else "REVIEW",
            })


def check_duplicates(invoices, history=None):
    """Mark duplicates within the batch and against history.
    Sets inv.duplicate_of / inv.duplicate_note. Returns the number flagged."""
    history = load_history() if history is None else history

    hist_by_key, hist_by_hash = {}, {}
    for row in history:
        k = _key(row.get("vendor"), row.get("invoice_number"))
        if k:
            hist_by_key.setdefault(k, row)
        if row.get("file_hash"):
            hist_by_hash.setdefault(row["file_hash"], row)

    seen_key, seen_hash = {}, {}
    flagged = 0
    for inv in invoices:
        note, dup_of = "", ""
        h = (inv.extra or {}).get("_file_hash", "")
        k = _key(inv.vendor, inv.invoice_number)

        # identical file, or same vendor+number, earlier in THIS batch
        if h and h in seen_hash:
            note, dup_of = "identical file already in this batch", seen_hash[h]
        elif k and k in seen_key:
            note, dup_of = "same vendor & invoice number in this batch", seen_key[k]
        # ...or in a previous run
        elif h and h in hist_by_hash:
            r = hist_by_hash[h]
            note = f"identical file processed on {r.get('processed_at','')}"
            dup_of = r.get("source_file", "")
        elif k and k in hist_by_key:
            r = hist_by_key[k]
            note = (f"invoice {inv.invoice_number} from {inv.vendor} already processed "
                    f"on {r.get('processed_at','')}")
            dup_of = r.get("source_file", "")

        if note:
            inv.duplicate_of = dup_of
            inv.duplicate_note = note
            flagged += 1
        if h:
            seen_hash.setdefault(h, inv.source_file)
        if k:
            seen_key.setdefault(k, inv.source_file)
    return flagged


def clear_history():
    if os.path.exists(HISTORY_PATH):
        os.remove(HISTORY_PATH)
        return True
    return False
