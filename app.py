"""
Invoice → Excel Extractor — main page.
Pick a vendor (or let the tool detect it), upload PDFs, review/fix the data, export.
"""
import os
from pathlib import Path
import tempfile

import streamlit as st

from extractor.ui import apply_theme, hero
from extractor.security import (check_upload, safe_filename, log_event, load_settings)
from extractor import (extract_invoice, validate, list_vendors, load_template, to_excel,
                       reconcile, detect_vendor, guess_vendor_name, pdf_text,
                       apply_rules, load_rules, check_duplicates, append_history,
                       file_hash, to_json, to_quickbooks_csv, to_tally_xml)

st.set_page_config(page_title="Invoice → Excel Extractor", page_icon="📄", layout="wide")
apply_theme()
hero("📄 Invoice → Excel Extractor",
     "Upload invoices, review what was captured, and export to Excel, Tally, or your accounting system.")

ss = st.session_state
vendors = list_vendors()

st.info("✨ **No template for a vendor?** Use **Extract Any Invoice** in the left sidebar "
        "to pull data from any invoice, bill, or receipt with AI — no setup needed.")

# ---- Step 1: vendor ----
st.markdown('<span class="step-label">Step 1</span>  **Choose how to read the invoices**',
            unsafe_allow_html=True)
AUTO = {"id": "__auto__", "name": "🔎 Auto-detect vendor (recommended)"}
options = [AUTO] + vendors
vendor_choice = st.selectbox("Vendor", options=options,
                             format_func=lambda v: v["name"], label_visibility="collapsed")
if not vendors:
    st.warning("No vendor templates yet — use **Extract Any Invoice**, or create one on "
               "**Add New Vendor**.")

# ---- Step 2: upload ----
st.markdown('<span class="step-label">Step 2</span>  **Upload PDF invoices**',
            unsafe_allow_html=True)
uploads = st.file_uploader("Upload", type=["pdf"], accept_multiple_files=True,
                           label_visibility="collapsed")

# ---- Step 3: extract ----
st.markdown('<span class="step-label">Step 3</span>', unsafe_allow_html=True)
go = st.button("Extract invoices", type="primary", disabled=not uploads,
               use_container_width=True)

if go:
    settings = load_settings()
    invoices, unmatched, rejected = [], [], []
    if len(uploads) > int(settings.get("max_batch_files", 100)):
        st.error(f"Too many files at once (limit {settings['max_batch_files']}).")
        st.stop()
    bar = st.progress(0.0, text="Reading invoices...")
    for i, up in enumerate(uploads, start=1):
        data = up.getbuffer().tobytes()
        ok, msg = check_upload(data, safe_filename(up.name), settings)
        if not ok:
            rejected.append(msg)
            log_event("upload_rejected", msg, outcome="rejected")
            continue
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(data)
            tmp_path = tmp.name
        try:
            if vendor_choice["id"] == "__auto__":
                hit = detect_vendor(tmp_path)
                if not hit:
                    unmatched.append((up.name, guess_vendor_name(pdf_text(tmp_path))))
                    continue
                used_id = hit["id"]
            else:
                used_id = vendor_choice["id"]
            template = load_template(used_id)

            inv = validate(extract_invoice(tmp_path, template))
            inv.source_file = up.name
            inv.extra["_file_hash"] = file_hash(tmp_path)
            if not getattr(inv, 'ocr_used', False):
                try:
                    inv.reconciliation = reconcile(inv, tmp_path)
                    # FIX 10: skip reconciliation for scanned invoices — pdfplumber returns
                    # empty text for OCR-processed PDFs, causing false REVIEW flags
                except Exception:
                    pass
            apply_rules(inv, vendor_id=used_id)
            invoices.append(inv)
        finally:
            os.unlink(tmp_path)
        bar.progress(i / len(uploads), text=f"Reading invoices... ({i}/{len(uploads)})")
    bar.empty()

    check_duplicates(invoices)
    log_event("extract_batch",
              f"files={len(uploads)} extracted={len(invoices)} "
              f"unmatched={len(unmatched)} rejected={len(rejected)}")
    ss.invoices = invoices
    ss.unmatched = unmatched
    ss.rejected = rejected

invoices = ss.get("invoices") or []
for msg in (ss.get("rejected") or []):
    st.error(f"🚫 {msg}")
for name, guess in (ss.get("unmatched") or []):
    st.warning(f"⚠️ **{name}** — no matching template"
               + (f" (looks like **{guess}**)" if guess else "")
               + ". Go to **Add New Vendor** and use **⚡ Auto-build** to create one from "
                 "this invoice in a couple of clicks (no AI needed), or use "
                 "**Extract Any Invoice** for a one-off.")

if invoices:
    dup_count = sum(1 for i in invoices if i.duplicate_note)
    rule_count = sum(1 for i in invoices if i.rule_failures)
    flag_count = sum(1 for i in invoices if not i.validation_ok)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Extracted", len(invoices))
    c2.metric("Arithmetic issues", flag_count)
    c3.metric("Rule failures", rule_count)
    c4.metric("Possible duplicates", dup_count)

    if dup_count:
        st.error(f"🔁 {dup_count} possible duplicate invoice(s) — check before paying.")
        for i in invoices:
            if i.duplicate_note:
                st.caption(f"• **{i.source_file}**: {i.duplicate_note}")
    if rule_count:
        st.warning(f"📋 {rule_count} invoice(s) failed a business rule.")
        for i in invoices:
            for f in i.rule_failures:
                st.caption(f"• **{i.source_file}**: {f}")
    if not (dup_count or rule_count or flag_count):
        st.success("All invoices extracted, reconciled, and passed every rule.")

    # ---------- Step 4: review & fix ----------
    st.markdown('<span class="step-label">Step 4</span>  **Review & fix before export**',
                unsafe_allow_html=True)
    st.caption("Edit any cell that was captured incorrectly — your changes flow into "
               "every export below.")

    header_rows = [{
        "File": inv.source_file, "Vendor": inv.vendor,
        "Invoice #": inv.invoice_number or "", "Date": inv.invoice_date or "",
        "PO #": inv.po_number or "",
        "Subtotal": inv.subtotal, "Tax": inv.tax, "Total": inv.total,
    } for inv in invoices]
    edited = st.data_editor(header_rows, hide_index=True, use_container_width=True,
                            disabled=["File"], key="hdr_editor")
    for inv, row in zip(invoices, edited):
        inv.vendor = row["Vendor"]
        inv.invoice_number = row["Invoice #"] or None
        inv.invoice_date = row["Date"] or None
        inv.po_number = row["PO #"] or None
        for f in ("Subtotal", "Tax", "Total"):
            v = row[f]
            setattr(inv, f.lower(), float(v) if isinstance(v, (int, float)) else None)

    with st.expander("Line items", expanded=False):
        for inv in invoices:
            st.write(f"**{inv.source_file}** — {inv.invoice_number or ''}")
            rows = [dict(li.cols) for li in inv.line_items]
            if rows:
                ed = st.data_editor(rows, hide_index=True, use_container_width=True,
                                    num_rows="dynamic", key=f"li_{inv.source_file}")
                for li, r in zip(inv.line_items, ed):
                    li.cols.update(r)
                summable = set(inv.line_total_columns or [])
                sums = {}
                for k in summable:
                    vals = [li.cols.get(k) for li in inv.line_items
                            if isinstance(li.cols.get(k), (int, float))]
                    if vals:
                        sums[k] = round(sum(vals), 2)
                if sums:
                    st.caption("Column totals: " +
                               " · ".join(f"{k.replace('_',' ').title()}: {v:,.2f}"
                                          for k, v in sums.items()))
            else:
                st.caption("No line items captured.")

    recon = [i for i in invoices if i.reconciliation]
    if recon:
        with st.expander("Reconciliation vs original PDF", expanded=False):
            st.dataframe([{
                "File": i.source_file,
                "Status": "✅ OK" if i.reconciliation.get("status") == "OK" else "⚠️ REVIEW",
                "Printed total": i.reconciliation.get("printed_total"),
                "Extracted total": i.reconciliation.get("extracted_total"),
                "Printed subtotal": i.reconciliation.get("printed_subtotal"),
                "Extracted subtotal": i.reconciliation.get("extracted_subtotal"),
                "Line-items sum": i.reconciliation.get("line_items_sum"),
                "# lines": i.reconciliation.get("n_line_items"),
                "Notes": i.reconciliation.get("notes"),
            } for i in recon], use_container_width=True, hide_index=True)

    # ---------- Step 5: export ----------
    st.markdown('<span class="step-label">Step 5</span>  **Export**', unsafe_allow_html=True)
    with tempfile.TemporaryDirectory() as d:
        xp = os.path.join(d, "invoices.xlsx"); to_excel(invoices, xp)
        tp = os.path.join(d, "tally_import.xml"); to_tally_xml(invoices, tp)
        qp = os.path.join(d, "bills.csv"); to_quickbooks_csv(invoices, qp)
        jp = os.path.join(d, "invoices.json"); to_json(invoices, jp)
        xb = Path(xp).read_bytes()
        tb = Path(tp).read_bytes()
        qb = Path(qp).read_bytes()
        jb = Path(jp).read_bytes()

    e1, e2, e3, e4 = st.columns(4)
    e1.download_button("⬇ Excel", xb, "invoices.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       type="primary", use_container_width=True)
    e2.download_button("⬇ Tally XML", tb, "tally_import.xml", "application/xml",
                       use_container_width=True)
    e3.download_button("⬇ Accounting CSV", qb, "bills.csv", "text/csv",
                       use_container_width=True)
    e4.download_button("⬇ JSON", jb, "invoices.json", "application/json",
                       use_container_width=True)

    if st.button("✅ Mark as processed (adds to duplicate history)"):
        append_history(invoices)
        log_event("marked_processed", f"count={len(invoices)}")
        st.success("Recorded. These invoices will be flagged if they're uploaded again.")
else:
    st.caption("Tip: you can drop in many invoices at once — auto-detect handles mixed vendors.")
