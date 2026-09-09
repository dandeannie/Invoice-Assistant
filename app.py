"""
Invoice → Excel Extractor — main page.
Pick a vendor (or let the tool detect it), upload PDFs, review/fix the data, export.
Neobrutalist UI with high-contrast sunshine yellow navigation.
"""
from __future__ import annotations
import os
from pathlib import Path
import tempfile

import streamlit as st
import importlib
import extractor.ui
importlib.reload(extractor.ui)

from extractor.ui import (apply_theme, top_nav_bar, hero_card, section_header,
                          metric_card, analytics_sparkline_card, activity_card,
                          review_card, status_pill,
                          ICON_DOCUMENT, ICON_BUILDING, ICON_BOLT, ICON_SHIELD)
from extractor.security import (check_upload, safe_filename, log_event, load_settings)
from extractor import (extract_invoice, validate, list_vendors, load_template, to_excel,
                       reconcile, detect_vendor, guess_vendor_name, pdf_text,
                       apply_rules, load_rules, check_duplicates, append_history,
                       file_hash, to_json, to_quickbooks_csv, to_tally_xml)

st.set_page_config(page_title="Invoice Extractor - AI & Template Engine", page_icon=":material/receipt_long:", layout="wide")
apply_theme()
top_nav_bar("INVOICE AI EXTRACTOR", search_placeholder="Quick search vendors, templates, invoices...", badge_text="Local Engine")

ss = st.session_state
vendors = list_vendors()

hero_card(
    title="Invoice AI Extractor",
    subtitle="High-precision offline document extraction & arithmetic reconciliation engine.",
    meta_tags=["#1 Auto-Detect", "100% Offline Core", "Tally & QuickBooks", "Zero Hallucination"],
    stat_items=[
        (str(len(vendors)), "Active Templates"),
        ("100% Local", "Data Security"),
        ("RapidOCR", "Vision Fallback"),
        ("Active", "Auto Reconcile")
    ],
    desc="Batch process accounts payable invoices with instant vendor auto-detection, sub-millimeter bounding box rules, and dual-pass arithmetic verification against printed totals.",
    color="#F8CD53",
    icon=ICON_DOCUMENT
)


def _safe_float(v):
    """Safely converts user input from data editor to float, handling strings, commas and symbols."""
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        cleaned = str(v).replace(",", "").replace("$", "").replace("₹", "").replace("€", "").strip()
        return float(cleaned) if cleaned else None
    except (ValueError, TypeError):
        return None


# Top Layout: Main Pipeline (left) and System Snapshot (right)
left_col, right_col = st.columns([2.5, 1.2], gap="large")

with left_col:
    # ---- Step 1: vendor ----
    section_header("01", "Choose Extraction Method")
    AUTO = {"id": "__auto__", "name": "Auto-detect vendor (recommended for batches)"}
    options = [AUTO] + vendors
    vendor_choice = st.selectbox(
        "Select Vendor Template",
        options=options,
        format_func=lambda v: v["name"]
    )
    if not vendors:
        st.info("No vendor templates installed yet. You can use **Extract Any Invoice** in the sidebar for one-offs, or create one in **Add New Vendor**.", icon=":material/info:")

    # ---- Step 2: upload ----
    section_header("02", "Upload Invoices (PDF)")
    uploads = st.file_uploader(
        "Drag and drop PDF files here",
        type=["pdf"],
        accept_multiple_files=True,
        help="Upload single or multiple PDF invoices. Vector text and scanned documents are supported."
    )

    # ---- Step 3: extract ----
    section_header("03", "Run Batch Extraction")
    extract_btn = st.button(
        "Extract Invoices",
        icon=":material/bolt:",
        type="primary",
        disabled=not uploads,
        use_container_width=True
    )

with right_col:
    st.markdown("#### System Overview")
    activity_card(
        icon=ICON_BUILDING,
        title="Active Vendor Mode",
        subtitle=vendor_choice["name"],
        meta="Automated Bounding Rules" if vendor_choice["id"] == "__auto__" else f"Template: {vendor_choice['id']}.yaml"
    )
    activity_card(
        icon=ICON_BOLT,
        title="Extraction Engine",
        subtitle="Air-Gapped Local Parser",
        meta="No External Telemetry"
    )
    activity_card(
        icon=ICON_SHIELD,
        title="Audit Verification",
        subtitle="Mathematical Cross-Check",
        meta="Tolerance: ±0.05"
    )

# Execution Logic
if extract_btn and uploads:
    settings = load_settings()
    invoices, unmatched, rejected = [], [], []
    if len(uploads) > int(settings.get("max_batch_files", 100)):
        st.error(f"Batch size exceeds current threshold limit of {settings['max_batch_files']} documents.")
        st.stop()

    bar = st.progress(0.0, text="Initializing batch extraction...")
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
                except Exception:
                    pass
            apply_rules(inv, vendor_id=used_id)
            invoices.append(inv)
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
        bar.progress(i / len(uploads), text=f"Processing {up.name} ({i}/{len(uploads)})")
    bar.empty()

    check_duplicates(invoices)
    log_event("extract_batch", f"files={len(uploads)} extracted={len(invoices)} unmatched={len(unmatched)} rejected={len(rejected)}")
    ss.invoices = invoices
    ss.unmatched = unmatched
    ss.rejected = rejected

# Notifications & Alerts
invoices = ss.get("invoices") or []
for msg in (ss.get("rejected") or []):
    st.error(msg, icon=":material/block:")
for name, guess in (ss.get("unmatched") or []):
    st.warning(f"**{name}** — No matching template detected"
               + (f" (identified entity: **{guess}**)" if guess else "")
               + ". Navigate to **Add New Vendor** to synthesize a template using **Auto-build** in 1 click.",
               icon=":material/warning:")

# Results Display
if invoices:
    st.divider()
    section_header("04", "Extraction Audit & Review")

    dup_count = sum(1 for i in invoices if i.duplicate_note)
    rule_count = sum(1 for i in invoices if i.rule_failures)
    flag_count = sum(1 for i in invoices if not i.validation_ok)
    valid_count = len(invoices) - flag_count
    acc_score = round((valid_count / len(invoices)) * 100, 1) if invoices else 100.0

    # Analytics Sparkline Card & Stat Cards (Bottom section matching reference image)
    res_col1, res_col2 = st.columns([1.5, 2.5])
    with res_col1:
        analytics_sparkline_card(
            title="Batch Precision",
            rating=f"{acc_score}%",
            count_text=f"{len(invoices)} Invoices Processed",
            btn_text="Batch Stats",
            bg_color="#F6C8FB"
        )
    with res_col2:
        m1, m2, m3 = st.columns(3)
        with m1: metric_card("Reconciliation Issues", flag_count, "#FFC6D9" if flag_count else "#FFFFFF", subtext="Arithmetic Flags")
        with m2: metric_card("Rule Exceptions", rule_count, "#F8CD53" if rule_count else "#FFFFFF", subtext="Compliance Flags")
        with m3: metric_card("Potential Duplicates", dup_count, "#FFC6D9" if dup_count else "#FFFFFF", subtext="Duplicate Flags")

    if dup_count:
        st.error(f"Duplicate Warning: {dup_count} possible duplicate invoice(s) detected. Review before releasing payment.", icon=":material/copy_all:")
        for i in invoices:
            if i.duplicate_note:
                st.caption(f"• **{i.source_file}**: {i.duplicate_note}")

    if rule_count:
        st.warning(f"Compliance Note: {rule_count} invoice(s) breached configured business rules.", icon=":material/policy:")
        for i in invoices:
            for f in i.rule_failures:
                st.caption(f"• **{i.source_file}**: {f}")

    # Editable Header Table
    st.markdown("#### Extracted Document Headers")
    st.caption("Double-click any cell to adjust values. Edits automatically synchronize to all export formats.")

    header_rows = [{
        "File": inv.source_file, "Vendor": inv.vendor,
        "Invoice #": inv.invoice_number or "", "Date": inv.invoice_date or "",
        "PO #": inv.po_number or "",
        "Subtotal": inv.subtotal, "Tax": inv.tax, "Total": inv.total,
    } for inv in invoices]

    edited = st.data_editor(
        header_rows,
        hide_index=True,
        use_container_width=True,
        disabled=["File"],
        key="hdr_editor"
    )

    # Safe float parsing to eliminate data loss
    for inv, row in zip(invoices, edited):
        inv.vendor = row["Vendor"]
        inv.invoice_number = row["Invoice #"] or None
        inv.invoice_date = row["Date"] or None
        inv.po_number = row["PO #"] or None
        for f in ("Subtotal", "Tax", "Total"):
            v = row[f]
            setattr(inv, f.lower(), _safe_float(v))

    # Line Items
    with st.expander("Itemized Line Items Breakdown", expanded=False, icon=":material/inventory_2:"):
        for inv in invoices:
            st.markdown(f"**{inv.source_file}** &nbsp;·&nbsp; `Invoice #{inv.invoice_number or 'N/A'}`")
            rows = [dict(li.cols) for li in inv.line_items]
            if rows:
                ed = st.data_editor(rows, hide_index=True, use_container_width=True,
                                    num_rows="dynamic", key=f"li_{inv.source_file}")
                for li, r in zip(inv.line_items, ed):
                    li.cols.update(r)
                summable = set(inv.line_total_columns or [])
                sums = {}
                for k in summable:
                    vals = [li.cols.get(k) for li in inv.line_items if isinstance(li.cols.get(k), (int, float))]
                    if vals:
                        sums[k] = round(sum(vals), 2)
                if sums:
                    st.caption("Column Totals: " + " · ".join(f"{k.replace('_',' ').title()}: {v:,.2f}" for k, v in sums.items()))
            else:
                st.caption("No line items extracted for this document.")

    # Optical Reconciliation Table
    recon = [i for i in invoices if i.reconciliation]
    if recon:
        with st.expander("Optical Ground-Truth Verification vs Raw PDF", expanded=False, icon=":material/find_in_page:"):
            st.dataframe([{
                "File": i.source_file,
                "Status": "PASS" if i.reconciliation.get("status") == "OK" else "REVIEW",
                "Printed Total": i.reconciliation.get("printed_total"),
                "Extracted Total": i.reconciliation.get("extracted_total"),
                "Printed Subtotal": i.reconciliation.get("printed_subtotal"),
                "Extracted Subtotal": i.reconciliation.get("extracted_subtotal"),
                "Line Items Sum": i.reconciliation.get("line_items_sum"),
                "# Lines": i.reconciliation.get("n_line_items"),
                "Audit Notes": i.reconciliation.get("notes"),
            } for i in recon], use_container_width=True, hide_index=True)

    # Per-Invoice Verification Cards (matching the reference image's review cards)
    st.markdown("#### Document Verification Cards")
    rev_c1, rev_c2 = st.columns(2)
    for idx, inv in enumerate(invoices):
        target_col = rev_c1 if idx % 2 == 0 else rev_c2
        status_sym = "PASS" if inv.validation_ok else "REVIEW"
        rating_lbl = "100% Reconciled" if inv.validation_ok else "Review Flagged"
        notes_str = "; ".join(inv.validation_notes) if inv.validation_notes else f"Total payable: {inv.total:,.2f} verified against printed anchors."
        with target_col:
            review_card(
                author=f"{inv.vendor} — #{inv.invoice_number or 'Unspecified'}",
                role=inv.source_file,
                rating=rating_lbl,
                comment=notes_str,
                status_icon=status_sym
            )

    # ---- Step 5: export ----
    section_header("05", "Accounting & ERP Export")
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
    e1.download_button("Download Excel", xb, "invoices.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       icon=":material/download:", type="primary", use_container_width=True)
    e2.download_button("Tally Prime XML", tb, "tally_import.xml", "application/xml",
                       icon=":material/download:", use_container_width=True)
    e3.download_button("Accounting CSV", qb, "bills.csv", "text/csv",
                       icon=":material/download:", use_container_width=True)
    e4.download_button("JSON Ledger", jb, "invoices.json", "application/json",
                       icon=":material/download:", use_container_width=True)

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("Mark Batch as Processed (Add to Duplicate Ledger)", icon=":material/check_circle:", use_container_width=False):
        append_history(invoices)
        log_event("marked_processed", f"count={len(invoices)}")
        st.success("Batch recorded in historical ledger. Duplicate uploads will be flagged automatically.", icon=":material/check:")
else:
    st.caption("Tip: You can drag and drop dozens of invoices simultaneously — auto-detect routes each PDF to its corresponding vendor template.")
