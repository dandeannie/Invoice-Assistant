"""
Exports into formats other systems can import: Tally (XML), QuickBooks / Zoho Books
(CSV), and JSON for any API or downstream script.
"""
import csv
import json
from xml.sax.saxutils import escape

from .models import Invoice


def _tax_fields(inv):
    """Pull GST components out of extra (case-insensitive)."""
    out = {}
    for k, v in (inv.extra or {}).items():
        lk = k.lower()
        if lk in ("cgst", "sgst", "igst", "cess", "vat") and isinstance(v, (int, float)):
            out[lk.upper()] = v
    return out


def to_json(invoices, path: str):
    """Full structured dump - useful for APIs, audits, or loading into another system."""
    data = []
    for inv in invoices:
        data.append({
            "source_file": inv.source_file,
            "vendor": inv.vendor,
            "invoice_number": inv.invoice_number,
            "invoice_date": inv.invoice_date,
            "po_number": inv.po_number,
            "subtotal": inv.subtotal,
            "tax": inv.tax,
            "total": inv.total,
            "taxes": _tax_fields(inv),
            "extra": {k: v for k, v in (inv.extra or {}).items() if not k.startswith("_")},
            "line_items": [li.cols for li in inv.line_items],
            "validation_ok": inv.validation_ok,
            "validation_notes": inv.validation_notes,
            "rule_failures": getattr(inv, "rule_failures", []),
            "duplicate_note": getattr(inv, "duplicate_note", ""),
            "reconciliation": inv.reconciliation or {},
        })
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return path


def to_quickbooks_csv(invoices, path: str):
    """Bill-import style CSV accepted by QuickBooks / Zoho Books style importers
    (one row per line item, invoice header repeated)."""
    cols = ["Bill No", "Supplier", "Bill Date", "Due Date", "PO Number",
            "Item Description", "Qty", "Rate", "Amount", "Tax Amount",
            "Bill Subtotal", "Bill Tax", "Bill Total", "Currency"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for inv in invoices:
            cur = (inv.extra or {}).get("currency", "INR")
            items = inv.line_items or [None]
            for li in items:
                c = li.cols if li else {}
                w.writerow([
                    inv.invoice_number or "", inv.vendor or "", inv.invoice_date or "",
                    (inv.extra or {}).get("due_date", ""), inv.po_number or "",
                    c.get("description", ""), c.get("quantity", ""),
                    c.get("rate", c.get("unit_price", "")),
                    c.get("taxable_value", c.get("amount", "")),
                    c.get("tax_amount", c.get("cgst", "")),
                    inv.subtotal if inv.subtotal is not None else "",
                    inv.tax if inv.tax is not None else "",
                    inv.total if inv.total is not None else "", cur,
                ])
    return path


def to_tally_xml(invoices, path: str, company_name: str = ""):
    """Tally Prime/ERP9 'Purchase' voucher import XML. Import via
    Gateway of Tally > Import Data > Vouchers."""
    parts = ['<ENVELOPE>', '<HEADER><TALLYREQUEST>Import Data</TALLYREQUEST></HEADER>',
             '<BODY><IMPORTDATA>',
             '<REQUESTDESC><REPORTNAME>Vouchers</REPORTNAME>']
    if company_name:
        parts.append('<STATICVARIABLES><SVCURRENTCOMPANY>'
                     f'{escape(company_name)}</SVCURRENTCOMPANY></STATICVARIABLES>')
    parts.append('</REQUESTDESC><REQUESTDATA>')

    for inv in invoices:
        date_str = (inv.invoice_date or "").replace("-", "")  # YYYYMMDD
        vendor = escape(inv.vendor or "Unknown Supplier")
        num = escape(inv.invoice_number or "")
        total = inv.total or 0.0
        parts.append(
            '<TALLYMESSAGE xmlns:UDF="TallyUDF">'
            f'<VOUCHER VCHTYPE="Purchase" ACTION="Create" OBJVIEW="Invoice Voucher View">'
            f'<DATE>{date_str}</DATE>'
            f'<REFERENCE>{num}</REFERENCE>'
            f'<VOUCHERTYPENAME>Purchase</VOUCHERTYPENAME>'
            f'<VOUCHERNUMBER>{num}</VOUCHERNUMBER>'
            f'<PARTYLEDGERNAME>{vendor}</PARTYLEDGERNAME>'
            f'<PERSISTEDVIEW>Invoice Voucher View</PERSISTEDVIEW>'
            # credit the supplier with the gross amount
            f'<ALLLEDGERENTRIES.LIST>'
            f'<LEDGERNAME>{vendor}</LEDGERNAME>'
            f'<ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>'
            f'<AMOUNT>{total:.2f}</AMOUNT>'
            f'</ALLLEDGERENTRIES.LIST>'
        )
        # debit purchases with the taxable value
        sub = inv.subtotal if inv.subtotal is not None else total
        parts.append(
            '<ALLLEDGERENTRIES.LIST>'
            '<LEDGERNAME>Purchase Accounts</LEDGERNAME>'
            '<ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>'
            f'<AMOUNT>-{sub:.2f}</AMOUNT>'
            '</ALLLEDGERENTRIES.LIST>'
        )
        # debit each tax component separately
        taxes = _tax_fields(inv)
        if not taxes and inv.tax:
            taxes = {"Input Tax": inv.tax}
        for name, amt in taxes.items():
            parts.append(
                '<ALLLEDGERENTRIES.LIST>'
                f'<LEDGERNAME>{escape(str(name))}</LEDGERNAME>'
                '<ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>'
                f'<AMOUNT>-{float(amt):.2f}</AMOUNT>'
                '</ALLLEDGERENTRIES.LIST>'
            )
        parts.append('</VOUCHER></TALLYMESSAGE>')

    parts.append('</REQUESTDATA></IMPORTDATA></BODY></ENVELOPE>')
    xml = "\n".join(parts)
    with open(path, "w", encoding="utf-8") as f:
        f.write(xml)
    return path
