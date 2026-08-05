"""
Command-line alternative to the web app, for people who prefer a terminal or want
to automate/schedule the job later.

Usage:
    python run.py <vendor_id> <folder_of_pdfs> [output_folder]

Example:
    python run.py acme sample_invoices output

<vendor_id> is the template filename without extension (acme, globex, ...).
"""
import os
import sys

from extractor import extract_invoice, validate, load_template, to_excel, to_csv


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    vendor_id = sys.argv[1]
    pdf_folder = sys.argv[2]
    out_folder = sys.argv[3] if len(sys.argv) > 3 else "output"
    os.makedirs(out_folder, exist_ok=True)

    template = load_template(vendor_id)
    pdfs = [f for f in sorted(os.listdir(pdf_folder)) if f.lower().endswith(".pdf")]
    if not pdfs:
        print(f"No PDF files found in {pdf_folder}")
        sys.exit(1)

    invoices = []
    for fn in pdfs:
        inv = validate(extract_invoice(os.path.join(pdf_folder, fn), template))
        invoices.append(inv)
        status = "OK" if inv.validation_ok else "CHECK -> " + "; ".join(inv.validation_notes)
        print(f"{fn:30s} {inv.invoice_number or '?':12s} total={inv.total}  [{status}]")

    xlsx = to_excel(invoices, os.path.join(out_folder, f"{vendor_id}_invoices.xlsx"))
    to_csv(invoices, out_folder)
    print(f"\nDone. Wrote {xlsx}")
    flagged = [i for i in invoices if not i.validation_ok]
    if flagged:
        print(f"{len(flagged)} invoice(s) flagged for review (see the highlighted rows).")


if __name__ == "__main__":
    main()
